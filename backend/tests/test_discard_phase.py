from copy import deepcopy

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.test_game_step_api import _base_state_13, _base_state_14


@pytest.mark.parametrize("context", [
    {"current_turn_seat": "S", "current_phase": "DISCARD"},
    {"current_turn_seat": "E", "current_phase": "CALL"},
    {"current_turn_seat": "E", "current_phase": "WAIT"},
    {"current_turn_seat": "E", "current_phase": "DRAW"},
    {"current_turn_seat": "E", "current_phase": "DISCARD", "response_pending": True},
])
def test_off_phase_discard_rejected(context):
    payload = _base_state_14(**context, event={
        "actor_seat": "E", "event_type": "DISCARD", "tile": "4p",
    })
    before = deepcopy(payload)
    response = TestClient(app).post("/api/game/step", json=payload)
    assert response.status_code == 400, response.text
    assert "discard phase" in response.json()["detail"]
    assert payload == before


def test_discard_before_draw_rejected_without_turn_context():
    payload = _base_state_13(event={"actor_seat": "E", "event_type": "DISCARD", "tile": "1m"})
    response = TestClient(app).post("/api/game/step", json=payload)
    assert response.status_code == 400
    assert "discard-ready" in response.json()["detail"]


def test_discard_in_phase_accepted():
    payload = _base_state_14(current_turn_seat="E", current_phase="DISCARD", event={
        "actor_seat": "E", "event_type": "DISCARD", "tile": "4p",
    })
    response = TestClient(app).post("/api/game/step", json=payload)
    assert response.status_code == 200, response.text
    assert len(response.json()["updated_state"]["hand_tiles"]) == 13
