"""Unit tests for strict input validation and byte-size ceiling enforcement (T08)."""

from __future__ import annotations

import pytest

from prompt_contracts.errors import (
    ErrorCode,
    InputValidationError,
    ResourceLimitError,
)
from prompt_contracts.types import RuntimePolicy
from prompt_contracts.validation.inputs import validate_contract_inputs
from prompt_contracts.validation.profile import compile_schema_profile

_SCHEMA = compile_schema_profile(
    {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["question", "years"],
        "properties": {
            "question": {"type": "string", "minLength": 2, "maxLength": 80},
            "years": {"type": "integer", "minimum": 0, "maximum": 50},
            "notes": {"type": "string", "maxLength": 100},
        },
    },
    is_input_schema=True,
)


def test_validate_contract_inputs_returns_immutable_mapping() -> None:
    raw = {"question": "Why Python?", "years": 5}
    validated = validate_contract_inputs(raw, _SCHEMA, contract_ref="demo.test@1.0.0")
    assert dict(validated) == raw
    with pytest.raises(TypeError):
        validated["question"] = "mutated"  # type: ignore[index]


def test_validate_contract_inputs_rejects_missing_required_and_unknown_fields() -> None:
    with pytest.raises(InputValidationError) as exc_info:
        validate_contract_inputs(
            {"question": "Why Python?"},
            _SCHEMA,
            contract_ref="demo.test@1.0.0",
        )
    assert exc_info.value.code == ErrorCode.INPUT_SCHEMA_VIOLATION
    assert any(issue.code == "required" for issue in exc_info.value.issues)

    with pytest.raises(InputValidationError) as exc_info2:
        validate_contract_inputs(
            {
                "question": "Why Python?",
                "years": 5,
                "secret_extra_key": "SYNTHETIC_SECRET_MARKER_881",
            },
            _SCHEMA,
            contract_ref="demo.test@1.0.0",
        )
    assert "secret_extra_key" not in str(exc_info2.value)
    assert "SYNTHETIC_SECRET_MARKER_881" not in str(exc_info2.value)


def test_validate_contract_inputs_rejects_bool_for_integer_and_size_limit() -> None:
    with pytest.raises(InputValidationError):
        validate_contract_inputs(
            {"question": "Why Python?", "years": True},
            _SCHEMA,
            contract_ref="demo.test@1.0.0",
        )

    small_policy = RuntimePolicy(max_input_bytes=32)
    with pytest.raises(ResourceLimitError) as exc_info:
        validate_contract_inputs(
            {"question": "A" * 50, "years": 5},
            _SCHEMA,
            contract_ref="demo.test@1.0.0",
            policy=small_policy,
        )
    assert exc_info.value.code == ErrorCode.RESOURCE_SIZE_EXCEEDED


def test_validate_inputs_accepts_supported_immutable_json_containers() -> None:
    from types import MappingProxyType

    schema = compile_schema_profile(
        {
            "type": "object",
            "additionalProperties": False,
            "required": ["items"],
            "properties": {"items": {"type": "array", "items": {"type": "integer"}}},
        },
        is_input_schema=True,
    )
    raw = MappingProxyType({"items": (1, 2)})
    assert validate_contract_inputs(raw, schema)["items"] == (1, 2)


def test_validate_inputs_rejects_surrogates_with_contract_context() -> None:
    with pytest.raises(InputValidationError) as exc_info:
        validate_contract_inputs(
            {"question": "SECRET_MARKER\ud800", "years": 5},
            _SCHEMA,
            contract_ref="demo.test@1.0.0",
        )
    assert exc_info.value.contract_ref == "demo.test@1.0.0"
    assert "SECRET_MARKER" not in repr(exc_info.value)
