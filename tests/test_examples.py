from examples.seed_data import build_schema, seed


async def test_seed_populates_a_working_authorization_graph(client):
    group, folder, document = build_schema()
    client.register_schema(group, folder, document)
    await seed(client)

    # alice owns the workspace folder -> inherits editor/viewer on its document.
    assert await client.check("user:alice", "viewer", "document:roadmap") is True
    # bob is a plain eng member -> folder viewer -> inherited by the document.
    assert await client.check("user:bob", "viewer", "document:roadmap") is True
    # someone outside the org has no access.
    assert await client.check("user:mallory", "viewer", "document:roadmap") is False
