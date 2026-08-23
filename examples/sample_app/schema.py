from authz import Direct, From, Namespace, TupleToUserset, Union

team = Namespace("team", {"member": Direct()})

project = Namespace(
    "project",
    {
        "owner": Direct(),
        "editor": Union(Direct(), From("owner")),
        "viewer": Union(Direct(), From("editor")),
    },
)

task = Namespace(
    "task",
    {
        "project": Direct(),
        "assignee": Direct(),
        "editor": Union(Direct(), From("assignee"), TupleToUserset("project", "editor")),
        "viewer": Union(Direct(), From("editor"), TupleToUserset("project", "viewer")),
    },
)

ALL_NAMESPACES = (team, project, task)
