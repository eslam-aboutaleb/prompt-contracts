"""Privacy and zero-leakage verification across exceptions, reprs, and CLI stderr (T10, AC-25)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_contracts import (
    InputValidationError,
    OutputValidationError,
    PromptContractError,
    PromptRegistry,
)
from prompt_contracts.cli.main import main as cli_main

SECRET_VALUE = "SYNTHETIC_SECRET_MARKER_VALUE_7731"
SECRET_KEY = "SYNTHETIC_SECRET_MARKER_KEY_9942"


def _assert_no_secret_leak(exc: PromptContractError) -> None:
    serialized = json.dumps(exc.to_dict())
    for surface in (str(exc), repr(exc), exc.to_json(), serialized):
        assert SECRET_VALUE not in surface
        assert SECRET_KEY not in surface
    assert exc.__cause__ is None
    assert exc.__suppress_context__ is True


def test_input_validation_errors_never_leak_rejected_values_or_unknown_keys(
    examples_dir: Path,
) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")

    # 1. Invalid type / constraint with secret value
    with pytest.raises(InputValidationError) as exc_info1:
        contract.validate_inputs(
            {
                "question": "",
                "verified_facts": SECRET_VALUE,
            }
        )
    _assert_no_secret_leak(exc_info1.value)

    # 2. Unknown property containing secret in both key and value
    with pytest.raises(InputValidationError) as exc_info2:
        contract.validate_inputs(
            {
                "question": "Valid question?",
                "verified_facts": "fact-1: Backend engineer",
                SECRET_KEY: SECRET_VALUE,
            }
        )
    _assert_no_secret_leak(exc_info2.value)


def test_output_errors_never_leak_raw_model_output(examples_dir: Path) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")

    with pytest.raises(OutputValidationError) as parse_exc:
        contract.validate_output(f"Malformed JSON containing {SECRET_VALUE}")
    _assert_no_secret_leak(parse_exc.value)

    with pytest.raises(OutputValidationError) as val_exc:
        contract.validate_output(
            json.dumps(
                {
                    "answer": SECRET_VALUE,
                    "evidence_ids": [],
                    "needs_review": False,
                    SECRET_KEY: SECRET_VALUE,
                }
            )
        )
    _assert_no_secret_leak(val_exc.value)


def test_cli_render_error_never_leaks_secret_to_stderr(
    examples_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    bad_input_file = tmp_path / "bad_input.json"
    bad_input_file.write_text(
        json.dumps(
            {
                "question": "Valid?",
                "verified_facts": "fact-1: Profile",
                SECRET_KEY: SECRET_VALUE,
            }
        ),
        encoding="utf-8",
    )
    code = cli_main(
        [
            "render",
            str(examples_dir / "contracts"),
            "--lock",
            str(examples_dir / "contracts.lock.json"),
            "--ref",
            "career.application-answer@1.0.0",
            "--input-file",
            str(bad_input_file),
        ]
    )
    assert code == 3
    captured = capsys.readouterr()
    assert SECRET_VALUE not in captured.err
    assert SECRET_KEY not in captured.err
    assert SECRET_VALUE not in captured.out
    assert SECRET_KEY not in captured.out
