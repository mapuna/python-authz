from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from authz import Client, Condition, RelationTuple

from examples.sample_app.auth import get_authz_client, require_admin

router = APIRouter(prefix="/authz")


class CheckRequest(BaseModel):
    subject: str
    permission: str
    resource: str


class TupleIn(BaseModel):
    namespace: str
    object_id: str
    relation: str
    subject: str
    condition_name: str | None = None
    condition_context: dict = Field(default_factory=dict)


class WriteRequest(BaseModel):
    tuples: list[TupleIn]


class ExpandRequest(BaseModel):
    permission: str
    resource: str


@router.post("/check")
async def check(
    body: CheckRequest,
    _: None = Depends(require_admin),
    client: Client = Depends(get_authz_client),
):
    allowed = await client.check(body.subject, body.permission, body.resource)
    return {"allowed": allowed}


@router.post("/write")
async def write(
    body: WriteRequest,
    _: None = Depends(require_admin),
    client: Client = Depends(get_authz_client),
):
    tuples = [
        RelationTuple(
            t.namespace, t.object_id, t.relation, t.subject,
            condition=Condition(t.condition_name, t.condition_context)
            if t.condition_name else None,
        )
        for t in body.tuples
    ]
    token = await client.write(tuples)
    return {"token": token}


@router.post("/expand")
async def expand(
    body: ExpandRequest,
    _: None = Depends(require_admin),
    client: Client = Depends(get_authz_client),
):
    return await client.expand(body.permission, body.resource)
