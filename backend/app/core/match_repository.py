"""Persistent match membership and engine-facing snapshots."""
import time
from app.storage.db import connect, utcnow
from app.auth import fail

ACTIVE = ('inviting', 'waiting', 'countdown', 'playing')

def active_match(db, user_id):
    row = db.execute("SELECT m.id FROM matches m JOIN match_members mm ON mm.match_id=m.id WHERE mm.user_id=? AND m.status IN ('inviting','waiting','countdown','playing')", (user_id,)).fetchone()
    return row['id'] if row else None

def member_match(db, match_id, user_id=None):
    row = db.execute('SELECT * FROM matches WHERE id=?', (match_id,)).fetchone()
    if row is None or (user_id and not db.execute('SELECT user_id FROM match_members WHERE match_id=? AND user_id=?', (match_id,user_id)).fetchone()):
        fail(404, 'match_not_found', '对局不存在或不可见')
    return row

def expire(db):
    db.execute("UPDATE invitations SET status='expired', responded_at=? WHERE status='pending' AND expires_at<=?", (utcnow(), utcnow()))

def match_view(db, match_id, user_id):
    from app.api.realtime import online
    row = member_match(db, match_id, user_id)
    expire(db)
    members = [dict(p) for p in db.execute('SELECT u.id AS user_id,u.account,u.display_name,mm.seat,mm.ready FROM match_members mm JOIN users u ON u.id=mm.user_id WHERE mm.match_id=? ORDER BY mm.seat', (match_id,)).fetchall()]
    for p in members:
        p['ready'] = bool(p['ready']); p['online'] = online(p['user_id'])
    invitations = []
    for i in db.execute('SELECT i.*,u.account,u.display_name FROM invitations i JOIN users u ON u.id=i.invitee_id WHERE i.match_id=? ORDER BY i.created_at', (match_id,)).fetchall():
        invitations.append({'id':i['id'], 'invitee':{'id':i['invitee_id'],'account':i['account'],'display_name':i['display_name']},'status':i['status'],'expires_at':i['expires_at']})
    return {'id':match_id,'host_id':row['host_id'],'status':row['status'],'members':members,'invitations':invitations,'ai_seats':[s for s in range(1,5) if s not in {p['seat'] for p in members}], 'start_at':row['start_at'],'server_time':time.time()*1000}

def snapshot(db, room_id):
    row = member_match(db, room_id)
    if row['status'] not in ACTIVE:
        fail(404,'match_ended','对局已结束')
    members = db.execute('SELECT mm.*,u.display_name FROM match_members mm JOIN users u ON u.id=mm.user_id WHERE match_id=? ORDER BY seat', (room_id,)).fetchall()
    players = [{'nickname':p['display_name'],'seat':p['seat']-1,'seat_wind':'ESWN'[p['seat']-1],'user_id':p['user_id'],'is_host':p['user_id']==row['host_id'],'is_ai':False,'ready':bool(p['ready'])} for p in members]
    if len(players)>=2:
        empty=[s for s in range(4) if s not in {p['seat'] for p in players}]
        players += [{'nickname':f'AI {i+1}号','seat':s,'seat_wind':'ESWN'[s],'is_host':False,'is_ai':True,'ready':True} for i,s in enumerate(empty)]
    return {'room_id':room_id,'match_id':room_id,'capacity':len(members),'players':sorted(players,key=lambda p:p['seat']),'human_count':len(members),'status':row['status'],'start_at':row['start_at']}

def membership_snapshot(db, room_id, user_id):
    member_match(db,room_id,user_id)
    result=snapshot(db,room_id)
    seat=db.execute('SELECT seat FROM match_members WHERE match_id=? AND user_id=?',(room_id,user_id)).fetchone()['seat']
    return {**result,'my_seat':seat-1,'user_id':user_id}
