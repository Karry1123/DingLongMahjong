import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api import matches
from app.storage.db import connect
from tests.test_rooms import client, visitor, invite_match


class Socket:
    def __init__(self):
        self.messages = []
        self.failed = False
        self.closed = None

    async def send_json(self, message):
        if self.failed:
            raise RuntimeError("transport disconnected")
        self.messages.append(message)

    async def close(self, code=1000):
        self.closed = code


def status(match_id):
    with connect() as db:
        return dict(db.execute("SELECT status,start_at FROM matches WHERE id=?", (match_id,)).fetchone())


def test_duplicate_control_connection_rejected_without_evicting_first(client):
    host, guest = visitor(client), visitor(client)
    match_id = invite_match(client, host, [guest]).json()["match"]["id"]
    path = f"/api/matches/{match_id}/ws"
    with client.websocket_connect(path) as first:
        first.send_json({"type": "authenticate", "token": host["token"]})
        assert first.receive_json()["type"] == "room_state"
        with client.websocket_connect(path) as duplicate:
            duplicate.send_json({"type": "authenticate", "token": host["token"]})
            assert duplicate.receive_json() == {"type": "error", "code": "already_connected"}
            with pytest.raises(WebSocketDisconnect) as closed:
                duplicate.receive_json()
            assert closed.value.code == 4409
        first.send_json({"type": "ping"})
        assert first.receive_json()["type"] == "pong"
        assert host["id"] in matches.rooms_manager.connections[match_id]


def test_disconnect_cancels_countdown_and_reconnect_keeps_membership(client):
    host, guest = visitor(client), visitor(client)
    match_id = invite_match(client, host, [guest]).json()["match"]["id"]
    manager = matches.rooms_manager
    manager.countdown_seconds = 10
    manager.disconnect_seconds = .08

    async def scenario():
        first, second, replacement = Socket(), Socket(), Socket()
        await manager.attach(match_id, host["id"], first)
        await manager.attach(match_id, guest["id"], second)
        await manager.start(match_id, host["id"])
        assert status(match_id)["status"] == "countdown"
        await manager.detach(match_id, guest["id"], second)
        assert status(match_id) == {"status": "waiting", "start_at": None}
        from app.core.invitations import invite
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as locked:
            with connect() as db:
                invite(db, match_id, host['id'], [guest['id']])
        assert locked.value.status_code == 409
        assert (match_id, guest["id"]) in manager.disconnects
        assert match_id not in manager.countdowns
        assert guest["id"] not in manager.connections[match_id]
        with connect() as db:
            assert db.execute("SELECT COUNT(*) AS n FROM match_members WHERE match_id=?", (match_id,)).fetchone()["n"] == 2
        await manager.attach(match_id, guest["id"], replacement)
        assert (match_id, guest["id"]) not in manager.disconnects
        assert replacement.messages[-1]["room"]["my_seat"] == 1
        await manager.detach(match_id, guest["id"], second)
        assert manager.connections[match_id][guest["id"]] is replacement
        await asyncio.sleep(.1)
        assert status(match_id)["status"] == "waiting"
        await manager.leave(match_id, host["id"])
    asyncio.run(scenario())


def test_startup_aborts_active_matches_and_cancels_invitations(client):
    from fastapi.testclient import TestClient
    from app.main import app
    host, guest = visitor(client), visitor(client)
    match = invite_match(client, host, [guest], accept=False).json()['match']
    with TestClient(app) as restarted:
        assert restarted.get('/api/me', headers=host['headers']).json()['active_match_id'] is None
        assert restarted.get('/api/invitations', headers=guest['headers']).json()['items'] == []
    assert status(match['id'])['status'] == 'aborted'


def test_disconnect_timeout_aborts_and_releases_members(client):
    host, guest = visitor(client), visitor(client)
    match_id = invite_match(client, host, [guest]).json()["match"]["id"]
    manager = matches.rooms_manager
    manager.disconnect_seconds = .01

    async def scenario():
        first, second = Socket(), Socket()
        await manager.attach(match_id, host["id"], first)
        await manager.attach(match_id, guest["id"], second)
        with connect() as db:
            db.execute("UPDATE matches SET status='playing' WHERE id=?", (match_id,))
        await manager.detach(match_id, guest["id"], second)
        assert status(match_id)["status"] == "playing"
        await asyncio.sleep(.05)
        assert status(match_id)["status"] == "aborted"
        assert match_id not in manager.connections
        assert first.messages[-1]["type"] == "room_closed"
        assert "disconnect_timeout" in str(first.messages[-1])
    asyncio.run(scenario())
    assert client.get("/api/me", headers=host["headers"]).json()["active_match_id"] is None
    assert client.get("/api/me", headers=guest["headers"]).json()["active_match_id"] is None


def test_failed_broadcast_uses_same_disconnect_grace(client):
    host, guest = visitor(client), visitor(client)
    match_id = invite_match(client, host, [guest]).json()["match"]["id"]
    manager = matches.rooms_manager
    manager.disconnect_seconds = .01

    async def scenario():
        first, second = Socket(), Socket()
        await manager.attach(match_id, host["id"], first)
        await manager.attach(match_id, guest["id"], second)
        second.failed = True
        async with manager.lock:
            await manager._broadcast(match_id)
        assert status(match_id)["status"] == "waiting"
        assert guest["id"] not in manager.connections[match_id]
        assert (match_id, guest["id"]) in manager.disconnects
        assert first.closed is None
        await asyncio.sleep(.05)
        assert status(match_id)["status"] == "aborted"
    asyncio.run(scenario())
