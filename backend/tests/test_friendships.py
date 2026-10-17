from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.auth import issue_token
from app.main import app
from app.storage.db import connect, ensure_schema, utcnow


@pytest.fixture
def social(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "friends.sqlite3"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    ensure_schema()
    users = []
    with TestClient(app) as client:
        for index in range(3):
            user = {"id": str(uuid4()), "account": f"friend{index}", "display_name": f"牌友{index}"}
            with connect() as db:
                db.execute("INSERT INTO users (id,account,account_normalized,display_name,password_hash,created_at) VALUES (?,?,?,?,?,?)",
                           (user["id"], user["account"], user["account"], user["display_name"], "unused", utcnow()))
                data = issue_token(db, user)
            users.append((data["user"], {"Authorization": f'Bearer {data["token"]}'}))
        yield client, users


def request(client, source, target):
    return client.post("/api/friend-requests", headers=source[1], json={"target_user_id": target[0]["id"]})


def test_realtime_authentication_presence_and_hints(social):
    from app.api.realtime import online
    from starlette.websockets import WebSocketDisconnect
    client, (alice, bob, _) = social
    with client.websocket_connect('/api/realtime/ws') as invalid:
        invalid.send_json({'type':'authenticate','token':'invalid'})
        with pytest.raises(WebSocketDisconnect) as closed:
            invalid.receive_json()
        assert closed.value.code == 4401
    with client.websocket_connect('/api/realtime/ws') as socket:
        socket.send_json({'type':'authenticate','token':bob[1]['Authorization'].split()[1]})
        assert socket.receive_json() == {'type':'authenticated','user_id':bob[0]['id']}
        assert online(bob[0]['id'])
        socket.send_json({'type':'ping'})
        assert socket.receive_json() == {'type':'pong'}
        created = request(client,alice,bob)
        assert socket.receive_json() == {'type':'friend_request'}
        assert client.post(f'/api/friend-requests/{created.json()["id"]}/accept',headers=bob[1]).status_code == 200
        assert socket.receive_json() == {'type':'friend_update'}
        assert client.get('/api/friends',headers=alice[1]).json()['items'][0]['online'] is True
    assert not online(bob[0]['id'])


def test_search_and_friend_request_acceptance(social):
    client, (alice, bob, carol) = social
    assert client.get("/api/friends").status_code == 401
    assert client.get("/api/users/search?account=friend", headers=alice[1]).json() == {"items": []}
    self_result = client.get("/api/users/search?account=FRIEND0", headers=alice[1]).json()["items"]
    assert self_result == [{**alice[0], "relationship": "self"}]
    created = request(client, alice, bob)
    assert created.status_code == 201
    request_id = created.json()["id"]
    assert created.json()["status"] == "pending"
    assert request(client, alice, bob).status_code == 409
    assert client.get("/api/users/search?account=friend1", headers=alice[1]).json()["items"][0]["relationship"] == "outgoing"
    assert client.get("/api/users/search?account=friend0", headers=bob[1]).json()["items"][0]["relationship"] == "incoming"
    outgoing = client.get("/api/friend-requests", headers=alice[1]).json()
    incoming = client.get("/api/friend-requests", headers=bob[1]).json()
    assert outgoing["incoming"] == [] and outgoing["outgoing"][0]["to"] == bob[0]
    assert incoming["outgoing"] == [] and incoming["incoming"][0]["from"] == alice[0]
    assert incoming["incoming"][0]["created_at"]
    assert client.post(f"/api/friend-requests/{request_id}/accept", headers=carol[1]).status_code == 404
    assert client.post(f"/api/friend-requests/{request_id}/accept", headers=alice[1]).status_code == 403
    assert client.post(f"/api/friend-requests/{request_id}/accept", headers=bob[1]).json() == {"id": request_id, "status": "accepted"}
    assert client.get("/api/friends", headers=alice[1]).json() == {"items": [{**bob[0], "online": False, "in_match": False}]}
    assert client.get("/api/friends", headers=bob[1]).json()["items"][0]["id"] == alice[0]["id"]
    assert client.get("/api/users/search?account=friend1", headers=alice[1]).json()["items"][0]["relationship"] == "friend"
    assert client.get("/api/friend-requests", headers=alice[1]).json() == {"incoming": [], "outgoing": []}
    assert request(client, alice, bob).status_code == 409


def test_inverse_request_reject_and_withdraw(social):
    client, (alice, bob, carol) = social
    assert request(client, alice, alice).status_code == 422
    assert client.post("/api/friend-requests", headers=alice[1], json={"target_user_id": str(uuid4())}).status_code == 404
    initial = request(client, alice, bob).json()
    reciprocal = request(client, bob, alice)
    assert reciprocal.status_code == 201
    assert reciprocal.json() == {"id": initial["id"], "status": "accepted"}
    for responder in (alice, carol):
        pending = request(client, alice, carol).json()
        assert client.post(f'/api/friend-requests/{pending["id"]}/reject', headers=bob[1]).status_code == 404
        assert client.post(f'/api/friend-requests/{pending["id"]}/reject', headers=responder[1]).status_code == 204
        assert client.get("/api/friend-requests", headers=carol[1]).json()["incoming"] == []
    assert client.delete(f'/api/friends/{bob[0]["id"]}', headers=alice[1]).status_code == 204
    assert client.get("/api/friends", headers=bob[1]).json() == {"items": []}
    assert client.delete(f'/api/friends/{bob[0]["id"]}', headers=alice[1]).status_code == 404


def test_delete_cancels_both_directions_of_pending_invitations(social):
    client, (alice, bob, _) = social
    request(client, alice, bob)
    request(client, bob, alice)
    now, match_id = utcnow(), str(uuid4())
    with connect() as db:
        db.execute("INSERT INTO matches (id,host_id,status,created_at,updated_at) VALUES (?,?,'inviting',?,?)",
                   (match_id, alice[0]["id"], now, now))
        for index, (source, target) in enumerate(((alice, bob), (bob, alice), (alice, bob))):
            db.execute("INSERT INTO invitations (id,match_id,inviter_id,invitee_id,status,expires_at,created_at) VALUES (?,?,?,?,?,?,?)",
                       (str(uuid4()), match_id, source[0]["id"], target[0]["id"], "accepted" if index == 2 else "pending",
                        "2099-01-01T00:00:00+00:00", now))
    assert client.delete(f'/api/friends/{bob[0]["id"]}', headers=alice[1]).status_code == 204
    with connect() as db:
        statuses = [row["status"] for row in db.execute("SELECT status FROM invitations WHERE match_id=?", (match_id,)).fetchall()]
    assert sorted(statuses) == ["accepted", "cancelled", "cancelled"]
