from fastapi.testclient import TestClient

from app.main import _parse_allowed_origins, app


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
