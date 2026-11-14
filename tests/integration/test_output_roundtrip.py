"""Integration tests for Contract.validate_output on JSON and text contracts (T09)."""

from __future__ import annotations

from pathlib import Path

import pytest

from prompt_contracts import (
    Contract,
    OutputValidationError,
    PromptRegistry,
)


def test_example_contract_output_validation_roundtrip(examples_dir: Path) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")
    valid = contract.validate_output(
        '{"answer": "I built deterministic prompt pipelines.", '
        '"evidence_ids": ["fact-1"], "needs_review": false}'
    )
    assert valid["needs_review"] is False

    with pytest.raises(OutputValidationError):
        contract.validate_output(
            '{"answer": "dup", "answer": "dup2", "evidence_ids": ["fact-1"], "needs_review": false}'
        )

    with pytest.raises(OutputValidationError):
        contract.validate_output(
            '{"answer": "ok", "evidence_ids": ["fact-1"], "needs_review": false, "extra": 1}'
        )


def test_text_mode_contract_bundle_roundtrip(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "demo.text-contract" / "1.0.0"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "contract.toml").write_text(
        "format_version = 1\n"
        'name = "demo.text-contract"\n'
        'version = "1.0.0"\n'
        'description = "Text output contract."\n'
        'renderer = "placeholders-v1"\n'
        'input_schema = "input.schema.json"\n\n'
        "[output]\n"
        'mode = "text"\n'
        "min_length = 4\n"
        "max_length = 50\n\n"
        "[[messages]]\n"
        'role = "user"\n'
        'file = "user.md"\n',
        encoding="utf-8",
    )
    (bundle_dir / "user.md").write_text("Summarize: {{topic}}", encoding="utf-8")
    (bundle_dir / "input.schema.json").write_text(
        '{"$schema":"https://json-schema.org/draft/2020-12/schema","type":"object",'
        '"additionalProperties":false,"required":["topic"],'
        '"properties":{"topic":{"type":"string","minLength":1}}}',
        encoding="utf-8",
    )
    contract = Contract.from_directory(bundle_dir)
    assert contract.output_schema is None
    assert contract.validate_output("Concise summary.") == "Concise summary."
    with pytest.raises(OutputValidationError):
        contract.validate_output("abc")
