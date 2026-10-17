"""Friend-only matches, invitations and authenticated game transport."""
import asyncio
import time
import json
import base64
from uuid import uuid4
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException, Query
from pydantic import BaseModel, Field
from app.auth import require_user, fail
from app.storage.db import connect, utcnow
from app.core import invitations as service
from app.core.match_repository import active_match, member_match, match_view, expire
from app.core.rooms_manager import RoomsManager
from app.api.realtime import authenticate_socket, notify

router=APIRouter(prefix='/api')
rooms_manager=RoomsManager()
class Invitees(BaseModel):
    invitee_ids:list[str]=Field(min_length=1,max_length=3)

async def changed(match_id):
    with connect() as db:
        members=db.execute('SELECT user_id FROM match_members WHERE match_id=?',(match_id,)).fetchall()
        invites=db.execute("SELECT id,invitee_id,status FROM invitations WHERE match_id=?",(match_id,)).fetchall()
    for p in members: await notify(p['user_id'],{'type':'match_update','match_id':match_id})
    for i in invites:
        await notify(i['invitee_id'],{'type':'invitation','invitation_id':i['id']} if i['status']=='pending' else {'type':'invitation_update','match_id':match_id})
    async with rooms_manager.lock:
        if rooms_manager.connections.get(match_id): await rooms_manager._broadcast(match_id)

@router.post('/matches',status_code=201)
async def create(payload:Invitees,user=Depends(require_user)):
    mid=str(uuid4())
    with connect() as db:
        if active_match(db,user['id']): fail(409,'already_in_match','你已经在对局中')
        db.execute("INSERT INTO matches(id,host_id,status,created_at,updated_at) VALUES(?,?,'inviting',?,?)",(mid,user['id'],utcnow(),utcnow()))
        db.execute('INSERT INTO match_members(match_id,user_id,seat,ready,joined_at) VALUES(?,?,1,1,?)',(mid,user['id'],utcnow()))
        service.invite(db,mid,user['id'],payload.invitee_ids)
        result=match_view(db,mid,user['id'])
    await changed(mid)
    return {'match':result}

@router.post('/matches/{mid}/invitations')
async def invite(mid:str,payload:Invitees,user=Depends(require_user)):
    with connect() as db:
        service.invite(db,mid,user['id'],payload.invitee_ids)
        result=match_view(db,mid,user['id'])
    await changed(mid)
    return {'match':result}

@router.get('/invitations')
def pending(user=Depends(require_user)):
    with connect() as db:
        expire(db)
        rows=db.execute("SELECT i.*,u.account,u.display_name FROM invitations i JOIN users u ON u.id=i.inviter_id WHERE i.invitee_id=? AND i.status='pending'",(user['id'],)).fetchall()
        return {'items':[{'id':i['id'],'match_id':i['match_id'],'inviter':{'id':i['inviter_id'],'account':i['account'],'display_name':i['display_name']},'members_count':db.execute('SELECT COUNT(*) AS n FROM match_members WHERE match_id=?',(i['match_id'],)).fetchone()['n'],'expires_at':i['expires_at']} for i in rows]}

@router.post('/invitations/{iid}/accept')
async def accept(iid:str,user=Depends(require_user)):
    with connect() as db:
        mid=service.accept(db,iid,user['id']); result=match_view(db,mid,user['id'])
    await changed(mid)
    await notify(user['id'],{'type':'invitation_update','match_id':mid})
    return {'match':result}

@router.post('/invitations/{iid}/decline',status_code=204)
async def decline(iid:str,user=Depends(require_user)):
    with connect() as db:
        row=service.invitation(db,iid,user['id'])
        db.execute("UPDATE invitations SET status='declined',responded_at=? WHERE id=?",(utcnow(),iid))
    await notify(row['inviter_id'],{'type':'invitation_update','match_id':row['match_id']})

@router.get('/matches/{mid}')
def get_match(mid:str,user=Depends(require_user)):
    with connect() as db: return {'match':match_view(db,mid,user['id'])}

@router.post('/matches/{mid}/start')
async def start(mid:str,user=Depends(require_user)):
    await rooms_manager.start(mid,user['id'])
    with connect() as db: result=match_view(db,mid,user['id'])
    await changed(mid)
    return {'match':result}

@router.post('/matches/{mid}/leave',status_code=204)
async def leave(mid:str,user=Depends(require_user)):
    await rooms_manager.leave(mid,user['id'])

@router.get('/me/match-history')
def history(limit:int=Query(20,ge=1,le=100),cursor:str='',user=Depends(require_user)):
    cursor_time, cursor_id = '', ''
    if cursor:
        try:
            cursor_time, cursor_id = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            if not isinstance(cursor_time,str) or not isinstance(cursor_id,str): raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            fail(422,'invalid_cursor','历史记录游标无效')
    with connect() as db:
        rows=db.execute("SELECT m.* FROM matches m JOIN match_members mm ON mm.match_id=m.id WHERE mm.user_id=? AND m.status IN ('finished','cancelled','aborted') AND (?='' OR m.updated_at<? OR (m.updated_at=? AND m.id<?)) ORDER BY m.updated_at DESC,m.id DESC LIMIT ?",(user['id'],cursor,cursor_time,cursor_time,cursor_id,limit+1)).fetchall()
        items=[]
        for row in rows[:limit]:
            members=[dict(p) for p in db.execute('SELECT u.display_name,mm.seat FROM match_members mm JOIN users u ON u.id=mm.user_id WHERE mm.match_id=? ORDER BY mm.seat',(row['id'],)).fetchall()]
            hands=db.execute('SELECT scores FROM match_hands WHERE match_id=? ORDER BY hand_number DESC',(row['id'],)).fetchall()
            scores=json.loads(hands[0]['scores']) if hands else {}
            for p in members: p['score']=scores.get('ESWN'[p['seat']-1],0)
            items.append({'match_id':row['id'],'finished_at':row['updated_at'],'members':members,'hands':len(hands)})
        next_cursor = base64.urlsafe_b64encode(json.dumps([rows[limit-1]['updated_at'],rows[limit-1]['id']]).encode()).decode() if len(rows)>limit else None
        return {'items':items,'next_cursor':next_cursor}

@router.websocket('/matches/{mid}/ws')
async def match_socket(socket:WebSocket,mid:str):
    user=await authenticate_socket(socket)
    if not user: return
    uid=user['id']
    try:
        with connect() as db: member_match(db,mid,uid)
    except HTTPException:
        await socket.close(code=4403); return
    attached=False
    try:
        await rooms_manager.attach(mid,uid,socket); attached=True
        while True:
            message=await socket.receive_json()
            if not isinstance(message,dict):
                await socket.send_json({'type':'error','code':'invalid_message','message':'无效消息'}); continue
            try:
                await rooms_manager.handle(mid,uid,socket,message)
                if message.get('type')=='leave': return
            except HTTPException as error:
                detail=error.detail
                await socket.send_json({'type':'error','message':detail.get('detail') if isinstance(detail,dict) else detail,'code':detail.get('code','invalid_action') if isinstance(detail,dict) else 'invalid_action'})
    except (WebSocketDisconnect,ValueError,RuntimeError): pass
    except HTTPException as error:
        await socket.send_json({'type':'error','code':'already_connected' if error.status_code==409 else 'match_unavailable'})
        await socket.close(code=4409 if error.status_code==409 else 4403)
    finally:
        if attached: await rooms_manager.detach(mid,uid,socket)
