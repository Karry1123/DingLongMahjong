from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from starlette.websockets import WebSocketDisconnect

from app.storage.db import connect
from tests.test_rooms import client, visitor, invite_match, befriend


@pytest.mark.parametrize("humans", [2, 3, 4])
def test_human_counts_and_ai_seats(client, humans):
    host = visitor(client)
    guests = [visitor(client) for _ in range(humans - 1)]
    match = invite_match(client, host, guests).json()["match"]
    match = client.get(f'/api/matches/{match["id"]}', headers=host["headers"]).json()["match"]
    assert len(match["members"]) == humans
    assert len(match["ai_seats"]) == 4 - humans
    assert [member["seat"] for member in match["members"]] == list(range(1, humans + 1))
    assert all(member["ready"] for member in match["members"])
    assert set(match["ai_seats"]) == set(range(humans + 1, 5))


def test_access_friendship_busy_and_guessed_match(client):
    host, guest, outsider = [visitor(client) for _ in range(3)]
    assert client.post("/api/matches", headers=host["headers"], json={"invitee_ids": [guest["id"]]}).status_code == 403
    match = invite_match(client, host, [guest]).json()["match"]
    path = f'/api/matches/{match["id"]}'
    assert client.post("/api/matches", headers=host["headers"], json={"invitee_ids": [guest["id"]]}).status_code == 409
    assert client.get(path, headers=outsider["headers"]).status_code == 404
    assert client.get(f'/api/matches/{uuid4()}', headers=outsider["headers"]).status_code == 404
    with client.websocket_connect(path + "/ws") as socket:
        socket.send_json({"type": "authenticate", "token": outsider["token"]})
        with pytest.raises(WebSocketDisconnect) as closed:
            socket.receive_json()
        assert closed.value.code == 4403
    another = visitor(client)
    befriend(outsider, guest)
    other = client.post("/api/matches", headers=outsider["headers"], json={"invitee_ids": [guest["id"]]}).json()["match"]
    invitation = other["invitations"][0]
    assert client.post(f'/api/invitations/{invitation["id"]}/accept', headers=guest["headers"]).status_code == 409
    assert client.post(f'/api/invitations/{invitation["id"]}/accept', headers=another["headers"]).status_code == 404


def test_host_start_locks_roster_and_cancels_pending(client):
    host, joined, pending = [visitor(client) for _ in range(3)]
    match = invite_match(client, host, [joined, pending], accept=False).json()["match"]
    path = f'/api/matches/{match["id"]}'
    assert client.post(path + "/start", headers=host["headers"]).status_code == 409
    invitations = {entry["invitee"]["id"]: entry["id"] for entry in match["invitations"]}
    assert client.post(f'/api/invitations/{invitations[joined["id"]]}/accept', headers=joined["headers"]).status_code == 200
    assert client.post(path + "/start", headers=joined["headers"]).status_code == 403
    started = client.post(path + "/start", headers=host["headers"])
    assert started.status_code == 200, started.text
    assert started.json()["match"]["status"] == "countdown"
    assert started.json()["match"]["start_at"] > started.json()["match"]["server_time"]
    assert client.post(f'/api/invitations/{invitations[pending["id"]]}/accept', headers=pending["headers"]).status_code == 409
    assert client.post(path + "/invitations", headers=host["headers"], json={"invitee_ids": [pending["id"]]}).status_code == 409
    with connect() as db:
        assert db.execute("SELECT status FROM invitations WHERE id=?", (invitations[pending["id"]],)).fetchone()["status"] == "cancelled"


def test_concurrent_accepts_never_overfill(client):
    host = visitor(client)
    guests = [visitor(client) for _ in range(5)]
    match = invite_match(client, host, guests[:3], accept=False).json()["match"]
    for guest in guests[3:]:
        befriend(host, guest)
    assert client.post(f'/api/matches/{match["id"]}/invitations', headers=host["headers"],
                       json={"invitee_ids": [guest["id"] for guest in guests[3:]]}).status_code == 200
    match = client.get(f'/api/matches/{match["id"]}', headers=host["headers"]).json()["match"]
    ids = {entry["invitee"]["id"]: entry["id"] for entry in match["invitations"]}
    def accept(guest):
        return client.post(f'/api/invitations/{ids[guest["id"]]}/accept', headers=guest["headers"]).status_code
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(accept, guests))
    assert sorted(results) == [200, 200, 200, 409, 409]
    members = client.get(f'/api/matches/{match["id"]}', headers=host["headers"]).json()["match"]["members"]
    assert sorted(member["seat"] for member in members) == [1, 2, 3, 4]


def test_lazy_expiration_and_decline(client):
    host, guest, second = [visitor(client) for _ in range(3)]
    match = invite_match(client, host, [guest, second], accept=False).json()["match"]
    ids = {entry["invitee"]["id"]: entry["id"] for entry in match["invitations"]}
    with connect() as db:
        db.execute("UPDATE invitations SET expires_at=? WHERE id=?", ("2000-01-01T00:00:00+00:00", ids[guest["id"]]))
    assert client.get("/api/invitations", headers=guest["headers"]).json() == {"items": []}
    with connect() as db:
        assert db.execute("SELECT status FROM invitations WHERE id=?", (ids[guest["id"]],)).fetchone()["status"] == "expired"
    assert client.post(f'/api/invitations/{ids[guest["id"]]}/accept', headers=guest["headers"]).status_code == 409
    pending = client.get("/api/invitations", headers=second["headers"]).json()["items"]
    assert pending[0]["members_count"] == 1 and pending[0]["inviter"]["id"] == host["id"]
    assert client.post(f'/api/invitations/{ids[second["id"]]}/decline', headers=second["headers"]).status_code == 204
    assert client.get("/api/invitations", headers=second["headers"]).json() == {"items": []}


def test_history_cursor_handles_equal_timestamps_and_member_visibility(client):
    host, guest, outsider = [visitor(client) for _ in range(3)]
    first = invite_match(client, host, [guest]).json()['match']['id']
    assert client.post(f'/api/matches/{first}/leave',headers=host['headers']).status_code == 204
    second = client.post('/api/matches',headers=host['headers'],json={'invitee_ids':[guest['id']]}).json()['match']['id']
    assert client.post(f'/api/matches/{second}/leave',headers=host['headers']).status_code == 204
    with connect() as db:
        db.execute("UPDATE matches SET updated_at='2026-01-01T00:00:00+00:00'")
    page = client.get('/api/me/match-history?limit=1',headers=host['headers']).json()
    assert len(page['items']) == 1 and page['next_cursor']
    next_page = client.get('/api/me/match-history',params={'limit':1,'cursor':page['next_cursor']},headers=host['headers']).json()
    assert next_page['next_cursor'] is None
    assert {page['items'][0]['match_id'],next_page['items'][0]['match_id']} == {first,second}
    assert client.get('/api/me/match-history',headers=outsider['headers']).json()['items'] == []
    assert client.get('/api/me/match-history?cursor=invalid',headers=host['headers']).status_code == 422
