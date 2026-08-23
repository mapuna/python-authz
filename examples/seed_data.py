"""Runnable, self-contained walkthrough of the authz engine.

Run directly with: python -m examples.seed_data
"""
import asyncio

from authz import (
    Client,
    Direct,
    From,
    Namespace,
    PythonCallableEvaluator,
    RelationTuple,
    SqliteStorage,
    TupleToUserset,
    Union,
)


def build_schema() -> tuple[Namespace, Namespace, Namespace]:
    group = Namespace("group", {"member": Direct()})
    folder = Namespace(
        "folder",
        {
            "owner": Direct(),
            "editor": Union(Direct(), From("owner")),
            "viewer": Union(Direct(), From("editor")),
        },
    )
    document = Namespace(
        "document",
        {
            "parent": Direct(),
            "owner": Direct(),
            "editor": Union(Direct(), From("owner")),
            "viewer": Union(
                Direct(), From("editor"), TupleToUserset("parent", "viewer")
            ),
        },
    )
    return group, folder, document


async def seed(client: Client) -> None:
    await client.write(
        [
            # alice owns the workspace folder.
            RelationTuple("folder", "workspace", "owner", "user:alice"),
            # bob is a plain member of the eng group.
            RelationTuple("group", "eng", "member", "user:bob"),
            # the eng group can view the workspace folder.
            RelationTuple("folder", "workspace", "viewer", "group:eng#member"),
            # the roadmap document lives inside the workspace folder.
            RelationTuple("document", "roadmap", "parent", "folder:workspace"),
        ]
    )


async def main() -> None:
    async with SqliteStorage(":memory:") as storage:
        client = Client(storage=storage, condition_evaluator=PythonCallableEvaluator())
        group, folder, document = build_schema()
        client.register_schema(group, folder, document)
        await seed(client)

        print("alice viewer of roadmap:", await client.check("user:alice", "viewer", "document:roadmap"))
        print("bob viewer of roadmap:", await client.check("user:bob", "viewer", "document:roadmap"))
        print("mallory viewer of roadmap:", await client.check("user:mallory", "viewer", "document:roadmap"))


if __name__ == "__main__":
    asyncio.run(main())
