from authz.schema import Direct, Namespace
from authz.tuples import RelationTuple


async def test_check_with_token_observes_the_write_that_produced_it(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    token = await client.write(
        [RelationTuple("document", "doc42", "owner", "user:alice")]
    )
    result = await client.check(
        "user:alice", "owner", "document:doc42", at_least_as_fresh_as=token
    )
    assert result is True


async def test_check_without_token_still_observes_prior_writes(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    await client.write([RelationTuple("document", "doc42", "owner", "user:alice")])
    assert await client.check("user:alice", "owner", "document:doc42") is True


async def test_delete_returns_a_token_reflecting_the_removal(client):
    client.register_schema(Namespace("document", {"owner": Direct()}))
    t = RelationTuple("document", "doc42", "owner", "user:alice")
    write_token = await client.write([t])
    delete_token = await client.delete([t])
    assert int(delete_token) >= int(write_token)
    assert await client.check(
        "user:alice", "owner", "document:doc42", at_least_as_fresh_as=delete_token
    ) is False
