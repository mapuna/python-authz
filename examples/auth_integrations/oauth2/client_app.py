import os
from contextlib import asynccontextmanager

import httpx2
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import RedirectResponse

from authz import (
    Client,
    Direct,
    Namespace,
    PythonCallableEvaluator,
    RelationTuple,
    SqliteStorage,
)
from authz.integrations.fastapi import requires

PROVIDER_URL = os.environ.get("FAKE_PROVIDER_URL", "http://localhost:8001")
CALLBACK_URL = os.environ.get("CLIENT_CALLBACK_URL", "http://localhost:8000/callback")

demo = Namespace("demo", {"member": Direct()})

_http_client: httpx2.AsyncClient | None = None


def get_http_client() -> httpx2.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx2.AsyncClient()
    return _http_client


def set_http_client(client: httpx2.AsyncClient) -> None:
    global _http_client
    _http_client = client


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = SqliteStorage(":memory:")
    await storage.connect()
    client = Client(storage=storage, condition_evaluator=PythonCallableEvaluator())
    client.register_schema(demo)
    # both fake-provider users can reach the protected route once logged
    # in -- same rationale as the JWT recipe's seed step.
    await client.write(
        [
            RelationTuple("demo", "root", "member", "user:alice"),
            RelationTuple("demo", "root", "member", "user:bob"),
        ]
    )
    app.state.authz_client = client
    yield
    await storage.close()


app = FastAPI(title="fastapi-auth recipe: OAuth2 client", lifespan=lifespan)


async def get_authz_client(request: Request) -> Client:
    return request.app.state.authz_client


@app.get("/login")
async def login(state: str = "demo-state"):
    return RedirectResponse(
        f"{PROVIDER_URL}/authorize?client_id=demo&redirect_uri={CALLBACK_URL}&state={state}"
    )


@app.get("/callback")
async def callback(code: str, response: Response):
    http = get_http_client()
    token_resp = await http.post(f"{PROVIDER_URL}/token", params={"code": code})
    if token_resp.status_code != 200:
        raise HTTPException(status_code=400, detail="token exchange failed")
    access_token = token_resp.json()["access_token"]
    response.set_cookie("session_token", access_token, httponly=True)
    return {"message": "logged in"}


async def get_current_user(session_token: str | None = Cookie(default=None)) -> str:
    if not session_token:
        raise HTTPException(status_code=401, detail="not logged in")
    http = get_http_client()
    resp = await http.get(
        f"{PROVIDER_URL}/userinfo",
        headers={"Authorization": f"Bearer {session_token}"},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="invalid session")
    return f"user:{resp.json()['username']}"


@app.get("/whoami")
async def whoami(
    _: None = Depends(
        requires("member", "demo:root",
                 get_client=get_authz_client, get_subject=get_current_user)
    ),
):
    return {"message": "authenticated"}
