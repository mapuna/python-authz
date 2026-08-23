from collections import deque
from dataclasses import dataclass
from typing import Sequence

from authz.conditions import ConditionEvaluator, ConditionFn
from authz.errors import (
    ConditionNotFound,
    CycleDetected,
    DepthLimitExceeded,
    NamespaceNotFound,
    RelationNotFound,
    WouldCreateCycle,
)
from authz.schema import (
    Direct,
    Exclusion,
    From,
    Intersection,
    Namespace,
    RewriteRule,
    TupleToUserset,
    Union,
    check_schema_cycles,
    tupleset_relations,
)
from authz.storage.base import Storage, Token
from authz.tuples import ObjectRef, RelationTuple, SubjectRef


@dataclass(frozen=True)
class UsersetTree:
    relation: str
    object: ObjectRef
    direct_subjects: tuple[str, ...] = ()
    children: tuple["UsersetTree", ...] = ()


class Client:
    def __init__(
        self,
        storage: Storage,
        condition_evaluator: ConditionEvaluator,
        max_depth: int = 25,
    ):
        self._storage = storage
        self._conditions = condition_evaluator
        self._max_depth = max_depth
        self._namespaces: dict[str, Namespace] = {}
        self._traversal_relations: dict[str, set[str]] = {}

    def register_schema(self, *namespaces: Namespace) -> None:
        for ns in namespaces:
            check_schema_cycles(ns)
            self._namespaces[ns.name] = ns
            traversal: set[str] = set()
            for rule in ns.relations.values():
                traversal |= tupleset_relations(rule)
            self._traversal_relations[ns.name] = traversal

    def register_condition(self, name: str, fn: ConditionFn) -> None:
        self._conditions.register(name, fn)

    def _get_relation(self, namespace: str, relation: str) -> RewriteRule:
        ns = self._namespaces.get(namespace)
        if ns is None:
            raise NamespaceNotFound(namespace)
        rule = ns.relations.get(relation)
        if rule is None:
            raise RelationNotFound(namespace, relation)
        return rule

    def _validate_tuple(self, t: RelationTuple) -> None:
        self._get_relation(t.namespace, t.relation)
        if t.condition is not None and not self._conditions.is_registered(t.condition.name):
            raise ConditionNotFound(t.condition.name)

    def _is_graph_edge(self, t: RelationTuple) -> bool:
        if t.relation in self._traversal_relations.get(t.namespace, set()):
            return True
        return t.subject_ref.is_userset

    async def _guard_against_cycle(self, t: RelationTuple) -> None:
        source = (t.namespace, t.object_id)
        subject_ref = t.subject_ref
        if subject_ref.is_userset:
            start = (subject_ref.namespace, subject_ref.object_id, subject_ref.relation)
        else:
            start = (subject_ref.namespace, subject_ref.object_id, t.relation)

        visited: set[tuple[str, str]] = set()
        queue: deque[tuple[str, str, str]] = deque([start])
        while queue:
            namespace, object_id, relation = queue.popleft()
            if (namespace, object_id) == source:
                raise WouldCreateCycle(t, f"{t.object} -> {namespace}:{object_id}")
            if (namespace, object_id) in visited:
                continue
            visited.add((namespace, object_id))
            existing = await self._storage.read_tuples(
                namespace, object_id=object_id, relation=relation
            )
            for et in existing:
                eref = et.subject_ref
                if eref.is_userset:
                    queue.append((eref.namespace, eref.object_id, eref.relation))
                elif relation in self._traversal_relations.get(namespace, set()):
                    queue.append((eref.namespace, eref.object_id, relation))

    async def write(self, tuples: Sequence[RelationTuple]) -> Token:
        for t in tuples:
            self._validate_tuple(t)
        async with self._storage.transaction():
            for t in tuples:
                if self._is_graph_edge(t):
                    await self._guard_against_cycle(t)
                await self._storage.write_tuples([t])
            return await self._storage.current_token()

    async def delete(self, tuples: Sequence[RelationTuple]) -> Token:
        for t in tuples:
            self._get_relation(t.namespace, t.relation)
        return await self._storage.delete_tuples(tuples)

    async def read(
        self,
        namespace: str,
        object_id: str | None = None,
        relation: str | None = None,
        subject: str | None = None,
    ) -> list[RelationTuple]:
        if namespace not in self._namespaces:
            raise NamespaceNotFound(namespace)
        if relation is not None:
            self._get_relation(namespace, relation)
        return await self._storage.read_tuples(
            namespace, object_id=object_id, relation=relation, subject=subject
        )

    async def check(
        self,
        subject: str,
        permission: str,
        resource: str,
        *,
        at_least_as_fresh_as: Token | None = None,
    ) -> bool:
        if at_least_as_fresh_as is not None:
            await self._storage.wait_for_token(at_least_as_fresh_as)
        target = ObjectRef.parse(resource)
        self._get_relation(target.namespace, permission)
        return await self._check_relation(
            subject, target.namespace, target.object_id, permission, []
        )

    async def _check_relation(
        self,
        subject: str,
        namespace: str,
        object_id: str,
        relation: str,
        path: list[tuple[str, str, str]],
    ) -> bool:
        node = (namespace, object_id, relation)
        if node in path:
            trail = [f"{ns}:{oid}#{rel}" for ns, oid, rel in path]
            trail.append(f"{namespace}:{object_id}#{relation}")
            raise CycleDetected(trail)
        if len(path) >= self._max_depth:
            raise DepthLimitExceeded(self._max_depth)
        rule = self._get_relation(namespace, relation)
        return await self._eval_rule(
            rule, subject, namespace, object_id, relation, path + [node]
        )

    async def _eval_rule(
        self,
        rule,
        subject: str,
        namespace: str,
        object_id: str,
        relation: str,
        path: list[tuple[str, str, str]],
    ) -> bool:
        if isinstance(rule, Direct):
            return await self._eval_direct(subject, namespace, object_id, relation, path)
        if isinstance(rule, Union):
            for child in rule.children:
                if await self._eval_rule(child, subject, namespace, object_id, relation, path):
                    return True
            return False
        if isinstance(rule, Intersection):
            for child in rule.children:
                if not await self._eval_rule(child, subject, namespace, object_id, relation, path):
                    return False
            return True
        if isinstance(rule, Exclusion):
            if not await self._eval_rule(rule.base, subject, namespace, object_id, relation, path):
                return False
            return not await self._eval_rule(
                rule.subtract, subject, namespace, object_id, relation, path
            )
        if isinstance(rule, From):
            return await self._check_relation(subject, namespace, object_id, rule.relation, path)
        if isinstance(rule, TupleToUserset):
            parents = await self._storage.read_tuples(
                namespace, object_id=object_id, relation=rule.tupleset_relation
            )
            for pt in parents:
                pref = pt.subject_ref
                if await self._check_relation(
                    subject, pref.namespace, pref.object_id, rule.computed_relation, path
                ):
                    return True
            return False
        raise TypeError(f"unsupported rewrite rule: {rule!r}")

    async def _eval_direct(
        self,
        subject: str,
        namespace: str,
        object_id: str,
        relation: str,
        path: list[tuple[str, str, str]],
    ) -> bool:
        subject_ref = SubjectRef.parse(subject)
        tuples = await self._storage.read_tuples(namespace, object_id=object_id, relation=relation)
        for t in tuples:
            if t.condition is not None:
                holds = await self._conditions.evaluate(
                    t.condition.name, subject, f"{namespace}:{object_id}", t.condition.context
                )
                if not holds:
                    continue
            tref = t.subject_ref
            if not tref.is_userset:
                if tref.namespace == subject_ref.namespace and tref.object_id == subject_ref.object_id:
                    return True
            else:
                if await self._check_relation(
                    subject, tref.namespace, tref.object_id, tref.relation, path
                ):
                    return True
        return False

    async def expand(self, permission: str, resource: str) -> "UsersetTree":
        target = ObjectRef.parse(resource)
        rule = self._get_relation(target.namespace, permission)
        return await self._expand_rule(rule, target.namespace, target.object_id, permission)

    async def _expand_rule(
        self, rule, namespace: str, object_id: str, relation: str
    ) -> "UsersetTree":
        direct_subjects: list[str] = []
        children: list[UsersetTree] = []

        async def walk(r) -> None:
            if isinstance(r, Direct):
                tuples = await self._storage.read_tuples(
                    namespace, object_id=object_id, relation=relation
                )
                direct_subjects.extend(t.subject for t in tuples)
            elif isinstance(r, (Union, Intersection)):
                for child in r.children:
                    await walk(child)
            elif isinstance(r, Exclusion):
                await walk(r.base)
            elif isinstance(r, From):
                children.append(
                    await self._expand_rule(
                        self._get_relation(namespace, r.relation),
                        namespace,
                        object_id,
                        r.relation,
                    )
                )
            elif isinstance(r, TupleToUserset):
                parents = await self._storage.read_tuples(
                    namespace, object_id=object_id, relation=r.tupleset_relation
                )
                for pt in parents:
                    pref = pt.subject_ref
                    children.append(
                        await self._expand_rule(
                            self._get_relation(pref.namespace, r.computed_relation),
                            pref.namespace,
                            pref.object_id,
                            r.computed_relation,
                        )
                    )

        await walk(rule)
        return UsersetTree(
            relation=relation,
            object=ObjectRef(namespace, object_id),
            direct_subjects=tuple(direct_subjects),
            children=tuple(children),
        )
