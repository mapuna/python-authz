import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from authz import (
    Client,
    Direct,
    Namespace,
    PythonCallableEvaluator,
    RelationTuple,
    SqliteStorage,
    TupleToUserset,
)
from authz import Union as UnionRule
from authz.integrations.fastapi import requires


@pytest.fixture
async def authz_client():
    storage = SqliteStorage(":memory:")
    await storage.connect()
    c = Client(storage=storage, condition_evaluator=PythonCallableEvaluator())
    c.register_schema(Namespace("document", {"owner": Direct(), "viewer": Direct()}))
    await c.write([RelationTuple("document", "doc42", "viewer", "user:alice")])
    yield c
    await storage.close()


def _make_app(authz_client, *, resource, subject="user:alice"):
    app = FastAPI()

    async def get_client():
        return authz_client

    async def get_subject():
        return subject

    @app.get("/documents/{document_id}")
    async def read_document(
        document_id: str,
        _: None = Depends(
            requires("viewer", resource, get_client=get_client, get_subject=get_subject)
        ),
    ):
        return {"document_id": document_id}

    return app


def test_allowed_request_returns_200(authz_client):
    app = _make_app(authz_client, resource="document:{document_id}")
    client = TestClient(app)
    response = client.get("/documents/doc42")
    assert response.status_code == 200
    assert response.json() == {"document_id": "doc42"}


def test_denied_request_returns_403(authz_client):
    app = _make_app(
        authz_client, resource="document:{document_id}", subject="user:mallory"
    )
    client = TestClient(app)
    response = client.get("/documents/doc42")
    assert response.status_code == 403


def test_denied_request_uses_custom_detail(authz_client):
    def build_app():
        app = FastAPI()

        async def get_client():
            return authz_client

        async def get_subject():
            return "user:mallory"

        @app.get("/documents/{document_id}")
        async def read_document(
            document_id: str,
            _: None = Depends(
                requires(
                    "viewer", "document:{document_id}",
                    get_client=get_client, get_subject=get_subject,
                    detail="you cannot view this document",
                )
            ),
        ):
            return {"document_id": document_id}

        return app

    client = TestClient(build_app())
    response = client.get("/documents/doc42")
    assert response.status_code == 403
    assert response.json()["detail"] == "you cannot view this document"


def test_callable_resource_sync(authz_client):
    def resource_fn(request):
        return f"document:{request.path_params['document_id']}"

    app = _make_app(authz_client, resource=resource_fn)
    client = TestClient(app)
    response = client.get("/documents/doc42")
    assert response.status_code == 200


def test_callable_resource_async(authz_client):
    async def resource_fn(request):
        return f"document:{request.path_params['document_id']}"

    app = _make_app(authz_client, resource=resource_fn)
    client = TestClient(app)
    response = client.get("/documents/doc42")
    assert response.status_code == 200


@pytest.fixture
async def cyclic_folder_client():
    storage = SqliteStorage(":memory:")
    await storage.connect()
    c = Client(storage=storage, condition_evaluator=PythonCallableEvaluator())
    c.register_schema(
        Namespace(
            "folder",
            {
                "parent": Direct(),
                "viewer": UnionRule(Direct(), TupleToUserset("parent", "viewer")),
            },
        )
    )
    # Bypass write()'s cycle guard by writing directly through storage,
    # same technique as tests/test_engine_cycle_and_depth.py.
    await storage.write_tuples(
        [
            RelationTuple("folder", "A", "parent", "folder:B"),
            RelationTuple("folder", "B", "parent", "folder:A"),
        ]
    )
    yield c
    await storage.close()


def test_auth_error_propagates_as_500_not_403(cyclic_folder_client):
    app = FastAPI()

    async def get_client():
        return cyclic_folder_client

    async def get_subject():
        return "user:alice"

    @app.get("/folders/{folder_id}")
    async def read_folder(
        folder_id: str,
        _: None = Depends(
            requires(
                "viewer", "folder:{folder_id}",
                get_client=get_client, get_subject=get_subject,
            )
        ),
    ):
        return {"folder_id": folder_id}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/folders/A")
    assert response.status_code == 500
    assert response.status_code != 403


def test_get_subject_dependency_chain_resolves_transitively(authz_client):
    app = FastAPI()

    def fake_bearer_token(authorization: str = "") -> str:
        # stand-in for a real OAuth2/bearer-token dependency: get_subject
        # below depends on THIS, proving requires() doesn't flatten or
        # otherwise interfere with a multi-level dependency chain.
        return authorization or "alice"

    async def get_client():
        return authz_client

    async def get_subject(token: str = Depends(fake_bearer_token)):
        return f"user:{token}"

    @app.get("/documents/{document_id}")
    async def read_document(
        document_id: str,
        _: None = Depends(
            requires(
                "viewer", "document:{document_id}",
                get_client=get_client, get_subject=get_subject,
            )
        ),
    ):
        return {"document_id": document_id}

    client = TestClient(app)
    response = client.get("/documents/doc42")
    assert response.status_code == 200


def test_dependency_overrides_swap_client_and_subject(authz_client):
    # get_client/get_subject are defined here (not via _make_app) so this
    # test can reference them by identity for app.dependency_overrides --
    # FastAPI keys overrides by the exact callable used in the route.
    app = FastAPI()

    async def get_client():
        return authz_client

    async def get_subject():
        return "user:alice"

    @app.get("/documents/{document_id}")
    async def read_document(
        document_id: str,
        _: None = Depends(
            requires(
                "viewer", "document:{document_id}",
                get_client=get_client, get_subject=get_subject,
            )
        ),
    ):
        return {"document_id": document_id}

    client = TestClient(app)
    assert client.get("/documents/doc42").status_code == 200

    # user:alice is a viewer; user:mallory is not -- override_subject flips
    # the outcome without touching the route or get_subject itself.
    async def override_subject():
        return "user:mallory"

    app.dependency_overrides[get_subject] = override_subject
    assert client.get("/documents/doc42").status_code == 403

    del app.dependency_overrides[get_subject]
    assert client.get("/documents/doc42").status_code == 200
