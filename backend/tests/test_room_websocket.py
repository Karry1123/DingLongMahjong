import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app
from app.api import matches as rooms
from tests.test_rooms import visitor as make_visitor, invite_match
from app.core.rooms_manager import RoomsManager


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("PVP_RECORD_DB_PATH", str(tmp_path / "pvp_records.sqlite3"))
    monkeypatch.setattr(rooms, "rooms_manager", RoomsManager(countdown_seconds=.15))
    with TestClient(app) as client:
        global _client
        _client = client
        yield client


def visitor(name):
    return make_visitor(_client, name)


def create(client, host, capacity=2, guest=None):
    guests = ([guest] if guest else []) + [visitor(f"玩家{i}") for i in range(capacity - 1 - bool(guest))]
    host["guests"] = guests
    return invite_match(client, host, guests).json()["match"]["id"]


def receive_state(socket):
    value = socket.receive_json()
    assert value["type"] == "room_state", value
    return value


def join(socket, person):
    socket.send_json({"type": "authenticate", "token": person["token"]})
    return receive_state(socket)


def test_seats_ready_ai_cancel_and_shared_private_deal(client):
    host, guest = visitor("东家"), visitor("南家")
    room_id = create(client, host, guest=guest)
    with client.websocket_connect(f"/api/matches/{room_id}/ws") as first:
        state = join(first, host)
        assert state["room"]["my_seat"] == 0
        assert len(state["room"]["players"]) == 4
        # Four physical seats exist even in a two-human room.
        first.send_json({"type": "seat", "seat": "N"})
        assert receive_state(first)["room"]["my_seat"] == 3
        with client.websocket_connect(f"/api/matches/{room_id}/ws") as second:
            state = join(second, guest)
            assert state["room"]["my_seat"] == 1
            assert len(state["room"]["players"]) == 4
            assert [p["nickname"] for p in state["room"]["players"] if p["is_ai"]] == ["AI 1号", "AI 2号"]
            assert all(p["ready"] for p in state["room"]["players"] if p["is_ai"])
            receive_state(first)
            second.send_json({"type": "seat", "seat": "W"})
            assert receive_state(second)["room"]["my_seat"] == 2
            assert next(p for p in receive_state(first)["room"]["players"] if p["nickname"] == "南家")["seat_wind"] == "W"
            first.send_json({"type": "seat", "seat": "W"})
            assert first.receive_json()["type"] == "error"
            first.send_json({"type": "ready", "ready": True})
            assert receive_state(first)["room"]["status"] == "waiting"
            assert any(p["ready"] and not p["is_ai"] for p in receive_state(second)["room"]["players"])
            second.send_json({"type": "ready", "ready": True})
            receive_state(first); receive_state(second)
            assert client.post(f"/api/matches/{room_id}/start", headers=host["headers"]).status_code == 200
            one, two = receive_state(first), receive_state(second)
            assert one["room"]["status"] == two["room"]["status"] == "countdown"
            assert one["room"]["start_at"] == two["room"]["start_at"]
            second.send_json({"type": "ready", "ready": False})
            assert receive_state(first)["room"]["status"] == receive_state(second)["room"]["status"] == "waiting"
            assert not rooms.rooms_manager.countdowns
            second.send_json({"type": "ready", "ready": True})
            receive_state(first); receive_state(second)
            started_one, started_two = receive_state(first), receive_state(second)
            assert started_one["room"]["status"] == started_two["room"]["status"] == "playing"
            game_one, game_two = started_one["game"], started_two["game"]
            assert game_one["game_id"] == game_two["game_id"]
            assert game_one["dealer_tile"] == game_two["dealer_tile"]
            assert game_one["seat_wind"] == "N" and game_two["seat_wind"] == "W"
            assert len(game_one["hand_tiles"]) == len(game_two["hand_tiles"]) == 13
            assert game_one["wall_count"] == 82
            assert "hands" not in game_one and "wall_tiles" not in game_one
            assert not any("client_id" in p for p in started_one["room"]["players"])
            first.send_json({"type": "seat", "seat": "E"})
            assert first.receive_json()["type"] == "error"
            second.send_json({"type": "leave"})
            assert first.receive_json()["type"] == second.receive_json()["type"] == "room_closed"
            assert room_id not in rooms.rooms_manager.games


def test_disconnect_grace_cancels_countdown_then_dissolves(client):
    rooms.rooms_manager.countdown_seconds = 10
    rooms.rooms_manager.disconnect_seconds = .08
    host, guest = visitor("房主"), visitor("牌友")
    room_id = create(client, host, guest=guest)
    with client.websocket_connect(f"/api/matches/{room_id}/ws") as first:
        join(first, host)
        with client.websocket_connect(f"/api/matches/{room_id}/ws") as second:
            join(second, guest); receive_state(first)
            assert client.post(f"/api/matches/{room_id}/start", headers=host["headers"]).status_code == 200
            receive_state(first); receive_state(second)
            second.close()
        disconnected = receive_state(first)["room"]
        assert disconnected["status"] == "waiting"
        assert not rooms.rooms_manager.countdowns
        assert not next(p for p in disconnected["players"] if p.get("user_id") == guest["id"])["connected"]
        notification = first.receive_json()
        assert notification["type"] == "room_closed" and notification["code"] == "disconnect_timeout"
    assert not rooms.rooms_manager.connections and not rooms.rooms_manager.countdowns
    assert client.get("/api/me", headers=guest["headers"]).json()["active_match_id"] is None


def test_full_and_duplicate_sockets_do_not_dissolve_room(client):
    host, guest = visitor("房主"), visitor("牌友")
    room_id = create(client, host, guest=guest)
    with client.websocket_connect(f"/api/matches/{room_id}/ws") as first:
        join(first, host)
        with client.websocket_connect(f"/api/matches/{room_id}/ws") as second:
            join(second, guest); receive_state(first)
            for person in [host, visitor("多余玩家")]:
                with client.websocket_connect(f"/api/matches/{room_id}/ws") as rejected:
                    rejected.send_json({"type": "authenticate", "token": person["token"]})
                    if person is host:
                        assert rejected.receive_json()["code"] == "already_connected"
                    with pytest.raises(WebSocketDisconnect):
                        rejected.receive_json()
            first.send_json({"type": "ping"})
            assert first.receive_json()["type"] == "pong"
            first.send_json({"type": "leave"})
            assert first.receive_json()["type"] == "room_closed"


@pytest.mark.parametrize("capacity", [3, 4])
def test_ai_fill_count_for_capacities(client, capacity):
    host = visitor("房主")
    room_id = create(client, host, capacity)
    result = client.get(f"/api/matches/{room_id}", headers=host["headers"]).json()["match"]
    assert len(result["members"]) == capacity
    assert len(result["members"]) + len(result["ai_seats"]) == 4
    assert len(result["ai_seats"]) == 4 - capacity


def test_illegal_protocol_and_origin(client):
    room_id = create(client, visitor("房主"))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/matches/{room_id}/ws", headers={"origin": "https://evil.example"}):
            pass
    with client.websocket_connect(f"/api/matches/{room_id}/ws") as socket:
        socket.send_json({"type": "ready", "ready": True})
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 4401


@pytest.mark.parametrize("origin", ["http://172.20.10.2:5173", "http://192.168.1.25:5181", "http://10.35.246.104:5173", "http://localhost:5181"])
def test_lan_create_join_and_websocket_share_origin_policy(client, origin):
    host, guest = visitor("电脑房主"), visitor("手机牌友")
    created = invite_match(client, host, [guest], origin=origin)
    assert created.status_code == 201 and created.headers["access-control-allow-origin"] == origin
    room_id = created.json()["match"]["id"]
    with client.websocket_connect(f"/api/matches/{room_id}/ws", headers={"Origin":"http://localhost:5173"}) as first:
        join(first, host)
        with client.websocket_connect(f"/api/matches/{room_id}/ws", headers={"Origin":origin}) as second:
            joined = join(second, guest); shared = receive_state(first)
            assert joined["room"]["human_count"] == shared["room"]["human_count"] == 2
            first.send_json({"type":"leave"})
            assert first.receive_json()["type"] == second.receive_json()["type"] == "room_closed"


def test_moving_seat_cancels_own_ready_and_countdown(client):
    rooms.rooms_manager.countdown_seconds = 10
    host, guest = visitor("房主"), visitor("牌友")
    room_id = create(client, host, guest=guest)
    with client.websocket_connect(f"/api/matches/{room_id}/ws") as first:
        join(first, host)
        with client.websocket_connect(f"/api/matches/{room_id}/ws") as second:
            join(second, guest); receive_state(first)
            first.send_json({"type": "ready", "ready": True}); receive_state(first); receive_state(second)
            second.send_json({"type": "ready", "ready": True}); receive_state(first); receive_state(second)
            assert client.post(f"/api/matches/{room_id}/start", headers=host["headers"]).status_code == 200
            receive_state(first); receive_state(second)
            first.send_json({"type": "seat", "seat": "W"})
            state = receive_state(first)["room"]; receive_state(second)
            assert state["status"] == "waiting" and state["my_seat"] == 2
            assert not next(p for p in state["players"] if p["seat"] == 2)["ready"]
            assert not rooms.rooms_manager.countdowns
            first.send_json({"type": "leave"}); first.receive_json(); second.receive_json()


def test_opening_barrier_and_authoritative_live_discard(client):
    rooms.rooms_manager.opening_seconds = .03
    host, guest = visitor("东家"), visitor("南家")
    room_id = create(client, host, guest=guest)
    with client.websocket_connect(f"/api/matches/{room_id}/ws") as first:
        join(first, host)
        with client.websocket_connect(f"/api/matches/{room_id}/ws") as second:
            join(second, guest); receive_state(first)
            first.send_json({"type": "ready", "ready": True}); receive_state(first); receive_state(second)
            second.send_json({"type": "ready", "ready": True}); receive_state(first); receive_state(second)
            assert client.post(f"/api/matches/{room_id}/start", headers=host["headers"]).status_code == 200
            receive_state(first); receive_state(second)
            initial_one, initial_two = receive_state(first), receive_state(second)
            game = initial_one["game"]
            assert game["phase"] == "opening" and not game["actions"]
            first.send_json({"type": "opening_complete", "game_id": game["game_id"]})
            # A second player must explicitly finish their ceremony too.
            first.send_json({"type": "ping"})
            assert first.receive_json()["type"] == "pong"
            assert rooms.rooms_manager.games[room_id].phase == "opening"
            second.send_json({"type": "opening_complete", "game_id": game["game_id"]})
            live_one, live_two = receive_state(first)["game"], receive_state(second)["game"]
            assert live_one["phase"] == live_two["phase"] == "discard"
            assert live_one["current_turn"] == "E" and not live_two["actions"]
            action = next(a for a in live_one["actions"] if a["action_type"] == "discard")
            command = {"type": "game_action", "game_id": live_one["game_id"], "revision": live_one["revision"], "action_id": action["action_id"]}
            second.send_json(command)
            assert second.receive_json()["type"] == "error"
            first.send_json(command)
            updated_one, updated_two = receive_state(first)["game"], receive_state(second)["game"]
            river = next(p for p in updated_two["players"] if p["seat_wind"] == "E")["discards"]
            assert river == [action["tiles"][0]]
            assert updated_one["revision"] == updated_two["revision"]
            first.send_json(command)
            assert first.receive_json()["type"] == "error"
            second.send_json({"type": "leave"}); first.receive_json(); second.receive_json()
    assert not rooms.rooms_manager.game_tasks


def test_server_timer_auto_win_and_all_humans_confirm_exactly_one_next_game(client, monkeypatch):
    import app.core.rooms_manager as manager_module
    from tests.test_pvp_match import custom
    original = manager_module.PvpMatch
    def winning(players, **kwargs):
        match = custom({"E": "1m 1m 1m 2m 3m 4m 3p 4p 5p 6s 7s 8s C C".split()})
        match.players = {p["seat_wind"]: p for p in players}
        match.phase = "opening"
        match.options = {seat: [] for seat in "ESWN"}
        match.clocks = {}
        match.opening_ready = {p["seat_wind"] for p in players if p["is_ai"]}
        match.opening_ends_at = match.now_ms()
        return match
    monkeypatch.setattr(manager_module, "PvpMatch", winning)
    host, guest = visitor("房主"), visitor("牌友")
    room_id = create(client, host, guest=guest)
    with client.websocket_connect(f"/api/matches/{room_id}/ws") as first:
        join(first, host)
        with client.websocket_connect(f"/api/matches/{room_id}/ws") as second:
            join(second, guest); receive_state(first)
            first.send_json({"type":"ready", "ready":True}); receive_state(first); receive_state(second)
            second.send_json({"type":"ready", "ready":True}); receive_state(first); receive_state(second)
            assert client.post(f"/api/matches/{room_id}/start", headers=host["headers"]).status_code == 200
            receive_state(first); receive_state(second)
            game = receive_state(first)["game"]; receive_state(second)
            for socket in [first, second]:
                socket.send_json({"type":"opening_complete", "game_id":game["game_id"]})
            receive_state(first); receive_state(second)
            # Exercise the manager's own polling task rather than issuing a client action.
            rooms.rooms_manager.games[room_id].clocks["E"]["deadline"] = 0
            finished = receive_state(first)["game"]; receive_state(second)
            assert finished["phase"] == "finished" and finished["result"]["win_type"] == "zimo"
            import os, sqlite3, json, zlib
            with sqlite3.connect(os.environ['PVP_RECORD_DB_PATH']) as db:
                row = db.execute('SELECT game_id,payload FROM pvp_game_records').fetchone()
            saved = json.loads(zlib.decompress(row[1]))
            assert row[0] == finished['game_id'] and saved['steps'][-1]['automatic']
            assert saved['final_hands']['E'] and saved['result']['seat_details']['S']['hand_tiles']
            monkeypatch.setattr(manager_module, "PvpMatch", original)
            first.send_json({"type":"next_hand", "game_id":finished["game_id"]})
            waiting = receive_state(first)["game"]; receive_state(second)
            assert waiting["next_ready"] == ["E"] and waiting["game_id"] == finished["game_id"]
            first.send_json({"type":"next_hand", "game_id":finished["game_id"]})
            assert receive_state(first)["game"]["next_ready"] == ["E"]; receive_state(second)
            second.send_json({"type":"next_hand", "game_id":finished["game_id"]})
            one, two = receive_state(first)["game"], receive_state(second)["game"]
            assert one["game_id"] == two["game_id"] != finished["game_id"]
            assert one["phase"] == "opening" and one["hand_number"] == 2 and one["dealer_seat"] == "E"
            assert one["scores"] == two["scores"] == finished["scores"]
            second.send_json({"type":"next_hand", "game_id":finished["game_id"]})
            assert second.receive_json()["type"] == "error"
            second.send_json({"type":"leave"})
            assert "玩家 牌友 退出" in first.receive_json()["message"]
            second.receive_json()
    assert not rooms.rooms_manager.game_tasks and not rooms.rooms_manager.games
    history = client.get('/api/me/match-history', headers=host['headers']).json()
    assert history['next_cursor'] is None
    assert history['items'][0]['match_id'] == room_id
    assert history['items'][0]['hands'] == 1
    assert history['items'][0]['members'][0]['score'] == finished['scores']['E']
    assert len(history['items'][0]['members']) == 2
