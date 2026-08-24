# Recipe: Self-Issued JWT

The app is its own identity provider. `/login` checks credentials against
a tiny in-memory user store and mints a signed JWT; `get_current_user`
verifies that JWT on every subsequent request. No external service is
involved.

## Run it

```bash
uv run uvicorn examples.auth_integrations.jwt.app:app --port 8010
```

## Try it

```bash
curl -X POST "localhost:8010/login?username=alice&password=password123"
# -> {"access_token": "...", "token_type": "bearer"}

curl localhost:8010/whoami -H "Authorization: Bearer <token from above>"
# -> {"message": "authenticated"}
```

Wrong credentials, a missing token, or a tampered/expired token all return
`401` from `/whoami` or `/login` respectively.

## What to change for production

- **`SECRET_KEY`**: hardcoded here for a runnable demo. Read it from an
  environment variable instead, and never commit a real one.
- **`FAKE_USERS`**: a plain dict is fine for this recipe; a real app
  checks credentials against its actual user store (hashed passwords, not
  plaintext).
- **Token expiry**: tune `timedelta(hours=1)` in `login()` to whatever
  your app's session policy calls for, and consider adding refresh tokens
  if silent re-authentication matters to you.
- **Algorithm**: this recipe uses `HS256` (a shared secret) for
  simplicity. If multiple services need to verify tokens without sharing
  that secret, use `RS256`/`ES256` with a public/private key pair instead.
