import pytest

from authz.conditions import PythonCallableEvaluator
from authz.engine import Client
from authz.storage.sqlite import SqliteStorage


@pytest.fixture
async def storage():
    s = SqliteStorage(":memory:")
    await s.connect()
    yield s
    await s.close()


@pytest.fixture
def condition_evaluator():
    return PythonCallableEvaluator()


@pytest.fixture
def client(storage, condition_evaluator):
    return Client(storage=storage, condition_evaluator=condition_evaluator)
