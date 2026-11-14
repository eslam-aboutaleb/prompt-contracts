"""Strict output parsing and schema/length validation without coercion or repair."""

from __future__ import annotations

from typing import Any

from prompt_contracts.errors import (
    ErrorCode,
    OutputValidationError,
    ResourceLimitError,
    ValidationIssue,
)
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    OutputMode,
    OutputSpec,
    RuntimePolicy,
    thaw_json_value,
)
from prompt_contracts.validation.json_io import parse_strict_json
from prompt_contracts.validation.profile import CompiledSchema, validate_instance_sanitized

__all__ = ["validate_contract_output"]


def validate_contract_output(
    raw_output: str,
    output_spec: OutputSpec,
    compiled_output_schema: CompiledSchema | None = None,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    contract_ref: str | None = None,
) -> Any:
    """Validate ``raw_output`` according to ``output_spec`` and ``policy``.

    - For ``OutputMode.TEXT``, enforces UTF-8 byte ceiling and code-point length bounds,
      returning ``raw_output`` with whitespace preserved.
    - For ``OutputMode.JSON``, rejects Markdown fences and surrounding prose, parses one
      strict JSON document, validates against ``compiled_output_schema``, and returns a
      fresh mutable deep copy of the parsed JSON structure.
    """
    if type(raw_output) is not str:
        raise OutputValidationError(
            "Contract output to validate must be a string",
            code=ErrorCode.OUTPUT_SCHEMA_VIOLATION,
            contract_ref=contract_ref,
        )

    try:
        utf8_len = len(raw_output.encode("utf-8", errors="strict"))
    except UnicodeEncodeError:
        raise OutputValidationError(
            "Contract output is not valid UTF-8",
            code=ErrorCode.JSON_SYNTAX_INVALID
            if output_spec.mode == OutputMode.JSON
            else ErrorCode.OUTPUT_SCHEMA_VIOLATION,
            contract_ref=contract_ref,
        ) from None
    if utf8_len > policy.max_response_bytes:
        raise ResourceLimitError(
            f"Response UTF-8 size ({utf8_len} bytes) exceeds "
            f"limit ({policy.max_response_bytes} bytes)",
            code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
            contract_ref=contract_ref,
        )

    if output_spec.mode == OutputMode.TEXT:
        min_len = output_spec.min_length if output_spec.min_length is not None else 0
        max_len = (
            output_spec.max_length
            if output_spec.max_length is not None
            else policy.max_response_bytes
        )
        codepoint_len = len(raw_output)
        if codepoint_len < min_len:
            raise OutputValidationError(
                f"Text output length ({codepoint_len}) is shorter than minimum ({min_len})",
                code=ErrorCode.OUTPUT_TEXT_LENGTH_VIOLATION,
                contract_ref=contract_ref,
                issues=(
                    ValidationIssue(
                        code="minLength",
                        message=f"Text length is less than minimum {min_len}",
                        data_path="$",
                        schema_path="$.output.min_length",
                    ),
                ),
            )
        if codepoint_len > max_len:
            raise OutputValidationError(
                f"Text output length ({codepoint_len}) exceeds maximum ({max_len})",
                code=ErrorCode.OUTPUT_TEXT_LENGTH_VIOLATION,
                contract_ref=contract_ref,
                issues=(
                    ValidationIssue(
                        code="maxLength",
                        message=f"Text length exceeds maximum {max_len}",
                        data_path="$",
                        schema_path="$.output.max_length",
                    ),
                ),
            )
        return raw_output

    if compiled_output_schema is None:
        raise OutputValidationError(
            "JSON output mode requires a compiled output schema",
            code=ErrorCode.OUTPUT_SCHEMA_VIOLATION,
            contract_ref=contract_ref,
        )

    parsed = parse_strict_json(
        raw_output,
        max_bytes=policy.max_response_bytes,
        max_depth=policy.max_nesting_depth,
        error_cls=OutputValidationError,
        contract_ref=contract_ref,
        reject_fences_and_prose=True,
    )

    validate_instance_sanitized(
        compiled_output_schema,
        parsed,
        policy=policy,
        error_cls=OutputValidationError,
        error_code=ErrorCode.OUTPUT_SCHEMA_VIOLATION,
        summary_message="Contract JSON output validation failed",
        contract_ref=contract_ref,
    )
    return thaw_json_value(parsed)
