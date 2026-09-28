from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import rooms
from app.core.rooms_manager import RoomsManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ROOM_DB_PATH", str(tmp_path / "rooms.sqlite3"))
    monkeypatch.setattr(rooms, "rooms_manager", RoomsManager())
    return TestClient(app)


def visitor(name="牌友"):
    return {"client_id": str(uuid4()), "nickname": name}


def test_room_flow_membership_capacity_and_exit_dissolves(client):
    host, guest = visitor("房主"), visitor("来客")
    room = client.post("/api/rooms", json={**host, "capacity": 2}).json()
    room_id = room["room_id"]
    assert len(room_id) == 6 and room_id.isdigit()
    assert room["my_seat"] == 0 and room["players"][0]["is_host"]
    assert "client_id" not in room["players"][0]
    path = f"/api/rooms/{room_id}"
    assert client.post(path + "/join", json=guest).status_code == 200
    assert client.post(path + "/join", json=guest).json()["my_seat"] == 1
    assert client.post(path + "/join", json={**host, "nickname": guest["nickname"]}).status_code == 409
    assert client.post(path + "/join", json=visitor("第三人")).status_code == 409
    state = client.post(path + "/state", json=host).json()
    assert state["human_count"] == 2
    assert len(state["players"]) == 4
    assert sum(p["is_ai"] for p in state["players"]) == 2
    assert client.post(path + "/state", json=visitor()).status_code == 403
    assert client.post(path + "/leave", json=host).status_code == 200
    assert client.post(path + "/state", json=guest).status_code == 404
    assert client.post(path + "/leave", json=guest).status_code == 404
    assert client.post(path + "/join", json=host).status_code == 404


@pytest.mark.parametrize("name", ["", "   ", "AI 1号", "aI2号", "来客A I-3号", "ＡＩ４号", "ai四号", "\u200b", "龙" * 7])
def test_server_rechecks_nickname(client, name):
    assert client.post("/api/rooms", json={**visitor(name), "capacity": 4}).status_code == 422


def test_nickname_six_character_boundary_for_create_and_join(client):
    host = visitor("顶龙真人牌友")
    response = client.post("/api/rooms", json={**host, "capacity": 2})
    assert response.status_code == 200
    path = f'/api/rooms/{response.json()["room_id"]}/join'
    assert client.post(path, json=visitor("七字昵称不允许")).status_code == 422
    assert client.post(path, json=visitor("六字真人牌友")).status_code == 200


def test_unique_numbers_retry_collision_and_persist(client, monkeypatch):
    values = iter([123456, 123456, 234567])
    monkeypatch.setattr(rooms.secrets, "randbelow", lambda _: next(values))
    first = client.post("/api/rooms", json={**visitor("甲"), "capacity": 3}).json()
    second = client.post("/api/rooms", json={**visitor("乙"), "capacity": 4}).json()
    assert first["room_id"] == "223456"
    assert second["room_id"] == "334567"
    assert TestClient(app).post(f'/api/rooms/{first["room_id"]}/join', json=visitor("丙")).status_code == 200


def test_concurrent_join_does_not_overfill(client):
    room = client.post("/api/rooms", json={**visitor(), "capacity": 2}).json()
    def join(index):
        return client.post(f'/api/rooms/{room["room_id"]}/join', json=visitor(f"玩家{index}")).status_code
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(join, range(4)))
    assert sorted(results) == [200, 409, 409, 409]


def test_room_and_capacity_errors(client):
    assert client.post("/api/rooms/000000/join", json=visitor()).status_code == 404
    for capacity in [1, 5]:
        assert client.post("/api/rooms", json={**visitor(), "capacity": capacity}).status_code == 422
    host = visitor("相同昵称")
    room = client.post("/api/rooms", json={**host, "capacity": 4}).json()
    assert client.post(f'/api/rooms/{room["room_id"]}/join', json=visitor("相同昵称")).status_code == 409
