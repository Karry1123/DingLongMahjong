from io import BytesIO
import json
from types import SimpleNamespace
from urllib.error import HTTPError

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
    monkeypatch.setattr(app_update, "_failed_at", None)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def offline(*args, **kwargs):
        raise OSError("offline")

    monkeypatch.setattr(app_update, "urlopen", offline)
    monkeypatch.setattr(app_update, "build_opener", lambda *args: SimpleNamespace(open=offline))


def github(monkeypatch, payload):
    calls = []

    def open_request(request, timeout):
        if request.full_url.endswith("-update.json"):
            raise OSError("no manifest")
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
                                   size=42, notes="notes", page="https://example.test/release", nativeBuild=None)
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


def redirect(monkeypatch, location, status=302):
    calls = []

    def open_request(request, timeout):
        calls.append((request.full_url, request.get_method(), timeout))
        raise HTTPError(request.full_url, status, "redirect", {"Location": location}, BytesIO())

    def opener(handler):
        assert isinstance(handler, app_update._NoRedirect)
        assert handler.redirect_request(None, None, 302, "redirect", {}, location) is None
        return SimpleNamespace(open=open_request)

    monkeypatch.setattr(app_update, "build_opener", opener)
    return calls


def test_redirect_parses_tag_and_head_size(monkeypatch):
    page = f"{app_update.RELEASES_PAGE}/tag/v0.4.3-beta"
    redirects = redirect(monkeypatch, page)
    calls = []

    def head(request, timeout):
        if request.full_url.endswith("-update.json"):
            raise OSError("no manifest")
        calls.append((request.full_url, request.get_method(), timeout))
        response = BytesIO()
        response.headers = {"Content-Length": "123456"}
        return response

    monkeypatch.setattr(app_update, "urlopen", head)
    expected_url = f"{app_update.RELEASES_PAGE}/download/v0.4.3-beta/DingLongMahjong-v0.4.3-beta.apk"
    assert app_update.latest() == dict(version="v0.4.3-beta", url=expected_url,
                                       size=123456, notes="", page=page, nativeBuild=None)
    assert redirects == [(f"{app_update.RELEASES_PAGE}/latest", "GET", 8)]
    assert calls == [(expected_url, "HEAD", 8)]


@pytest.mark.parametrize("length", [None, "invalid", "-1"])
def test_head_missing_or_invalid_size_is_zero(monkeypatch, length):
    redirect(monkeypatch, "/Karry1123/DingLongMahjong/releases/tag/v0.4.3-beta")

    def head(request, timeout):
        assert request.get_method() == "HEAD"
        response = BytesIO()
        response.headers = {} if length is None else {"Content-Length": length}
        return response

    monkeypatch.setattr(app_update, "urlopen", head)
    assert app_update.latest()["size"] == 0


def test_head_failure_is_zero_and_logs_status(monkeypatch, caplog):
    redirect(monkeypatch, f"{app_update.RELEASES_PAGE}/tag/v0.4.3-beta")

    def head(request, timeout):
        assert request.get_method() == "HEAD"
        raise HTTPError(request.full_url, 404, "Not Found", {}, None)

    monkeypatch.setattr(app_update, "urlopen", head)
    assert app_update.latest()["size"] == 0
    assert "HTTP status 404" in caplog.text


@pytest.mark.parametrize("location", ["", "https://example.test/releases/tag/v1.0.0",
                                      f"{app_update.RELEASES_PAGE}/tag/latest"])
def test_invalid_redirect_falls_back_to_api(monkeypatch, location):
    redirect(monkeypatch, location)
    calls = github(monkeypatch, [release("v1.0.0")])
    assert app_update.latest()["version"] == "v1.0.0"
    assert calls == [(app_update.RELEASES_API, 8)]


def test_token_api_precedes_redirect(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    calls = []

    def api(request, timeout):
        if request.full_url.endswith("-update.json"):
            raise OSError("no manifest")
        calls.append(request)
        assert request.full_url == app_update.RELEASES_API
        assert request.get_header("Authorization") == "Bearer test-token"
        return BytesIO(json.dumps([release("v0.4.3-beta")]).encode())

    def unexpected_redirect(*args):
        pytest.fail("Token API succeeded; redirect must not run")

    monkeypatch.setattr(app_update, "urlopen", api)
    monkeypatch.setattr(app_update, "build_opener", unexpected_redirect)
    assert app_update.latest()["version"] == "v0.4.3-beta"
    assert len(calls) == 1


def test_token_failure_falls_back_to_redirect(monkeypatch, caplog):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    redirects = redirect(monkeypatch, f"{app_update.RELEASES_PAGE}/tag/v0.4.3-beta")
    calls = []

    def open_request(request, timeout):
        if request.full_url.endswith("-update.json"):
            raise OSError("no manifest")
        calls.append(request)
        if request.full_url == app_update.RELEASES_API:
            assert request.get_header("Authorization") == "Bearer test-token"
            raise HTTPError(request.full_url, 403, "Forbidden", {}, None)
        assert request.get_method() == "HEAD"
        assert request.get_header("Authorization") is None
        response = BytesIO()
        response.headers = {"Content-Length": "42"}
        return response

    monkeypatch.setattr(app_update, "urlopen", open_request)
    assert app_update.latest()["size"] == 42
    assert len(redirects) == 1
    assert len(calls) == 2
    assert "HTTP status 403" in caplog.text


def test_all_sources_fail_then_unauthenticated_api(monkeypatch, caplog):
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    redirects = redirect(monkeypatch, "", status=429)
    calls = []

    def api(request, timeout):
        calls.append(request.get_header("Authorization"))
        raise HTTPError(request.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(app_update, "urlopen", api)
    response = TestClient(app).get("/api/app/latest")
    assert response.status_code == 503
    assert response.json() == {"detail": "更新服务暂不可用，请稍后重试"}
    assert calls == ["Bearer test-token", None]
    assert len(redirects) == 1
    assert "HTTP status 403" in caplog.text
    assert "HTTP status 429" in caplog.text


@pytest.mark.parametrize("stale", [False, True])
def test_negative_cache_expires_and_recovers(monkeypatch, stale):
    clock = [1000]
    monkeypatch.setattr(app_update.time, "monotonic", lambda: clock[0])
    cached = dict(version="v0.4.2", url="old.apk", size=0, notes="", page="")
    if stale:
        monkeypatch.setattr(app_update, "_cached", cached)
    redirects = redirect(monkeypatch, "", status=503)
    calls = []

    def api(request, timeout):
        calls.append(request.full_url)
        raise OSError("offline")

    monkeypatch.setattr(app_update, "urlopen", api)
    client = TestClient(app)
    for seconds in (0, 59):
        clock[0] = 1000 + seconds
        response = client.get("/api/app/latest")
        assert response.status_code == (200 if stale else 503)
        if stale:
            assert response.json() == cached
    assert len(calls) == len(redirects) == 1
    recovered = github(monkeypatch, [release("v0.4.3-beta")])
    clock[0] = 1060
    assert client.get("/api/app/latest").json()["version"] == "v0.4.3-beta"
    assert len(recovered) == 1
    assert len(redirects) == 2
    assert app_update._failed_at is None


def manifest_fixture(monkeypatch, **changes):
    info = dict(version="v1.2.3", url="old.apk", size=42, notes="notes", page="page")
    monkeypatch.setattr(app_update, "_fetch_latest_base", lambda: dict(info))
    base = f"{app_update.RELEASES_PAGE}/download/v1.2.3/DingLongMahjong-v1.2.3"
    manifest = dict(version="v1.2.3", nativeBuild=1, bundleUrl=f"{base}-web.zip",
                    bundleSha256="A" * 64, apkUrl=f"{base}.apk", apkSize=1234)
    manifest.update(changes)
    calls = []

    def download(request, timeout):
        assert request.full_url == f"{base}-update.json"
        assert "api.github.com" not in request.full_url
        calls.append(request.full_url)
        return BytesIO(json.dumps(manifest).encode())

    monkeypatch.setattr(app_update, "urlopen", download)
    return info, manifest, calls


def test_manifest_enriches_latest_and_is_cached(monkeypatch):
    _, manifest, calls = manifest_fixture(monkeypatch)
    client = TestClient(app)
    result = client.get("/api/app/latest").json()
    assert result == dict(version="v1.2.3", url=manifest["apkUrl"], size=1234, notes="notes", page="page",
                          nativeBuild=1, bundleUrl=manifest["bundleUrl"], bundleSha256="a" * 64)
    assert client.get("/api/app/latest").json() == result
    assert len(calls) == 1


@pytest.mark.parametrize("changes", [dict(version="v1.2.4"), dict(nativeBuild=True), dict(nativeBuild=None),
                                     dict(nativeBuild=0), dict(bundleSha256="bad"), dict(bundleUrl="https://evil.test/a.zip"),
                                     dict(apkUrl="http://example.test/app.apk"), dict(apkSize=-1)])
def test_invalid_manifest_keeps_apk_fallback(monkeypatch, changes):
    info, _, _ = manifest_fixture(monkeypatch, **changes)
    assert app_update.latest() == dict(info, nativeBuild=None)


@pytest.mark.parametrize("payload", [b"not json", b"[]", b"null"])
def test_malformed_manifest_keeps_apk_fallback(monkeypatch, payload):
    info, _, _ = manifest_fixture(monkeypatch)
    monkeypatch.setattr(app_update, "urlopen", lambda *args, **kwargs: BytesIO(payload))
    assert app_update.latest() == dict(info, nativeBuild=None)


def test_missing_manifest_keeps_apk_fallback(monkeypatch):
    info, _, _ = manifest_fixture(monkeypatch)
    def missing(*args, **kwargs):
        raise HTTPError("manifest", 404, "missing", {}, None)
    monkeypatch.setattr(app_update, "urlopen", missing)
    assert app_update.latest() == dict(info, nativeBuild=None)
