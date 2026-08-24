# Recipe: OAuth2 Authorization Code Flow

A real OAuth2 flow always involves two parties, so this recipe is two
apps: your app (the "client") and an authorization server (the
"provider"). `fake_provider.py` is a small stand-in authorization server
(`/authorize`, `/token`, `/userinfo`), so the whole exchange is runnable
and inspectable locally, with no real provider to register an app with
just to try it.

`client_app.py` is the actual recipe: it redirects to the provider,
exchanges the returned code for an access token, stores it in a session
cookie, and calls the provider's `/userinfo` on each request to resolve
`get_current_user`.

## Run it

Two processes, in two terminals:

```bash
uv run uvicorn examples.auth_integrations.oauth2.fake_provider:provider_app --port 8001
uv run uvicorn examples.auth_integrations.oauth2.client_app:app --port 8000
```

## Try it

```bash
curl -v localhost:8000/login
# -> a 307 redirect to localhost:8001/authorize?...
```

Following that redirect (a browser will do this automatically; with curl
you'd need `-L` or to follow it manually) takes you to the fake provider,
which immediately redirects back to `/callback?code=...`. The fake
provider skips the real login-form step; see `authorize()`'s `username`
query parameter, a stand-in for "the user clicking log in." The client
app's `/callback` exchanges that code for an access token and sets it as
a `session_token` cookie:

```bash
curl -v "localhost:8000/callback?code=<code from the redirect>"
# -> {"message": "logged in"}, with a Set-Cookie: session_token=... header

curl localhost:8000/whoami --cookie "session_token=<token from above>"
# -> {"message": "authenticated"}
```

## Pointing at a real provider

Set `FAKE_PROVIDER_URL` to the real provider's base URL and
`CLIENT_CALLBACK_URL` to your registered callback:

```bash
FAKE_PROVIDER_URL=https://your-real-provider.example.com \
CLIENT_CALLBACK_URL=https://your-app.example.com/callback \
uv run uvicorn examples.auth_integrations.oauth2.client_app:app --port 8000
```

Most real OAuth2 providers follow the same three-endpoint shape this
recipe demonstrates (`/authorize`, `/token`, and a userinfo-equivalent
endpoint), so `client_app.py`'s `login`/`callback`/`get_current_user`
logic carries over largely unchanged. You'd mainly need to adjust
request/response field names to match that provider's exact API, and add
a real `client_id`/`client_secret` (this recipe's fake provider doesn't
check either).

## What's deliberately fake

`fake_provider.py` accepts a `username` query parameter on `/authorize`
that a real authorization server never would: it stands in for a user
actually logging in and clicking "allow." It also skips client
authentication entirely (no `client_secret` check on `/token`). Neither
of these is something to carry over when pointing at a real provider.
