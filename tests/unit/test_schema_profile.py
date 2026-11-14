"""Unit tests for JSON Schema Draft 2020-12 profile enforcement and $ref bounds (T05)."""

from __future__ import annotations

from typing import Any

import pytest

from prompt_contracts.errors import (
    ErrorCode,
    OutputValidationError,
    ResourceLimitError,
    UnsupportedSchemaError,
)
from prompt_contracts.types import RuntimePolicy
from prompt_contracts.validation.profile import (
    compile_schema_profile,
    validate_instance_sanitized,
)


def test_validation_diagnostics_are_capped_and_count_omitted_issues() -> None:
    schema = compile_schema_profile({"type": "array", "items": {"type": "integer"}})
    with pytest.raises(OutputValidationError) as caught:
        validate_instance_sanitized(
            schema,
            ["SYNTHETIC_SECRET"] * 60,
            policy=RuntimePolicy(max_reported_issues=5),
            error_cls=OutputValidationError,
            error_code=ErrorCode.OUTPUT_SCHEMA_VIOLATION,
            summary_message="Output validation failed",
        )
    assert len(caught.value.issues) == 5
    assert caught.value.truncated_issue_count == 55
    assert "SYNTHETIC_SECRET" not in caught.value.to_json()


def _base_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["question", "item"],
        "properties": {
            "question": {"type": "string", "minLength": 1, "maxLength": 100},
            "item": {"$ref": "#/$defs/Item"},
        },
        "$defs": {
            "Item": {
                "type": "object",
                "additionalProperties": False,
                "required": ["score"],
                "properties": {
                    "score": {"type": "number", "minimum": 0, "maximum": 1},
                },
            }
        },
    }


def test_compile_schema_accepts_supported_profile_and_local_defs() -> None:
    compiled = compile_schema_profile(_base_schema(), is_input_schema=True)
    assert compiled.expanded_node_count > 0
    validate_instance_sanitized(
        compiled,
        {"question": "Why?", "item": {"score": 0.5}},
        error_cls=UnsupportedSchemaError,
        error_code=ErrorCode.INPUT_SCHEMA_VIOLATION,
        summary_message="validation failed",
    )


@pytest.mark.parametrize(
    "unsupported_kw,value",
    [
        ("pattern", "^[a-z]+$"),
        ("format", "email"),
        ("oneOf", [{"type": "string"}]),
        ("allOf", [{"type": "string"}]),
        ("not", {"type": "null"}),
        ("patternProperties", {"^a": {"type": "string"}}),
        ("unevaluatedProperties", False),
    ],
)
def test_compile_schema_rejects_unsupported_keywords(unsupported_kw: str, value: Any) -> None:
    schema = _base_schema()
    schema["properties"]["question"][unsupported_kw] = value
    with pytest.raises(UnsupportedSchemaError) as exc_info:
        compile_schema_profile(schema)
    assert exc_info.value.code == ErrorCode.SCHEMA_KEYWORD_UNSUPPORTED


def test_compile_schema_rejects_external_or_non_defs_refs() -> None:
    schema = _base_schema()
    schema["properties"]["item"] = {"$ref": "https://example.com/item.json"}
    with pytest.raises(UnsupportedSchemaError) as exc_info:
        compile_schema_profile(schema)
    assert exc_info.value.code == ErrorCode.SCHEMA_REF_EXTERNAL_OR_INVALID


def test_compile_schema_rejects_cyclic_local_refs() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["node"],
        "properties": {"node": {"$ref": "#/$defs/NodeA"}},
        "$defs": {
            "NodeA": {"$ref": "#/$defs/NodeB"},
            "NodeB": {"$ref": "#/$defs/NodeA"},
        },
    }
    with pytest.raises(UnsupportedSchemaError) as exc_info:
        compile_schema_profile(schema)
    assert exc_info.value.code == ErrorCode.SCHEMA_REF_CYCLE


def test_compile_schema_rejects_node_explosion_beyond_policy_limit() -> None:
    policy = RuntimePolicy(max_expanded_schema_nodes=12)
    props = {f"p_{i}": {"type": "string"} for i in range(20)}
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": list(props.keys()),
        "properties": props,
    }
    with pytest.raises(ResourceLimitError) as exc_info:
        compile_schema_profile(schema, policy=policy)
    assert exc_info.value.code == ErrorCode.SCHEMA_EXPANSION_EXCEEDED


def test_compile_schema_enforces_root_object_for_input_schema() -> None:
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "array",
        "items": {"type": "string"},
    }
    with pytest.raises(UnsupportedSchemaError):
        compile_schema_profile(schema, is_input_schema=True)


def test_compile_schema_profile_keyword_type_and_bound_errors() -> None:
    compiled = compile_schema_profile(_base_schema())
    assert compiled.to_dict()["type"] == "object"

    invalid_schemas: list[Any] = [
        {"$schema": "http://json-schema.org/draft-07/schema#", "type": "object"},
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"$defs": {}}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "title": 123,
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"$ref": "#/$defs/Missing"}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "$defs": {"A": {"type": "string"}},
            "properties": {"x": {"$ref": "#/$defs/A", "minLength": 1}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"type": "date"}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"type": ["string", "string"]}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"type": 123}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"enum": []}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "additionalProperties": {"type": "string"},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["a", "a"],
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": "not-an-object",
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": "not-an-object"},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"type": "array", "items": ["not-an-object"]}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"type": "string", "minLength": -1}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"type": "string", "minLength": 10, "maxLength": 5}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {
                "x": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 2}
            },
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"type": "number", "minimum": "bad"}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"x": {"type": "number", "minimum": 10, "maximum": 5}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "$defs": "not-an-object",
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "$defs": {"bad/name": {"type": "string"}},
        },
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "$defs": {"Bad": "not-an-object"},
        },
    ]
    for bad in invalid_schemas:
        with pytest.raises(UnsupportedSchemaError):
            compile_schema_profile(bad)
