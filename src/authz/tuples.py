from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ObjectRef:
    namespace: str
    object_id: str

    def __str__(self) -> str:
        return f"{self.namespace}:{self.object_id}"

    @classmethod
    def parse(cls, raw: str) -> "ObjectRef":
        namespace, colon, object_id = raw.partition(":")
        if not colon:
            raise ValueError(
                f"invalid object reference {raw!r}; expected 'namespace:object_id'"
            )
        return cls(namespace, object_id)


@dataclass(frozen=True)
class SubjectRef:
    namespace: str
    object_id: str
    relation: str | None = None

    @property
    def is_userset(self) -> bool:
        return self.relation is not None

    def __str__(self) -> str:
        base = f"{self.namespace}:{self.object_id}"
        return f"{base}#{self.relation}" if self.relation else base

    @classmethod
    def parse(cls, raw: str) -> "SubjectRef":
        obj_part, sep, relation = raw.partition("#")
        namespace, colon, object_id = obj_part.partition(":")
        if not colon:
            raise ValueError(
                f"invalid subject reference {raw!r}; expected 'namespace:object_id' "
                "or 'namespace:object_id#relation'"
            )
        return cls(namespace, object_id, relation if sep else None)


@dataclass(frozen=True)
class Condition:
    name: str
    context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RelationTuple:
    namespace: str
    object_id: str
    relation: str
    subject: str
    condition: Condition | None = None

    @property
    def object(self) -> ObjectRef:
        return ObjectRef(self.namespace, self.object_id)

    @property
    def subject_ref(self) -> SubjectRef:
        return SubjectRef.parse(self.subject)

    def __str__(self) -> str:
        return (
            f"({self.namespace}, {self.object_id!r}, "
            f"{self.relation!r}, {self.subject!r})"
        )
