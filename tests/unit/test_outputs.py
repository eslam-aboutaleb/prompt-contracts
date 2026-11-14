"""Unit tests for text and JSON output validation (T09)."""

from __future__ import annotations

import pytest

from prompt_contracts.errors import ErrorCode, OutputValidationError
from prompt_contracts.types import OutputMode, OutputSpec
from prompt_contracts.validation.outputs import validate_contract_output
from prompt_contracts.validation.profile import compile_schema_profile

_RAW_OUT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["answer", "confidence"],
    "properties": {
        "answer": {"type": "string", "minLength": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}
_JSON_SPEC = OutputSpec(
    mode=OutputMode.JSON,
    schema_file="output.schema.json",
    schema=_RAW_OUT_SCHEMA,
)
_COMPILED_OUTPUT = compile_schema_profile(_RAW_OUT_SCHEMA)


def test_validate_json_output_accepts_valid_payload() -> None:
    result = validate_contract_output(
        '{"answer": "Grounded response.", "confidence": 0.85}',
        _JSON_SPEC,
        _COMPILED_OUTPUT,
        contract_ref="demo.test@1.0.0",
    )
    assert result == {"answer": "Grounded response.", "confidence": 0.85}


def test_validate_json_output_distinguishes_parse_error_from_schema_violation() -> None:
    with pytest.raises(OutputValidationError) as parse_exc:
        validate_contract_output(
            '```json\n{"answer": "fenced", "confidence": 0.5}\n```',
            _JSON_SPEC,
            _COMPILED_OUTPUT,
            contract_ref="demo.test@1.0.0",
        )
    assert parse_exc.value.code == ErrorCode.OUTPUT_FENCE_OR_PROSE_REJECTED

    with pytest.raises(OutputValidationError) as val_exc:
        validate_contract_output(
            '{"answer": "ok", "confidence": 2.5}',
            _JSON_SPEC,
            _COMPILED_OUTPUT,
            contract_ref="demo.test@1.0.0",
        )
    assert val_exc.value.code == ErrorCode.OUTPUT_SCHEMA_VIOLATION


def test_validate_text_output_enforces_length_bounds() -> None:
    text_spec = OutputSpec(mode=OutputMode.TEXT, min_length=5, max_length=20)
    out = validate_contract_output(
        "Valid text output",
        text_spec,
        None,
        contract_ref="demo.text@1.0.0",
    )
    assert out == "Valid text output"

    with pytest.raises(OutputValidationError) as short_exc:
        validate_contract_output(
            "Hi",
            text_spec,
            None,
            contract_ref="demo.text@1.0.0",
        )
    assert short_exc.value.code == ErrorCode.OUTPUT_TEXT_LENGTH_VIOLATION


@pytest.mark.parametrize(
    "spec", [_JSON_SPEC, OutputSpec(mode=OutputMode.TEXT, min_length=1, max_length=100)]
)
def test_output_surrogates_raise_safe_domain_errors(spec: OutputSpec) -> None:
    with pytest.raises(OutputValidationError) as exc_info:
        validate_contract_output("SECRET_MARKER\ud800", spec, _COMPILED_OUTPUT)
    assert "SECRET_MARKER" not in str(exc_info.value)
    assert exc_info.value.__suppress_context__ is True
