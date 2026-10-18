import inspect
from typing import Any, Awaitable, Callable, Mapping

from fastapi import Depends, HTTPException, Request

from authz.engine import Client, EvaluationDecision

ResourceFn = Callable[[Request], str | Awaitable[str]]
ContextFn = Callable[[Request], Mapping[str, Any] | Awaitable[Mapping[str, Any]]]

__all__ = ["ContextFn", "ResourceFn", "explain_access", "requires"]


async def _resolve_resource(resource: str | ResourceFn, request: Request) -> str:
    if isinstance(resource, str):
        params = {
            **dict(request.headers),
            **dict(request.query_params),
            **dict(request.path_params),
        }
        return resource.format(**params)
    result = resource(request)
    if inspect.isawaitable(result):
        result = await result
    return result


async def _resolve_context(
    get_context: ContextFn | None, request: Request
) -> Mapping[str, Any] | None:
    if get_context is None:
        return None
    try:
        result = get_context(request)
    except TypeError:
        result = get_context()  # type: ignore[call-arg]
    if inspect.isawaitable(result):
        result = await result
    return result


def requires(
    permission: str,
    resource: str | ResourceFn,
    *,
    get_client: Callable[..., Client | Awaitable[Client]],
    get_subject: Callable[..., str | Awaitable[str]],
    get_context: ContextFn | None = None,
    detail: str = "Forbidden",
) -> Callable:
    async def dependency(
        request: Request,
        client: Client = Depends(get_client),
        subject: str = Depends(get_subject),
    ) -> None:
        resolved = await _resolve_resource(resource, request)
        ctx = await _resolve_context(get_context, request)
        if not await client.check(subject, permission, resolved, context=ctx):
            raise HTTPException(status_code=403, detail=detail)

    return dependency


def explain_access(
    permission: str,
    resource: str | ResourceFn,
    *,
    get_client: Callable[..., Client | Awaitable[Client]],
    get_subject: Callable[..., str | Awaitable[str]],
    get_context: ContextFn | None = None,
    detail: str = "Forbidden",
) -> Callable:
    async def dependency(
        request: Request,
        client: Client = Depends(get_client),
        subject: str = Depends(get_subject),
    ) -> EvaluationDecision:
        resolved = await _resolve_resource(resource, request)
        ctx = await _resolve_context(get_context, request)
        decision = await client.explain(subject, permission, resolved, context=ctx)
        request.state.authz_decision = decision
        if not decision.allowed:
            raise HTTPException(status_code=403, detail=detail)
        return decision

    return dependency
