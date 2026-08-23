import httpx2
import pytest
from fastapi.testclient import TestClient

from examples.auth_integrations.oauth2 import client_app
from examples.auth_integrations.oauth2.fake_provider import provider_app


@pytest.fixture(autouse=True)
def route_client_to_fake_provider():
    client_app.set_http_client(
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=provider_app),
            base_url=client_app.PROVIDER_URL,
        )
    )
    yield


async def _get_code_via_fake_provider(state: str = "xyz", username: str = "alice") -> str:
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=provider_app)) as http:
        response = await http.get(
            f"{client_app.PROVIDER_URL}/authorize",
            params={
                "client_id": "demo",
                "redirect_uri": client_app.CALLBACK_URL,
                "state": state,
                "username": username,
            },
            follow_redirects=False,
        )
    return response.headers["location"].split("code=")[1].split("&")[0]


def test_login_redirects_to_fake_provider_authorize():
    with TestClient(client_app.app) as client:
        response = client.get("/login", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"].startswith(f"{client_app.PROVIDER_URL}/authorize")


async def test_full_flow_login_callback_whoami_succeeds():
    with TestClient(client_app.app) as client:
        code = await _get_code_via_fake_provider()

        callback_response = client.get(f"/callback?code={code}")
        assert callback_response.status_code == 200
        assert "session_token" in callback_response.cookies

        whoami_response = client.get("/whoami")
        assert whoami_response.status_code == 200


def test_whoami_without_session_returns_401():
    with TestClient(client_app.app) as client:
        response = client.get("/whoami")
        assert response.status_code == 401


def test_whoami_with_invalid_session_returns_401():
    with TestClient(client_app.app) as client:
        client.cookies.set("session_token", "garbage-token")
        response = client.get("/whoami")
        assert response.status_code == 401


def test_callback_with_invalid_code_returns_error():
    with TestClient(client_app.app) as client:
        response = client.get("/callback?code=not-a-real-code")
        assert response.status_code >= 400
