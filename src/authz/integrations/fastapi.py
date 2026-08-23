import inspect
from typing import Awaitable, Callable

from fastapi import Depends, HTTPException, Request

from authz.engine import Client

ResourceFn = Callable[[Request], str | Awaitable[str]]


async def _resolve_resource(resource: str | ResourceFn, request: Request) -> str:
    if isinstance(resource, str):
        return resource.format(**request.path_params)
    result = resource(request)
    if inspect.isawaitable(result):
        result = await result
    return result


def requires(
    permission: str,
    resource: str | ResourceFn,
    *,
    get_client: Callable[..., Client | Awaitable[Client]],
    get_subject: Callable[..., str | Awaitable[str]],
    detail: str = "Forbidden",
) -> Callable:
    async def dependency(
        request: Request,
        client: Client = Depends(get_client),
        subject: str = Depends(get_subject),
    ) -> None:
        resolved = await _resolve_resource(resource, request)
        if not await client.check(subject, permission, resolved):
            raise HTTPException(status_code=403, detail=detail)

    return dependency
