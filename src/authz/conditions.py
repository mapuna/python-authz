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

    @classmethod
    def with_builtins(
        cls, extra: Mapping[str, ConditionFn] | None = None
    ) -> "PythonCallableEvaluator":
        evaluator = cls()
        for name, fn in builtin_conditions().items():
            evaluator.register(name, fn)
        if extra:
            for name, fn in extra.items():
                evaluator.register(name, fn)
        return evaluator

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


def _max_amount(*, subject: str, resource: str, **ctx: Any) -> bool:
    try:
        amount = float(ctx.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0.0
    try:
        max_amount = float(ctx.get("max_amount", float("inf")))
    except (ValueError, TypeError):
        max_amount = float("inf")
    return amount <= max_amount


def _min_amount(*, subject: str, resource: str, **ctx: Any) -> bool:
    try:
        amount = float(ctx.get("amount", 0))
    except (ValueError, TypeError):
        amount = 0.0
    try:
        min_amount = float(ctx.get("min_amount", 0))
    except (ValueError, TypeError):
        min_amount = 0.0
    return amount >= min_amount


def _equals_attr(*, subject: str, resource: str, **ctx: Any) -> bool:
    attr_name = str(ctx.get("attribute", ""))
    return ctx.get(attr_name) == ctx.get("expected")


def _in_set(*, subject: str, resource: str, **ctx: Any) -> bool:
    attr_name = str(ctx.get("attribute", ""))
    allowed = ctx.get("allowed_values")
    if allowed is None:
        allowed = ()
    return ctx.get(attr_name) in allowed


def _jurisdiction_match(*, subject: str, resource: str, **ctx: Any) -> bool:
    jur = ctx.get("jurisdiction")
    if "allowed_jurisdictions" in ctx:
        allowed = ctx.get("allowed_jurisdictions")
        if allowed is None:
            allowed = ()
        return jur in allowed
    if "required_jurisdiction" in ctx:
        return jur == ctx.get("required_jurisdiction")
    return True


def _not_same_subject(*, subject: str, resource: str, **ctx: Any) -> bool:
    return subject != ctx.get("excluded_subject")


def builtin_conditions() -> dict[str, ConditionFn]:
    return {
        "max_amount": _max_amount,
        "min_amount": _min_amount,
        "equals_attr": _equals_attr,
        "in_set": _in_set,
        "jurisdiction_match": _jurisdiction_match,
        "not_same_subject": _not_same_subject,
    }
