from fastapi import Depends, Header, HTTPException, Request

from authz import Client

ADMIN_USERS = {"user:alice"}


async def get_current_user(x_user_id: str | None = Header(default=None)) -> str:
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    return f"user:{x_user_id}"


async def get_authz_client(request: Request) -> Client:
    return request.app.state.authz_client


async def require_admin(subject: str = Depends(get_current_user)) -> None:
    if subject not in ADMIN_USERS:
        raise HTTPException(status_code=403, detail="admin only")
