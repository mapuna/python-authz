from fastapi.testclient import TestClient

from examples.auth_integrations.oauth2.fake_provider import provider_app


def _get_code(client: TestClient, username: str = "alice") -> str:
    response = client.get(
        "/authorize",
        params={
            "client_id": "demo",
            "redirect_uri": "http://localhost:8000/callback",
            "state": "xyz",
            "username": username,
        },
        follow_redirects=False,
    )
    location = response.headers["location"]
    return location.split("code=")[1].split("&")[0]


def test_authorize_redirects_with_code_and_state():
    client = TestClient(provider_app)
    response = client.get(
        "/authorize",
        params={
            "client_id": "demo",
            "redirect_uri": "http://localhost:8000/callback",
            "state": "xyz",
        },
        follow_redirects=False,
    )
    assert response.status_code == 307
    assert "code=" in response.headers["location"]
    assert "state=xyz" in response.headers["location"]


def test_token_exchange_with_valid_code_returns_access_token():
    client = TestClient(provider_app)
    code = _get_code(client)
    response = client.post("/token", params={"code": code})
    assert response.status_code == 200
    assert "access_token" in response.json()


def test_token_exchange_with_invalid_code_returns_400():
    client = TestClient(provider_app)
    response = client.post("/token", params={"code": "not-a-real-code"})
    assert response.status_code == 400


def test_token_exchange_consumes_the_code():
    client = TestClient(provider_app)
    code = _get_code(client)
    first = client.post("/token", params={"code": code})
    assert first.status_code == 200
    second = client.post("/token", params={"code": code})
    assert second.status_code == 400


def test_userinfo_with_valid_token_returns_username():
    client = TestClient(provider_app)
    code = _get_code(client, username="bob")
    token_response = client.post("/token", params={"code": code})
    access_token = token_response.json()["access_token"]
    response = client.get("/userinfo", headers={"Authorization": f"Bearer {access_token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "bob"


def test_userinfo_with_invalid_token_returns_401():
    client = TestClient(provider_app)
    response = client.get("/userinfo", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401
