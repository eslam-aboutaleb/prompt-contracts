"""Unit tests for strict JSON parser, duplicate key rejection, and depth limits (T05)."""

from __future__ import annotations

import pytest

from prompt_contracts.errors import (
    ErrorCode,
    OutputValidationError,
    ResourceLimitError,
)
from prompt_contracts.validation.json_io import parse_strict_json


def test_parse_strict_json_accepts_valid_json() -> None:
    parsed = parse_strict_json(
        '{"answer": "Ready", "confidence": 0.9, "tags": ["a", "b"]}',
        max_bytes=1024,
        max_depth=8,
    )
    assert parsed == {"answer": "Ready", "confidence": 0.9, "tags": ["a", "b"]}


def test_parse_strict_json_rejects_duplicate_keys() -> None:
    with pytest.raises(OutputValidationError) as exc_info:
        parse_strict_json(
            '{"answer": "first", "answer": "second"}',
            max_bytes=1024,
            max_depth=8,
        )
    assert exc_info.value.code == ErrorCode.JSON_DUPLICATE_KEY
    assert "first" not in str(exc_info.value)
    assert "second" not in str(exc_info.value)


@pytest.mark.parametrize(
    "raw_payload",
    [
        '{"score": NaN}',
        '{"score": Infinity}',
        '{"score": -Infinity}',
    ],
)
def test_parse_strict_json_rejects_non_finite_constants(raw_payload: str) -> None:
    with pytest.raises(OutputValidationError) as exc_info:
        parse_strict_json(raw_payload, max_bytes=1024, max_depth=8)
    assert exc_info.value.code == ErrorCode.JSON_NONFINITE_NUMBER


@pytest.mark.parametrize(
    "fenced_or_prose",
    [
        '```json\n{"answer": "ok"}\n```',
        'Here is the JSON:\n{"answer": "ok"}',
        '{"answer": "ok"}\nTrailing text',
        "",
        "   ",
    ],
)
def test_parse_strict_json_rejects_fences_and_surrounding_prose(
    fenced_or_prose: str,
) -> None:
    with pytest.raises(OutputValidationError) as exc_info:
        parse_strict_json(
            fenced_or_prose, max_bytes=1024, max_depth=8, reject_fences_and_prose=True
        )
    assert exc_info.value.code in (
        ErrorCode.OUTPUT_FENCE_OR_PROSE_REJECTED,
        ErrorCode.JSON_SYNTAX_INVALID,
    )


def test_parse_strict_json_rejects_excessive_nesting_before_recursion_error() -> None:
    deep_json = ("[" * 40) + "1" + ("]" * 40)
    with pytest.raises(ResourceLimitError) as exc_info:
        parse_strict_json(deep_json, max_bytes=4096, max_depth=16)
    assert exc_info.value.code == ErrorCode.NESTING_DEPTH_EXCEEDED


def test_parse_strict_json_rejects_payload_exceeding_byte_budget() -> None:
    large = '{"a": "' + ("x" * 200) + '"}'
    with pytest.raises(ResourceLimitError) as exc_info:
        parse_strict_json(large, max_bytes=64, max_depth=8)
    assert exc_info.value.code == ErrorCode.RESOURCE_SIZE_EXCEEDED


@pytest.mark.parametrize("raw", ['"\ud800"', '"\\ud800"', '{"\\udfff": 1}'])
def test_parse_strict_json_rejects_surrogates_without_raw_encoding_errors(raw: str) -> None:
    with pytest.raises(OutputValidationError) as exc_info:
        parse_strict_json(raw, max_bytes=1024)
    assert exc_info.value.code == ErrorCode.JSON_SYNTAX_INVALID
    assert exc_info.value.__suppress_context__ is True


def test_parse_strict_json_translates_integer_decoder_limit() -> None:
    import sys

    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("Interpreter integer conversion limit is disabled")
    with pytest.raises(OutputValidationError) as exc_info:
        parse_strict_json("9" * (limit + 1), max_bytes=limit + 2)
    assert exc_info.value.code == ErrorCode.JSON_SYNTAX_INVALID
    assert exc_info.value.__suppress_context__ is True
