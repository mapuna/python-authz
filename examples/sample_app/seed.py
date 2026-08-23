from authz import Client, Condition, RelationTuple

from examples.sample_app import domain


async def seed(client: Client) -> None:
    domain.projects["p1"] = domain.Project(id="p1", name="Website Redesign")
    domain.tasks["t1"] = domain.Task(
        id="t1", project_id="p1", title="Design homepage", assignee="user:bob"
    )

    await client.write(
        [
            RelationTuple("project", "p1", "owner", "user:alice"),
            RelationTuple("task", "t1", "project", "project:p1"),
            RelationTuple("task", "t1", "assignee", "user:bob"),
            RelationTuple(
                "project", "p1", "editor", "user:carol",
                condition=Condition("is_active_contract", {"active": True}),
            ),
        ]
    )
