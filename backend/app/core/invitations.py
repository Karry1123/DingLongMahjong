"""Transactional friend invitation operations."""
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from app.storage.db import utcnow
from app.auth import fail
from app.core.match_repository import active_match, member_match, expire

def are_friends(db,a,b):
    low,high=sorted((a,b))
    return db.execute("SELECT id FROM friendships WHERE user_low=? AND user_high=? AND status='accepted'",(low,high)).fetchone() is not None

def invite(db, match_id, host, ids):
    row=member_match(db,match_id,host)
    if row['host_id']!=host: fail(403,'host_required','仅房主可以邀请')
    if row['status'] not in ('inviting','waiting'): fail(409,'roster_locked','对局名单已锁定')
    # A cancelled countdown stays locked until this match ends.
    from app.api.matches import rooms_manager
    if match_id in rooms_manager.roster_locked: fail(409,'roster_locked','对局名单已锁定')
    expire(db)
    for target in ids:
        if target==host or not are_friends(db,host,target): fail(403,'friend_required','只能邀请已添加的好友')
        if db.execute('SELECT user_id FROM match_members WHERE match_id=? AND user_id=?',(match_id,target)).fetchone(): fail(409,'already_member','好友已经入席')
        if db.execute("SELECT id FROM invitations WHERE match_id=? AND invitee_id=? AND status='pending'",(match_id,target)).fetchone(): continue
        db.execute("INSERT INTO invitations(id,match_id,inviter_id,invitee_id,status,expires_at,created_at) VALUES(?,?,?,?,'pending',?,?)",(str(uuid4()),match_id,host,target,(datetime.now(timezone.utc)+timedelta(seconds=120)).isoformat(),utcnow()))

def invitation(db, invitation_id, user_id):
    expire(db)
    row=db.execute('SELECT * FROM invitations WHERE id=? AND invitee_id=?',(invitation_id,user_id)).fetchone()
    if not row: fail(404,'invitation_not_found','邀请不存在')
    if row['status']!='pending': fail(409,'invitation_unavailable','邀请已失效或已处理')
    return row

def accept(db, invitation_id, user_id):
    row=invitation(db,invitation_id,user_id)
    match=member_match(db,row['match_id'])
    if match['status'] not in ('inviting','waiting'): fail(409,'roster_locked','对局名单已锁定')
    from app.api.matches import rooms_manager
    if match['id'] in rooms_manager.roster_locked: fail(409,'roster_locked','对局名单已锁定')
    if not are_friends(db,row['inviter_id'],user_id): fail(403,'friend_required','好友关系已解除')
    if active_match(db,user_id): fail(409,'already_in_match','你已在其他对局中')
    seats={p['seat'] for p in db.execute('SELECT seat FROM match_members WHERE match_id=?',(match['id'],)).fetchall()}
    if len(seats)>=4: fail(409,'match_full','对局已满')
    seat=next(s for s in range(1,5) if s not in seats)
    db.execute('INSERT INTO match_members(match_id,user_id,seat,ready,joined_at) VALUES(?,?,?,1,?)',(match['id'],user_id,seat,utcnow()))
    db.execute("UPDATE invitations SET status='accepted',responded_at=? WHERE id=?",(utcnow(),invitation_id))
    db.execute("UPDATE matches SET status='waiting',updated_at=? WHERE id=?",(utcnow(),match['id']))
    return match['id']
