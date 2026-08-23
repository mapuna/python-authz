import secrets

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import RedirectResponse

FAKE_CODES: dict[str, str] = {}
FAKE_TOKENS: dict[str, str] = {}

provider_app = FastAPI(title="fastapi-auth recipe: fake OAuth2 provider")


@provider_app.get("/authorize")
async def authorize(
    client_id: str, redirect_uri: str, state: str, username: str = "alice"
):
    # A real provider would show a login form here; `username` stands in
    # for a user clicking "log in as alice" -- this is a demo stand-in,
    # not something a real authorization server would ever accept as a
    # query parameter.
    code = secrets.token_urlsafe(16)
    FAKE_CODES[code] = username
    return RedirectResponse(f"{redirect_uri}?code={code}&state={state}")


@provider_app.post("/token")
async def token(code: str):
    username = FAKE_CODES.pop(code, None)
    if username is None:
        raise HTTPException(status_code=400, detail="invalid code")
    access_token = secrets.token_urlsafe(24)
    FAKE_TOKENS[access_token] = username
    return {"access_token": access_token, "token_type": "bearer"}


@provider_app.get("/userinfo")
async def userinfo(authorization: str = Header()):
    token_value = authorization.removeprefix("Bearer ")
    username = FAKE_TOKENS.get(token_value)
    if username is None:
        raise HTTPException(status_code=401)
    return {"username": username}
