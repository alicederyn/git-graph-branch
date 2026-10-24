"""Merge GraphQL queries into one document, and split the response (ADR 4)."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from graphql import (
    DocumentNode,
    FieldNode,
    FragmentDefinitionNode,
    FragmentSpreadNode,
    NameNode,
    OperationDefinitionNode,
    OperationType,
    VariableDefinitionNode,
    VariableNode,
    Visitor,
    parse,
    print_ast,
    visit,
)


class QueryError(Exception):
    """GraphQL errors for a query, or for the whole batch."""

    def __init__(self, errors: Sequence[Mapping[str, Any]]) -> None:
        super().__init__("; ".join(str(e.get("message", e)) for e in errors))
        self.errors = errors


@dataclass(frozen=True)
class Query:
    document: str
    variables: Mapping[str, Any]


class Prefixer(Visitor):
    """Prefix the names of all variables and fragments."""

    def __init__(self, prefix: str) -> None:
        super().__init__()
        self.prefix = prefix

    def rename(self, node: Any) -> Any:
        return dataclasses.replace(
            node, name=NameNode(value=self.prefix + node.name.value)
        )

    def enter_variable(self, node: VariableNode, *_: Any) -> VariableNode:
        return self.rename(node)  # type: ignore[no-any-return]

    def enter_fragment_spread(
        self, node: FragmentSpreadNode, *_: Any
    ) -> FragmentSpreadNode:
        return self.rename(node)  # type: ignore[no-any-return]

    def enter_fragment_definition(
        self, node: FragmentDefinitionNode, *_: Any
    ) -> FragmentDefinitionNode:
        return self.rename(node)  # type: ignore[no-any-return]


def operation(document: DocumentNode) -> OperationDefinitionNode:
    operations = [
        d for d in document.definitions if isinstance(d, OperationDefinitionNode)
    ]
    if len(operations) != 1 or operations[0].operation != OperationType.QUERY:
        raise ValueError("Each document must contain exactly one query")
    return operations[0]


@dataclass(frozen=True)
class MergedQuery:
    document: str
    variables: dict[str, Any]
    aliases: dict[str, tuple[int, str]]
    """The query index and original response key of each merged root field."""
    count: int

    def split(self, response: Mapping[str, Any]) -> list[dict[str, Any] | Exception]:
        """Split a response into one result for each query.

        An error goes to the query of the root field in its path. An error with no
        path, or a null `data`, fails all queries.
        """
        errors = response.get("errors") or []
        data = response.get("data")
        if data is None or any(not e.get("path") for e in errors):
            error = QueryError(errors or [{"message": "No data in response"}])
            return [error] * self.count

        results: list[dict[str, Any]] = [{} for _ in range(self.count)]
        for alias, value in data.items():
            index, key = self.aliases[alias]
            results[index][key] = value
        query_errors: list[list[Mapping[str, Any]]] = [[] for _ in range(self.count)]
        for error in errors:
            index, key = self.aliases[error["path"][0]]
            query_errors[index].append({**error, "path": [key, *error["path"][1:]]})
        return [
            QueryError(errs) if errs else result
            for result, errs in zip(results, query_errors)
        ]


def merge(queries: Sequence[Query]) -> MergedQuery:
    """Merge queries into one, with each root field aliased.

    Query i has its variables and fragments renamed with the prefix `q{i}_`, and
    its root fields aliased to `q{i}_<response key>`.
    """
    variable_definitions: list[VariableDefinitionNode] = []
    selections: list[FieldNode] = []
    fragments: list[FragmentDefinitionNode] = []
    variables: dict[str, Any] = {}
    aliases: dict[str, tuple[int, str]] = {}
    for index, query in enumerate(queries):
        prefix = f"q{index}_"
        document = visit(parse(query.document), Prefixer(prefix))
        op = operation(document)
        variable_definitions.extend(op.variable_definitions or ())
        for selection in op.selection_set.selections:
            if not isinstance(selection, FieldNode):
                raise ValueError("Root selections must be fields")
            key = (selection.alias or selection.name).value
            alias = prefix + key
            aliases[alias] = (index, key)
            selections.append(
                dataclasses.replace(selection, alias=NameNode(value=alias))
            )
        fragments.extend(
            d for d in document.definitions if isinstance(d, FragmentDefinitionNode)
        )
        variables.update(
            (prefix + name, value) for name, value in query.variables.items()
        )

    merged = parse("query Merged { __typename }")
    op = operation(merged)
    op = dataclasses.replace(
        op,
        variable_definitions=tuple(variable_definitions),
        selection_set=dataclasses.replace(
            op.selection_set, selections=tuple(selections)
        ),
    )
    document = DocumentNode(definitions=(op, *fragments))
    return MergedQuery(print_ast(document), variables, aliases, len(queries))
