"""Regression witnesses for schema changes that must not be certified compatible."""

from __future__ import annotations

from itertools import product
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from prompt_contracts.compatibility.models import CompatibilityDirection, CompatibilityStatus
from prompt_contracts.compatibility.rules import compare_expanded_schemas


@pytest.mark.parametrize(
    ("old", "new", "direction", "witness"),
    [
        (
            {"type": "object", "properties": {}},
            {"type": "object", "properties": {"x": {"type": "string"}}},
            CompatibilityDirection.INPUT,
            {"x": 1},
        ),
        (
            {"const": "a", "maxLength": 2},
            {"const": "a", "maxLength": 0},
            CompatibilityDirection.INPUT,
            "a",
        ),
        ({"enum": [True]}, {"enum": [1]}, CompatibilityDirection.INPUT, True),
        (
            {"const": {"value": True}},
            {"const": {"value": 1}},
            CompatibilityDirection.INPUT,
            {"value": True},
        ),
        (
            {"type": "object", "required": ["x"], "properties": {}},
            {"type": "object", "properties": {"x": {"type": "string"}}},
            CompatibilityDirection.OUTPUT,
            {},
        ),
    ],
)
def test_breaking_witness_is_never_reported_compatible(
    old: dict[str, Any],
    new: dict[str, Any],
    direction: CompatibilityDirection,
    witness: Any,
) -> None:
    source, target = (old, new) if direction == CompatibilityDirection.INPUT else (new, old)
    assert Draft202012Validator(source).is_valid(witness)
    assert not Draft202012Validator(target).is_valid(witness)
    status, _ = compare_expanded_schemas(old, new, direction=direction)
    assert status != CompatibilityStatus.COMPATIBLE


def test_object_compatibility_proofs_preserve_sampled_acceptance_sets() -> None:
    """Check combinations against independent JSON Schema validation, not diff rules."""
    schemas = [
        {
            "type": "object",
            "additionalProperties": additional,
            "properties": properties,
            "required": required,
        }
        for additional, properties, required in product(
            [True, False],
            [{}, {"x": {}}, {"x": {"type": "string"}}, {"x": {"const": True}}, {"x": {"const": 1}}],
            [[], ["x"], ["y"]],
        )
    ]
    samples = [{}, {"x": 1}, {"x": True}, {"x": "a"}, {"y": 1}, {"x": [], "y": 1}]
    accepted = [
        {i for i, sample in enumerate(samples) if Draft202012Validator(schema).is_valid(sample)}
        for schema in schemas
    ]
    for old, new in product(range(len(schemas)), repeat=2):
        for direction in (CompatibilityDirection.INPUT, CompatibilityDirection.OUTPUT):
            status, _ = compare_expanded_schemas(schemas[old], schemas[new], direction=direction)
            if status == CompatibilityStatus.COMPATIBLE:
                source, target = (
                    (old, new) if direction == CompatibilityDirection.INPUT else (new, old)
                )
                assert accepted[source] <= accepted[target], (schemas[old], schemas[new], direction)
