"""Integration tests for contract loading, input validation, and message rendering (T08)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_contracts import (
    ErrorCode,
    MessageRole,
    PromptRegistry,
    ResourceLimitError,
    RuntimePolicy,
)


def test_example_contract_render_roundtrip(examples_dir: Path) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")
    inputs = json.loads(
        (examples_dir / "inputs" / "application-answer.json").read_text(encoding="utf-8")
    )
    rendered = contract.render(inputs)
    assert str(rendered.contract_ref) == "career.application-answer@1.0.0"
    assert len(rendered.messages) == 2
    assert rendered.messages[0].role is MessageRole.SYSTEM
    assert rendered.messages[1].role is MessageRole.USER
    assert inputs["question"] in rendered.messages[1].content
    assert inputs["verified_facts"] in rendered.messages[1].content


def test_render_enforces_max_rendered_bytes(examples_dir: Path) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")
    inputs = json.loads(
        (examples_dir / "inputs" / "application-answer.json").read_text(encoding="utf-8")
    )
    tiny_policy = RuntimePolicy(max_rendered_bytes=64)
    with pytest.raises(ResourceLimitError) as exc_info:
        contract.render(inputs, policy=tiny_policy)
    assert exc_info.value.code == ErrorCode.RESOURCE_SIZE_EXCEEDED
