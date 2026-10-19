from io import BytesIO
import json

import pytest
from fastapi.testclient import TestClient

from app.api import app_update
from app.main import app


def release(version, **extra):
    return {"tag_name": version, "assets": [{"name": "app.apk", "browser_download_url": "https://example.test/app.apk", "size": 42}],
            "body": "notes", "html_url": "https://example.test/release", **extra}


@pytest.fixture(autouse=True)
def clear_cache(monkeypatch):
    monkeypatch.setattr(app_update, "_cached", None)
    monkeypatch.setattr(app_update, "_cached_at", 0)


def github(monkeypatch, payload):
    calls = []

    def open_request(request, timeout):
        calls.append((request.full_url, timeout))
        return BytesIO(json.dumps(payload).encode())

    monkeypatch.setattr(app_update, "urlopen", open_request)
    return calls


def test_public_latest_filters_and_sorts_releases(monkeypatch):
    calls = github(monkeypatch, [release("v9.0.0", draft=True), release("v8.0.0", assets=[]),
                                release("v1.2.0"), release("v1.10.0-beta.2", prerelease=True),
                                release("v1.10.0-beta.10", prerelease=True)])
    response = TestClient(app).get("/api/app/latest")
    assert response.status_code == 200
    assert response.json() == dict(version="v1.10.0-beta.10", url="https://example.test/app.apk",
                                   size=42, notes="notes", page="https://example.test/release")
    assert calls == [(app_update.RELEASES_API, 8)]


def test_final_outranks_prerelease_and_invalid_versions(monkeypatch):
    github(monkeypatch, [release("v2.0.0-beta"), release("v2.0.0"), release("latest")])
    assert TestClient(app).get("/api/app/latest").json()["version"] == "v2.0.0"


def test_cache_expires_and_refreshes(monkeypatch):
    clock = [1000]
    monkeypatch.setattr(app_update.time, "monotonic", lambda: clock[0])
    calls = github(monkeypatch, [release("v1.0.0")])
    client = TestClient(app)
    assert client.get("/api/app/latest").status_code == 200
    clock[0] += 599
    assert client.get("/api/app/latest").json()["version"] == "v1.0.0"
    assert len(calls) == 1
    refreshed = github(monkeypatch, [release("v2.0.0")])
    clock[0] += 1
    assert client.get("/api/app/latest").json()["version"] == "v2.0.0"
    assert len(refreshed) == 1


@pytest.mark.parametrize("failure", [OSError("offline"), TimeoutError("timeout"), ValueError("bad JSON")])
def test_failure_returns_503_or_stale_cache(monkeypatch, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(app_update, "urlopen", fail)
    client = TestClient(app)
    assert client.get("/api/app/latest").status_code == 503
    cached = dict(version="v1.0.0", url="https://example.test/app.apk", size=0, notes="", page="")
    monkeypatch.setattr(app_update, "_cached", cached)
    monkeypatch.setattr(app_update, "_cached_at", float("-inf"))
    assert client.get("/api/app/latest").json() == cached


def test_no_apk_is_unavailable(monkeypatch):
    github(monkeypatch, [release("v1.0.0", assets=[])])
    assert TestClient(app).get("/api/app/latest").status_code == 503
