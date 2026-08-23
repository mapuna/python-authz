import inspect
from typing import Any, Awaitable, Callable, Mapping, Protocol, Union

from authz.errors import ConditionNotFound

ConditionFn = Callable[..., Union[bool, Awaitable[bool]]]


class ConditionEvaluator(Protocol):
    def is_registered(self, name: str) -> bool: ...

    async def evaluate(
        self, name: str, subject: str, resource: str, context: Mapping[str, Any]
    ) -> bool: ...


class PythonCallableEvaluator:
    def __init__(self) -> None:
        self._conditions: dict[str, ConditionFn] = {}

    def register(self, name: str, fn: ConditionFn) -> None:
        self._conditions[name] = fn

    def is_registered(self, name: str) -> bool:
        return name in self._conditions

    async def evaluate(
        self, name: str, subject: str, resource: str, context: Mapping[str, Any]
    ) -> bool:
        try:
            fn = self._conditions[name]
        except KeyError:
            raise ConditionNotFound(name) from None
        result = fn(subject=subject, resource=resource, **context)
        if inspect.isawaitable(result):
            result = await result
        return bool(result)
