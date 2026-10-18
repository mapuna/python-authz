import ast
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "authz"

CORE_FILES = [
    "errors.py",
    "tuples.py",
    "schema.py",
    "conditions.py",
    "engine.py",
    "storage/base.py",
    "storage/sqlite.py",
    "storage/postgres.py",
    "__init__.py",
]


def test_core_files_never_import_fastapi():
    for relative_path in CORE_FILES:
        source = (SRC_ROOT / relative_path).read_text()
        tree = ast.parse(source, filename=relative_path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert not any(
                    n.name == "fastapi" or n.name.startswith("fastapi.")
                    for n in node.names
                ), f"{relative_path} imports fastapi directly"
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                assert module != "fastapi" and not module.startswith("fastapi."), (
                    f"{relative_path} imports from fastapi"
                )


def test_core_works_with_fastapi_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "fastapi", None)
    for module_name in list(sys.modules):
        if module_name == "authz" or module_name.startswith("authz."):
            del sys.modules[module_name]

    import authz

    async def _exercise():
        storage = authz.SqliteStorage(":memory:")
        await storage.connect()
        client = authz.Client(
            storage=storage, condition_evaluator=authz.PythonCallableEvaluator()
        )
        client.register_schema(authz.Namespace("demo", {"member": authz.Direct()}))
        await client.write(
            [authz.RelationTuple("demo", "root", "member", "user:alice")]
        )
        assert await client.check("user:alice", "member", "demo:root") is True
        decision = await client.explain("user:alice", "member", "demo:root")
        assert decision.allowed is True
        batch_results = await client.check_batch(
            [authz.CheckItem("user:alice", "member", "demo:root")]
        )
        assert batch_results == [True]
        perms = await client.list_permissions("user:alice", "demo:root")
        assert perms == ["member"]
        objs = await client.list_objects("user:alice", "member", "demo")
        assert objs == ["root"]
        await storage.close()

    import asyncio

    asyncio.run(_exercise())
