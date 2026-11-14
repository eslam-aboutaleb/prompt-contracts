"""Hypothesis property tests for directional compatibility soundness (T26, AC-17)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from prompt_contracts.compatibility.models import (
    CompatibilityDirection,
    CompatibilityStatus,
)
from prompt_contracts.compatibility.rules import compare_expanded_schemas
from prompt_contracts.errors import ErrorCode, InputValidationError
from prompt_contracts.validation.profile import (
    compile_schema_profile,
    expand_schema_node,
    validate_instance_sanitized,
)


def _is_valid(compiled: object, payload: dict[str, int]) -> bool:
    try:
        validate_instance_sanitized(
            compiled,  # type: ignore[arg-type]
            payload,
            error_cls=InputValidationError,
            error_code=ErrorCode.INPUT_SCHEMA_VIOLATION,
            summary_message="invalid",
        )
    except InputValidationError:
        return False
    return True


@settings(max_examples=50, deadline=None)
@given(
    old_min=st.integers(min_value=0, max_value=30),
    old_max=st.integers(min_value=30, max_value=100),
    new_min=st.integers(min_value=0, max_value=30),
    new_max=st.integers(min_value=30, max_value=100),
    sample_val=st.integers(min_value=-10, max_value=120),
)
def test_integer_bounds_compatibility_matches_instance_acceptance(
    old_min: int,
    old_max: int,
    new_min: int,
    new_max: int,
    sample_val: int,
) -> None:
    old_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["n"],
        "properties": {"n": {"type": "integer", "minimum": old_min, "maximum": old_max}},
    }
    new_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["n"],
        "properties": {"n": {"type": "integer", "minimum": new_min, "maximum": new_max}},
    }
    old_exp, _ = expand_schema_node(old_schema)
    new_exp, _ = expand_schema_node(new_schema)

    in_status, _ = compare_expanded_schemas(
        old_exp, new_exp, direction=CompatibilityDirection.INPUT
    )
    out_status, _ = compare_expanded_schemas(
        old_exp, new_exp, direction=CompatibilityDirection.OUTPUT
    )

    old_compiled = compile_schema_profile(old_schema)
    new_compiled = compile_schema_profile(new_schema)
    old_valid = _is_valid(old_compiled, {"n": sample_val})
    new_valid = _is_valid(new_compiled, {"n": sample_val})

    if in_status is CompatibilityStatus.COMPATIBLE and old_valid:
        assert new_valid
    if out_status is CompatibilityStatus.COMPATIBLE and new_valid:
        assert old_valid
