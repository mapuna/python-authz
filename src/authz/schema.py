from typing import Iterator

from authz.errors import SchemaCycleDetected


class RewriteRule:
    """Base class for relation-rewrite expressions."""


class Direct(RewriteRule):
    def __repr__(self) -> str:
        return "Direct()"


class Union(RewriteRule):
    def __init__(self, *children: RewriteRule):
        self.children = children

    def __repr__(self) -> str:
        return f"Union{self.children!r}"


class Intersection(RewriteRule):
    def __init__(self, *children: RewriteRule):
        self.children = children

    def __repr__(self) -> str:
        return f"Intersection{self.children!r}"


class Exclusion(RewriteRule):
    def __init__(self, base: RewriteRule, subtract: RewriteRule):
        self.base = base
        self.subtract = subtract

    def __repr__(self) -> str:
        return f"Exclusion({self.base!r}, {self.subtract!r})"


class From(RewriteRule):
    def __init__(self, relation: str):
        self.relation = relation

    def __repr__(self) -> str:
        return f"From({self.relation!r})"


class TupleToUserset(RewriteRule):
    def __init__(self, tupleset_relation: str, computed_relation: str):
        self.tupleset_relation = tupleset_relation
        self.computed_relation = computed_relation

    def __repr__(self) -> str:
        return f"TupleToUserset({self.tupleset_relation!r}, {self.computed_relation!r})"


class Namespace:
    def __init__(self, name: str, relations: dict[str, RewriteRule]):
        self.name = name
        self.relations = relations


def _from_edges(rule: RewriteRule) -> Iterator[str]:
    if isinstance(rule, From):
        yield rule.relation
    elif isinstance(rule, (Union, Intersection)):
        for child in rule.children:
            yield from _from_edges(child)
    elif isinstance(rule, Exclusion):
        yield from _from_edges(rule.base)
        yield from _from_edges(rule.subtract)


def check_schema_cycles(namespace: Namespace) -> None:
    graph: dict[str, list[str]] = {
        relation: list(_from_edges(rule))
        for relation, rule in namespace.relations.items()
    }

    visiting: set[str] = set()
    visited: set[str] = set()

    def dfs(relation: str, path: list[str]) -> None:
        if relation in visiting:
            raise SchemaCycleDetected(namespace.name, path + [relation])
        if relation in visited or relation not in graph:
            return
        visiting.add(relation)
        for neighbor in graph[relation]:
            dfs(neighbor, path + [relation])
        visiting.discard(relation)
        visited.add(relation)

    for relation in graph:
        if relation not in visited:
            dfs(relation, [])


def tupleset_relations(rule: RewriteRule) -> set[str]:
    if isinstance(rule, TupleToUserset):
        return {rule.tupleset_relation}
    if isinstance(rule, (Union, Intersection)):
        result: set[str] = set()
        for child in rule.children:
            result |= tupleset_relations(child)
        return result
    if isinstance(rule, Exclusion):
        return tupleset_relations(rule.base) | tupleset_relations(rule.subtract)
    return set()
