from fastapi.testclient import TestClient

from app.main import _parse_allowed_origins, app


def test_health_and_vercel_cors():
    client = TestClient(app)
    assert client.get("/health").json() == {"status": "ok"}

    headers = {
        "Origin": "https://mahjong-preview-123.vercel.app",
        "Access-Control-Request-Method": "POST",
    }
    response = client.options("/api/recommend", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == headers["Origin"]

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
