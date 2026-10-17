"""Authenticated friend discovery and reciprocal friend requests."""
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.auth import public_user, require_user
from app.storage.db import connect, utcnow

router = APIRouter(prefix="/api", tags=["friends"])


class FriendRequest(BaseModel):
    target_user_id: str


def fail(status, message, code):
    raise HTTPException(status, {"detail": message, "code": code})


def pair(first, second):
    return tuple(sorted((first, second)))


async def changed(user_ids, event="friend_update"):
    from app.api.realtime import notify
    for user_id in set(user_ids):
        await notify(user_id, {"type": event})


@router.get("/users/search")
def search_users(account: str, user=Depends(require_user)):
    with connect() as db:
        target = db.execute("SELECT * FROM users WHERE account_normalized=?", (account.lower(),)).fetchone()
        if target is None:
            return {"items": []}
        relationship = "self" if target["id"] == user["id"] else "none"
        if relationship != "self":
            friendship = db.execute("SELECT * FROM friendships WHERE user_low=? AND user_high=?", pair(user["id"], target["id"])).fetchone()
            if friendship:
                relationship = "friend" if friendship["status"] == "accepted" else (
                    "outgoing" if friendship["requested_by"] == user["id"] else "incoming")
        return {"items": [{**public_user(target), "relationship": relationship}]}


@router.get("/friends")
def list_friends(user=Depends(require_user)):
    from app.api.realtime import online
    with connect() as db:
        friends = db.execute("SELECT u.* FROM friendships f JOIN users u ON "
                             "u.id=CASE WHEN f.user_low=? THEN f.user_high ELSE f.user_low END "
                             "WHERE (f.user_low=? OR f.user_high=?) AND f.status='accepted' "
                             "ORDER BY u.account_normalized", (user["id"], user["id"], user["id"])).fetchall()
        items = []
        for friend in friends:
            active = db.execute("SELECT m.id FROM matches m JOIN match_members mm ON mm.match_id=m.id "
                                "WHERE mm.user_id=? AND m.status IN ('inviting','waiting','countdown','playing')",
                                (friend["id"],)).fetchone()
            items.append({**public_user(friend), "online": online(friend["id"]), "in_match": active is not None})
    return {"items": items}


@router.post("/friend-requests", status_code=201)
async def request_friend(body: FriendRequest, user=Depends(require_user)):
    target_id = body.target_user_id
    if target_id == user["id"]:
        fail(422, "不能添加自己为好友", "cannot_friend_self")
    with connect() as db:
        if db.execute("SELECT id FROM users WHERE id=?", (target_id,)).fetchone() is None:
            fail(404, "用户不存在", "user_not_found")
        low, high = pair(user["id"], target_id)
        existing = db.execute("SELECT * FROM friendships WHERE user_low=? AND user_high=?", (low, high)).fetchone()
        now = utcnow()
        if existing:
            if existing["status"] == "accepted":
                fail(409, "你们已经是好友", "already_friends")
            if existing["requested_by"] == user["id"]:
                fail(409, "好友申请已发送", "request_pending")
            request_id, status = existing["id"], "accepted"
            db.execute("UPDATE friendships SET status='accepted',updated_at=? WHERE id=?", (now, request_id))
        else:
            request_id, status = str(uuid4()), "pending"
            db.execute("INSERT INTO friendships (id,user_low,user_high,requested_by,status,created_at,updated_at) "
                       "VALUES (?,?,?,?,?,?,?)", (request_id, low, high, user["id"], status, now, now))
    await changed([user["id"], target_id], "friend_request" if status == "pending" else "friend_update")
    return {"id": request_id, "status": status}


@router.get("/friend-requests")
def list_requests(user=Depends(require_user)):
    with connect() as db:
        rows = db.execute("SELECT * FROM friendships WHERE status='pending' AND (user_low=? OR user_high=?) "
                          "ORDER BY created_at,id", (user["id"], user["id"])).fetchall()
        result = {"incoming": [], "outgoing": []}
        for row in rows:
            outgoing = row["requested_by"] == user["id"]
            other = row["user_high"] if row["user_low"] == user["id"] else row["user_low"]
            target = db.execute("SELECT * FROM users WHERE id=?", (other,)).fetchone()
            result["outgoing" if outgoing else "incoming"].append({
                "id": row["id"], "to" if outgoing else "from": public_user(target), "created_at": row["created_at"]})
        return result


def visible_request(db, request_id, user_id):
    row = db.execute("SELECT * FROM friendships WHERE id=? AND (user_low=? OR user_high=?)",
                     (request_id, user_id, user_id)).fetchone()
    if row is None:
        fail(404, "好友申请不存在", "request_not_found")
    if row["status"] != "pending":
        fail(409, "好友申请已处理", "request_not_pending")
    return row


@router.post("/friend-requests/{request_id}/accept")
async def accept_request(request_id: str, user=Depends(require_user)):
    with connect() as db:
        row = visible_request(db, request_id, user["id"])
        if row["requested_by"] == user["id"]:
            fail(403, "只能接受收到的好友申请", "request_forbidden")
        db.execute("UPDATE friendships SET status='accepted',updated_at=? WHERE id=?", (utcnow(), request_id))
    await changed([row["user_low"], row["user_high"]])
    return {"id": request_id, "status": "accepted"}


@router.post("/friend-requests/{request_id}/reject", status_code=204)
async def reject_request(request_id: str, user=Depends(require_user)):
    with connect() as db:
        row = visible_request(db, request_id, user["id"])
        db.execute("DELETE FROM friendships WHERE id=?", (request_id,))
    await changed([row["user_low"], row["user_high"]])
    return Response(status_code=204)


@router.delete("/friends/{friend_id}", status_code=204)
async def delete_friend(friend_id: str, user=Depends(require_user)):
    with connect() as db:
        low, high = pair(user["id"], friend_id)
        row = db.execute("SELECT id FROM friendships WHERE user_low=? AND user_high=? AND status='accepted'", (low, high)).fetchone()
        if row is None:
            fail(404, "好友不存在", "friend_not_found")
        db.execute("DELETE FROM friendships WHERE id=?", (row["id"],))
        invitations = db.execute("SELECT id,match_id FROM invitations WHERE status='pending' AND "
                                 "((inviter_id=? AND invitee_id=?) OR (inviter_id=? AND invitee_id=?))",
                                 (user["id"], friend_id, friend_id, user["id"])).fetchall()
        for invitation in invitations:
            db.execute("UPDATE invitations SET status='cancelled',responded_at=? WHERE id=?", (utcnow(), invitation["id"]))
    await changed([user["id"], friend_id])
    from app.api.realtime import notify
    for match_id in {item["match_id"] for item in invitations}:
        for user_id in (user["id"], friend_id):
            await notify(user_id, {"type": "invitation_update", "match_id": match_id})
    return Response(status_code=204)
