from fastapi.testclient import TestClient

from app.main import _parse_allowed_origins, app
from app.core.origins import is_local_origin


def test_health_and_vercel_cors():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}

    for origin in (
        "https://ding-long-mahjong.vercel.app",
        "https://mahjong-preview-123.vercel.app",
        "https://karry1123.github.io",
    ):
        headers = {
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        }
        for path in ("/api/recommend", "/api/game/auto-deal"):
            response = client.options(path, headers=headers)
            assert response.status_code == 200
            assert response.headers["access-control-allow-origin"] == origin

    denied = client.options("/api/recommend", headers={
        **headers, "Origin": "https://mahjong.vercel.app.evil.example",
    })
    assert denied.status_code == 400


def test_allowed_origins_env_is_trimmed_and_deduplicated():
    origins = _parse_allowed_origins(
        " https://mahjong.example.com/ , https://other.example.com,"
        "https://mahjong.example.com, ,"
    )
    assert origins.count("https://mahjong.example.com") == 1
    assert "https://other.example.com" in origins
    assert "http://localhost:5173" in origins


def test_lan_cors_and_valid_origin_boundaries():
    client = TestClient(app)
    for origin in ("http://172.20.10.2:5173", "http://192.168.1.25:5181", "http://10.35.246.104:5173", "https://[fd00::1]:5173", "http://localhost:5181"):
        assert is_local_origin(origin)
        response = client.options("/api/rooms", headers={"Origin":origin,"Access-Control-Request-Method":"POST","Access-Control-Request-Headers":"content-type"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == origin
    for origin in ("http://172.32.0.1:5173", "http://192.168.1.25.evil.example:5173", "http://10.999.1.1:5173", "http://10.1.1.1:99999", "http://user@10.1.1.1:5173", "http://10.1.1.1:5173/path", "https://evil.example", "null"):
        assert not is_local_origin(origin)
        response = client.options("/api/rooms", headers={"Origin":origin,"Access-Control-Request-Method":"POST"})
        assert response.status_code == 400
