from fastapi.testclient import TestClient

from examples.auth_integrations.jwt.app import app


def test_login_with_valid_credentials_returns_token():
    with TestClient(app) as client:
        response = client.post(
            "/login", params={"username": "alice", "password": "password123"}
        )
        assert response.status_code == 200
        assert "access_token" in response.json()


def test_login_with_invalid_credentials_returns_401():
    with TestClient(app) as client:
        response = client.post(
            "/login", params={"username": "alice", "password": "wrong"}
        )
        assert response.status_code == 401


def test_whoami_with_valid_token_succeeds():
    with TestClient(app) as client:
        login_response = client.post(
            "/login", params={"username": "alice", "password": "password123"}
        )
        token = login_response.json()["access_token"]
        response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200


def test_whoami_without_token_returns_401():
    with TestClient(app) as client:
        response = client.get("/whoami")
        assert response.status_code == 401


def test_whoami_with_invalid_token_returns_401():
    with TestClient(app) as client:
        response = client.get("/whoami", headers={"Authorization": "Bearer garbage"})
        assert response.status_code == 401
