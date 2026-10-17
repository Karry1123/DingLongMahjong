"""Legacy room behavior migrated to authenticated friend invitations."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import os
import sqlite3
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import matches
from app.core.rooms_manager import RoomsManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setattr(matches, "rooms_manager", RoomsManager())
    with TestClient(app) as client:
        yield client


def visitor(client, name="牌友"):
    user_id, token = str(uuid4()), str(uuid4())
    account = "u" + uuid4().hex[:15]
    now = datetime.now(timezone.utc)
    with sqlite3.connect(os.environ["AUTH_DB_PATH"]) as db:
        db.execute("INSERT INTO users(id,account,account_normalized,display_name,password_hash,created_at) VALUES(?,?,?,?,?,?)",
                   (user_id, account, account, name, "fixture", now.isoformat()))
        db.execute("INSERT INTO auth_tokens(token_digest,user_id,client_type,expires_at,created_at) VALUES(?,?,?,?,?)",
                   (sha256(token.encode()).hexdigest(), user_id, "web", (now + timedelta(days=1)).isoformat(), now.isoformat()))
    return {"id": user_id, "token": token, "nickname": name, "headers": {"Authorization": f"Bearer {token}"}}


def befriend(first, second):
    now = datetime.now(timezone.utc).isoformat()
    low, high = sorted([first["id"], second["id"]])
    with sqlite3.connect(os.environ["AUTH_DB_PATH"]) as db:
        db.execute("INSERT INTO friendships(id,user_low,user_high,requested_by,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                   (str(uuid4()), low, high, first["id"], "accepted", now, now))


def invite_match(client, host, guests, *, accept=True, origin=None):
    for guest in guests:
        befriend(host, guest)
    headers = {**host["headers"], **({"Origin": origin} if origin else {})}
    response = client.post("/api/matches", json={"invitee_ids": [p["id"] for p in guests]}, headers=headers)
    assert response.status_code == 201, response.text
    match = response.json()["match"]
    if accept:
        for guest in guests:
            invitation = next(i for i in match["invitations"] if i["invitee"]["id"] == guest["id"])
            joined = client.post(f'/api/invitations/{invitation["id"]}/accept', headers=guest["headers"])
            assert joined.status_code == 200, joined.text
    return response


def test_room_flow_membership_capacity_and_exit_dissolves(client):
    host, guest = visitor(client, "房主"), visitor(client, "来客")
    match = invite_match(client, host, [guest]).json()["match"]
    UUID(match["id"])
    path = f'/api/matches/{match["id"]}'
    state = client.get(path, headers=host["headers"]).json()["match"]
    assert state["host_id"] == host["id"] and state["members"][0]["seat"] == 1
    assert len(state["members"]) == 2 and len(state["ai_seats"]) == 2
    assert all("client_id" not in p for p in state["members"])
    assert client.get(path, headers=visitor(client)["headers"]).status_code == 404
    assert client.post(path + "/leave", headers=host["headers"]).status_code == 204
    assert client.get("/api/me", headers=guest["headers"]).json()["active_match_id"] is None
    assert client.post(path + "/start", headers=host["headers"]).status_code in (404, 409)


@pytest.mark.parametrize("name", ["", "   ", "AI 1号", "aI2号", "来客A I-3号", "ＡＩ４号", "ai四号", "\u200b", "龙" * 7])
def test_server_rechecks_nickname(client, name):
    person = visitor(client)
    assert client.patch("/api/me", json={"display_name": name}, headers=person["headers"]).status_code == 422


def test_nickname_six_character_boundary_for_create_and_join(client):
    person = visitor(client)
    assert client.patch("/api/me", json={"display_name": "顶龙真人牌友"}, headers=person["headers"]).status_code == 200
    assert client.patch("/api/me", json={"display_name": "七字昵称不允许"}, headers=person["headers"]).status_code == 422
    assert client.patch("/api/me", json={"display_name": "六字真人牌友"}, headers=person["headers"]).status_code == 200


def test_unique_match_ids_and_persist(client):
    first_host, second_host = visitor(client, "甲"), visitor(client, "丙")
    first = invite_match(client, first_host, [visitor(client, "乙")]).json()["match"]
    second = invite_match(client, second_host, [visitor(client, "丁")]).json()["match"]
    assert first["id"] != second["id"]
    UUID(first["id"]); UUID(second["id"])
    # Identity and membership persist across HTTP client instances.
    persisted = TestClient(app).get(f'/api/matches/{first["id"]}', headers=first_host["headers"])
    assert persisted.status_code == 200
    assert persisted.json()["match"]["id"] == first["id"]
    assert len(persisted.json()["match"]["members"]) == 2


def test_concurrent_accept_does_not_duplicate_or_overfill(client):
    host, guest = visitor(client), visitor(client)
    match = invite_match(client, host, [guest], accept=False).json()["match"]
    invitation = match["invitations"][0]["id"]
    def accept(_):
        return client.post(f"/api/invitations/{invitation}/accept", headers=guest["headers"]).status_code
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(accept, range(4)))
    assert sorted(results) == [200, 409, 409, 409]
    state = client.get(f'/api/matches/{match["id"]}', headers=host["headers"]).json()["match"]
    assert len(state["members"]) == 2
    assert len({p["seat"] for p in state["members"]}) == 2


def test_removed_room_numbers_and_invitation_capacity_errors(client):
    assert client.post("/api/rooms", json={}).status_code == 410
    response = client.get("/api/rooms/000000")
    assert response.status_code == 410 and response.json()["code"] == "rooms_removed"
    host = visitor(client, "相同昵称")
    for invitees in ([], [str(uuid4()) for _ in range(4)]):
        assert client.post("/api/matches", json={"invitee_ids": invitees}, headers=host["headers"]).status_code == 422
    # Nicknames are presentation only; authenticated users may share them.
    same_name = visitor(client, "相同昵称")
    assert invite_match(client, host, [same_name]).status_code == 201
