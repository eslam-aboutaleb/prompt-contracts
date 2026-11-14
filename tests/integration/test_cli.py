"""Integration tests for CLI commands lint, lock, verify, and render (T14, AC-22)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from prompt_contracts.cli.commands import (
    EXIT_LOCK_OR_IDENTITY_ERROR,
    EXIT_SUCCESS,
    EXIT_USAGE_ERROR,
    EXIT_VALIDATION_ERROR,
)
from prompt_contracts.cli.main import main


def test_cli_stdin_is_read_with_a_limit(examples_dir: Path) -> None:
    import io

    from prompt_contracts import ResourceLimitError, RuntimePolicy
    from prompt_contracts.cli.commands import run_render_command

    class BoundedInput(io.StringIO):
        def read(self, size: int | None = -1) -> str:
            assert size == 65
            return super().read(size)

    with pytest.raises(ResourceLimitError):
        run_render_command(
            examples_dir,
            lock_path=examples_dir / "contracts.lock.json",
            ref_str="career.application-answer@1.0.0",
            input_file="-",
            stdin=BoundedInput(" " * 1000),
            stdout=io.StringIO(),
            policy=RuntimePolicy(max_input_bytes=64),
        )


def test_cli_lint_verify_and_render_text_and_json_formats(
    examples_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contracts_dir = str(examples_dir / "contracts")
    lock_path = str(examples_dir / "contracts.lock.json")
    input_file = str(examples_dir / "inputs" / "application-answer.json")

    assert main(["lint", contracts_dir]) == EXIT_SUCCESS
    out = capsys.readouterr().out
    assert "career.application-answer@1.0.0" in out

    assert main(["lint", contracts_dir, "--format", "json"]) == EXIT_SUCCESS
    json_out = json.loads(capsys.readouterr().out)
    assert json_out["status"] == "ok"

    assert main(["verify", contracts_dir, "--lock", lock_path]) == EXIT_SUCCESS
    capsys.readouterr()

    assert main(["verify", contracts_dir, "--lock", lock_path, "--format", "json"]) == EXIT_SUCCESS
    verify_json = json.loads(capsys.readouterr().out)
    assert verify_json["status"] == "ok"

    assert (
        main(
            [
                "render",
                contracts_dir,
                "--lock",
                lock_path,
                "--ref",
                "career.application-answer@1.0.0",
                "--input-file",
                input_file,
                "--format",
                "json",
            ]
        )
        == EXIT_SUCCESS
    )
    render_json = json.loads(capsys.readouterr().out)
    assert render_json["contract_ref"] == "career.application-answer@1.0.0"
    assert len(render_json["messages"]) == 2


def test_cli_exit_codes_for_lock_contract_and_usage_errors(
    examples_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Usage error -> exit code 2
    assert main(["unknown-subcommand"]) == EXIT_USAGE_ERROR
    capsys.readouterr()

    # Copy contracts and test lock generation + overwrite denial -> exit code 4
    contracts_copy = tmp_path / "contracts"
    shutil.copytree(examples_dir / "contracts", contracts_copy)
    lock_file = tmp_path / "contracts.lock.json"

    assert main(["lock", str(contracts_copy), "--output", str(lock_file)]) == EXIT_SUCCESS
    capsys.readouterr()

    # Modify a template on disk and attempt lock without --update -> exit code 4
    user_md = contracts_copy / "career.application-answer" / "1.0.0" / "user.md"
    user_md.write_text(
        user_md.read_text(encoding="utf-8") + "\nUpdated line.\n",
        encoding="utf-8",
    )
    assert (
        main(["lock", str(contracts_copy), "--output", str(lock_file)])
        == EXIT_LOCK_OR_IDENTITY_ERROR
    )
    capsys.readouterr()

    assert (
        main(["lock", str(contracts_copy), "--output", str(lock_file), "--update"]) == EXIT_SUCCESS
    )
    capsys.readouterr()

    # Corrupt contract manifest -> exit code 3
    manifest_file = contracts_copy / "career.application-answer" / "1.0.0" / "contract.toml"
    manifest_file.write_text("format_version = 999\n", encoding="utf-8")
    assert main(["lint", str(contracts_copy)]) == EXIT_VALIDATION_ERROR
    capsys.readouterr()

    assert main(["lint", str(contracts_copy), "--format", "json"]) == EXIT_VALIDATION_ERROR
    err_json = json.loads(capsys.readouterr().out)
    assert err_json["status"] == "error"


def test_cli_render_text_and_lock_json_formats(
    examples_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contracts_dir = str(examples_dir / "contracts")
    lock_path = str(examples_dir / "contracts.lock.json")
    input_file = str(examples_dir / "inputs" / "application-answer.json")

    assert (
        main(
            [
                "render",
                contracts_dir,
                "--lock",
                lock_path,
                "--ref",
                "career.application-answer@1.0.0",
                "--input-file",
                input_file,
                "--format",
                "text",
            ]
        )
        == EXIT_SUCCESS
    )
    text_out = capsys.readouterr().out
    assert "[system]" in text_out
    assert "[user]" in text_out

    out_lock = tmp_path / "out.lock.json"
    assert (
        main(["lock", contracts_dir, "--output", str(out_lock), "--format", "json"]) == EXIT_SUCCESS
    )
    lock_json = json.loads(capsys.readouterr().out)
    assert lock_json["command"] == "lock"
    assert lock_json["contract_count"] == 1
