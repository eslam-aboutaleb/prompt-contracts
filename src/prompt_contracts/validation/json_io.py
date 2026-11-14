"""Strict, bounded JSON parser rejecting duplicate keys, non-finite numbers, and excess depth."""

from __future__ import annotations

import json
import math
from typing import Any

from prompt_contracts.errors import (
    ErrorCode,
    OutputValidationError,
    PromptContractError,
    ResourceLimitError,
)
from prompt_contracts.types import SPEC_MAX_NESTING_DEPTH

__all__ = [
    "check_nesting_depth_before_parse",
    "detect_fences_or_surrounding_prose",
    "parse_strict_json",
]


class _DuplicateKeySignalError(Exception):
    """Internal sentinel for duplicate object keys during ``json.loads``."""


class _NonFiniteNumberSignalError(Exception):
    """Internal sentinel for NaN / Infinity tokens during ``json.loads``."""


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeySignalError
        result[key] = value
    return result


def _reject_nonfinite_constant(token: str) -> Any:
    raise _NonFiniteNumberSignalError(token)


def check_nesting_depth_before_parse(
    text: str,
    *,
    max_depth: int,
    contract_ref: str | None = None,
    source_path: str | None = None,
) -> None:
    """Scan JSON structural brackets outside string literals to enforce ``max_depth`` safely.

    Prevents Python's C/stdlib JSON decoder from raising a raw ``RecursionError`` on
    adversarially deep inputs.
    """
    depth = 0
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch in "{[":
                depth += 1
                if depth > max_depth:
                    raise ResourceLimitError(
                        f"JSON structure exceeds maximum nesting depth of {max_depth}",
                        code=ErrorCode.NESTING_DEPTH_EXCEEDED,
                        contract_ref=contract_ref,
                        source_path=source_path,
                    )
            elif ch in "}]" and depth > 0:
                depth -= 1


def detect_fences_or_surrounding_prose(text: str) -> str | None:
    """Return a safe reason if ``text`` starts with Markdown fences or has trailing prose."""
    stripped = text.strip()
    if stripped.startswith("```") or stripped.endswith("```"):
        return "Markdown code fences are not permitted in JSON output mode"
    return None


def _verify_parsed_depth_and_finiteness(
    value: Any,
    *,
    max_depth: int,
    contract_ref: str | None,
    source_path: str | None,
    error_cls: type[PromptContractError],
    _depth: int = 0,
) -> None:
    if isinstance(value, str):
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise error_cls(
                "JSON string contains invalid UTF-8 surrogates",
                code=ErrorCode.JSON_SYNTAX_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            ) from None
        return
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise error_cls(
                "Non-finite floating-point value is not permitted in strict JSON",
                code=ErrorCode.JSON_NONFINITE_NUMBER,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        return
    if _depth >= max_depth:
        raise ResourceLimitError(
            f"JSON value exceeds maximum nesting depth of {max_depth}",
            code=ErrorCode.NESTING_DEPTH_EXCEEDED,
            contract_ref=contract_ref,
            source_path=source_path,
        )
    if isinstance(value, dict):
        for key in value:
            _verify_parsed_depth_and_finiteness(
                key,
                max_depth=max_depth,
                contract_ref=contract_ref,
                source_path=source_path,
                error_cls=error_cls,
                _depth=_depth + 1,
            )
        for v in value.values():
            _verify_parsed_depth_and_finiteness(
                v,
                max_depth=max_depth,
                contract_ref=contract_ref,
                source_path=source_path,
                error_cls=error_cls,
                _depth=_depth + 1,
            )
    elif isinstance(value, list):
        for item in value:
            _verify_parsed_depth_and_finiteness(
                item,
                max_depth=max_depth,
                contract_ref=contract_ref,
                source_path=source_path,
                error_cls=error_cls,
                _depth=_depth + 1,
            )


def parse_strict_json(
    raw: str | bytes,
    *,
    max_bytes: int,
    max_depth: int = SPEC_MAX_NESTING_DEPTH,
    error_cls: type[PromptContractError] = OutputValidationError,
    contract_ref: str | None = None,
    source_path: str | None = None,
    reject_fences_and_prose: bool = False,
) -> Any:
    """Parse one strict JSON document within byte and depth limits.

    Rejects duplicate object keys, NaN/Infinity constants, trailing prose, and Markdown
    fences without exposing rejected content in raised errors.
    """
    if isinstance(raw, bytes):
        if len(raw) > max_bytes:
            raise ResourceLimitError(
                f"JSON payload size ({len(raw)} bytes) exceeds limit ({max_bytes} bytes)",
                code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise error_cls(
                "JSON payload is not valid UTF-8",
                code=ErrorCode.JSON_SYNTAX_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            ) from None
    elif isinstance(raw, str):
        try:
            utf8_len = len(raw.encode("utf-8", errors="strict"))
        except UnicodeEncodeError:
            raise error_cls(
                "JSON payload is not valid UTF-8",
                code=ErrorCode.JSON_SYNTAX_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            ) from None
        if utf8_len > max_bytes:
            raise ResourceLimitError(
                f"JSON payload size ({utf8_len} bytes) exceeds limit ({max_bytes} bytes)",
                code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        text = raw
    else:
        raise error_cls(
            "JSON payload must be str or bytes",
            code=ErrorCode.JSON_SYNTAX_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    if reject_fences_and_prose:
        fence_reason = detect_fences_or_surrounding_prose(text)
        if fence_reason is not None:
            raise error_cls(
                fence_reason,
                code=ErrorCode.OUTPUT_FENCE_OR_PROSE_REJECTED,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    check_nesting_depth_before_parse(
        text,
        max_depth=max_depth,
        contract_ref=contract_ref,
        source_path=source_path,
    )

    stripped = text.strip()
    if not stripped:
        raise error_cls(
            "JSON payload is empty",
            code=ErrorCode.JSON_SYNTAX_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_pairs,
        parse_constant=_reject_nonfinite_constant,
    )
    try:
        parsed, end_idx = decoder.raw_decode(stripped)
    except _DuplicateKeySignalError:
        raise error_cls(
            "Duplicate object key in JSON document",
            code=ErrorCode.JSON_DUPLICATE_KEY,
            contract_ref=contract_ref,
            source_path=source_path,
        ) from None
    except _NonFiniteNumberSignalError:
        raise error_cls(
            "Non-finite number token (NaN or Infinity) in JSON document",
            code=ErrorCode.JSON_NONFINITE_NUMBER,
            contract_ref=contract_ref,
            source_path=source_path,
        ) from None
    except RecursionError:
        raise ResourceLimitError(
            f"JSON document exceeds maximum nesting depth of {max_depth}",
            code=ErrorCode.NESTING_DEPTH_EXCEEDED,
            contract_ref=contract_ref,
            source_path=source_path,
        ) from None
    except json.JSONDecodeError as exc:
        if reject_fences_and_prose and not stripped.startswith(
            (
                "{",
                "[",
                '"',
                "-",
                "0",
                "1",
                "2",
                "3",
                "4",
                "5",
                "6",
                "7",
                "8",
                "9",
                "t",
                "f",
                "n",
            )
        ):
            raise error_cls(
                "Leading prose or non-JSON prefix is not permitted",
                code=ErrorCode.OUTPUT_FENCE_OR_PROSE_REJECTED,
                contract_ref=contract_ref,
                source_path=source_path,
                line=exc.lineno,
                column=exc.colno,
            ) from None
        raise error_cls(
            "Malformed JSON document",
            code=ErrorCode.JSON_SYNTAX_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
            line=exc.lineno,
            column=exc.colno,
        ) from None
    except ValueError:
        raise error_cls(
            "JSON number exceeds the supported numeric representation",
            code=ErrorCode.JSON_SYNTAX_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        ) from None

    trailing = stripped[end_idx:].strip()
    if trailing:
        if reject_fences_and_prose:
            raise error_cls(
                "Trailing prose or extra content after JSON document is not permitted",
                code=ErrorCode.OUTPUT_FENCE_OR_PROSE_REJECTED,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        raise error_cls(
            "Extra data after top-level JSON document",
            code=ErrorCode.JSON_SYNTAX_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    _verify_parsed_depth_and_finiteness(
        parsed,
        max_depth=max_depth,
        contract_ref=contract_ref,
        source_path=source_path,
        error_cls=error_cls,
    )
    return parsed
