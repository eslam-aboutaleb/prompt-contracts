"""Property and adversarial tests for RuntimePolicy resource limits (T10, AC-09)."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from prompt_contracts import (
    ErrorCode,
    PromptRegistry,
    ResourceLimitError,
    RuntimePolicy,
)


def test_runtime_policy_enforces_input_rendered_output_and_depth_ceilings(
    examples_dir: Path,
) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")

    with pytest.raises(ResourceLimitError) as in_exc:
        contract.validate_inputs(
            {
                "question": "Q" * 100,
                "verified_facts": "F" * 100,
            },
            policy=RuntimePolicy(max_input_bytes=64),
        )
    assert in_exc.value.code == ErrorCode.RESOURCE_SIZE_EXCEEDED

    with pytest.raises(ResourceLimitError) as out_exc:
        contract.validate_output(
            '{"answer": "' + ("A" * 200) + '", "evidence_ids": ["f1"], "needs_review": false}',
            policy=RuntimePolicy(max_response_bytes=64),
        )
    assert out_exc.value.code == ErrorCode.RESOURCE_SIZE_EXCEEDED


@settings(max_examples=30, deadline=None)
@given(depth=st.integers(min_value=10, max_value=45))
def test_deep_json_never_raises_unhandled_recursion_error(depth: int) -> None:
    from prompt_contracts.validation.json_io import parse_strict_json

    payload = ("{" + '"a":') * depth + "1" + ("}" * depth)
    with pytest.raises(ResourceLimitError) as exc_info:
        parse_strict_json(payload, max_bytes=65536, max_depth=8)
    assert exc_info.value.code == ErrorCode.NESTING_DEPTH_EXCEEDED
