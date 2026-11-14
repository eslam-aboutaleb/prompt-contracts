"""Strict input validation before template rendering."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from prompt_contracts.errors import ErrorCode, InputValidationError, ResourceLimitError
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    RuntimePolicy,
    freeze_json_value,
    serialize_compact_json,
    thaw_json_value,
)
from prompt_contracts.validation.profile import CompiledSchema, validate_instance_sanitized

__all__ = ["validate_contract_inputs"]


def validate_contract_inputs(
    inputs: Any,
    compiled_schema: CompiledSchema,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    contract_ref: str | None = None,
) -> Mapping[str, Any]:
    """Validate ``inputs`` against resource limits and ``compiled_schema`` without coercion.

    Returns a deeply immutable view of the validated inputs.
    """
    if not isinstance(inputs, Mapping) or type(inputs) not in (dict, MappingProxyType):
        raise InputValidationError(
            "Contract inputs must be a JSON object (dict)",
            code=ErrorCode.INPUT_NOT_OBJECT,
            contract_ref=contract_ref,
        )

    for key in inputs:
        if type(key) is not str:
            raise InputValidationError(
                "Contract input keys must be strings",
                code=ErrorCode.INPUT_VALUE_INVALID,
                contract_ref=contract_ref,
            )

    try:
        frozen = freeze_json_value(
            inputs, max_depth=policy.max_nesting_depth, max_bytes=policy.max_input_bytes
        )
    except InputValidationError as exc:
        raise InputValidationError(
            exc.safe_message,
            code=exc.code,
            contract_ref=contract_ref,
        ) from None
    except ResourceLimitError as exc:
        raise ResourceLimitError(
            exc.safe_message,
            code=exc.code,
            contract_ref=contract_ref,
        ) from None

    serialized = serialize_compact_json(frozen, max_depth=policy.max_nesting_depth)
    utf8_len = len(serialized.encode("utf-8"))
    if utf8_len > policy.max_input_bytes:
        raise ResourceLimitError(
            f"Serialized input payload ({utf8_len} bytes) "
            f"exceeds limit ({policy.max_input_bytes} bytes)",
            code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
            contract_ref=contract_ref,
        )

    validate_instance_sanitized(
        compiled_schema,
        thaw_json_value(frozen),
        policy=policy,
        error_cls=InputValidationError,
        error_code=ErrorCode.INPUT_SCHEMA_VIOLATION,
        summary_message="Contract input validation failed",
        contract_ref=contract_ref,
    )
    assert isinstance(frozen, Mapping)
    return frozen
