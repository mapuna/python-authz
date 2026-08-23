from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from authz import (
    Client,
    Direct,
    Namespace,
    PythonCallableEvaluator,
    RelationTuple,
    SqliteStorage,
)
from authz.integrations.fastapi import requires

SECRET_KEY = "demo-secret-change-me-this-is-not-a-real-secret-key"  # placeholder; a real deployment reads this from env, >=32 bytes for HS256

FAKE_USERS = {"alice": "password123", "bob": "hunter2"}

demo = Namespace("demo", {"member": Direct()})


@asynccontextmanager
async def lifespan(app: FastAPI):
    storage = SqliteStorage(":memory:")
    await storage.connect()
    client = Client(storage=storage, condition_evaluator=PythonCallableEvaluator())
    client.register_schema(demo)
    # both fake users can reach the protected route once logged in -- this
    # recipe is about proving get_current_user resolves correctly, not
    # about teaching authorization rules again.
    await client.write(
        [
            RelationTuple("demo", "root", "member", "user:alice"),
            RelationTuple("demo", "root", "member", "user:bob"),
        ]
    )
    app.state.authz_client = client
    yield
    await storage.close()


app = FastAPI(title="fastapi-auth recipe: self-issued JWT", lifespan=lifespan)


async def get_authz_client(request: Request) -> Client:
    return request.app.state.authz_client


@app.post("/login")
async def login(username: str, password: str):
    if FAKE_USERS.get(username) != password:
        raise HTTPException(status_code=401, detail="bad credentials")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    token = jwt.encode({"sub": username, "exp": expires_at}, SECRET_KEY, algorithm="HS256")
    return {"access_token": token, "token_type": "bearer"}


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return f"user:{payload['sub']}"


@app.get("/whoami")
async def whoami(
    _: None = Depends(
        requires("member", "demo:root",
                 get_client=get_authz_client, get_subject=get_current_user)
    ),
):
    return {"message": "authenticated"}
