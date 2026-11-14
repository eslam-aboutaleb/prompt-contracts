"""Integration tests for prompt-contracts diff command and exit codes (T27, AC-22)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from prompt_contracts.cli.commands import (
    EXIT_COMPATIBILITY_FAILURE,
    EXIT_SUCCESS,
)
from prompt_contracts.cli.main import main


def test_cli_diff_compatible_and_breaking_exit_codes(
    examples_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    contracts_dir = tmp_path / "contracts"
    shutil.copytree(examples_dir / "contracts", contracts_dir)

    # Create 1.1.0 with an optional input field (compatible) and modified template text
    v1_dir = contracts_dir / "career.application-answer" / "1.0.0"
    v2_dir = contracts_dir / "career.application-answer" / "1.1.0"
    shutil.copytree(v1_dir, v2_dir)

    (v2_dir / "contract.toml").write_text(
        (v2_dir / "contract.toml")
        .read_text(encoding="utf-8")
        .replace('version = "1.0.0"', 'version = "1.1.0"'),
        encoding="utf-8",
    )
    input_schema = json.loads((v2_dir / "input.schema.json").read_text(encoding="utf-8"))
    input_schema["properties"]["optional_note"] = {
        "type": "string",
        "maxLength": 200,
    }
    (v2_dir / "input.schema.json").write_text(
        json.dumps(input_schema, indent=2) + "\n", encoding="utf-8"
    )
    (v2_dir / "user.md").write_text(
        (v2_dir / "user.md").read_text(encoding="utf-8") + "\nKeep tone professional.\n",
        encoding="utf-8",
    )

    # Structurally compatible -> exit code 0
    rc = main(["diff", str(v1_dir), str(v2_dir), "--format", "json"])
    assert rc == EXIT_SUCCESS
    report = json.loads(capsys.readouterr().out)
    assert report["overall_status"] == "compatible"
    assert report["behavioral_review_required"] is True

    # An uncertain schema proof must also block compatible-only promotion.
    output_schema = json.loads((v2_dir / "output.schema.json").read_text(encoding="utf-8"))
    output_schema["properties"]["answer"]["const"] = "fixed answer"
    (v2_dir / "output.schema.json").write_text(json.dumps(output_schema), encoding="utf-8")
    assert (
        main(["diff", str(v1_dir), str(v2_dir), "--format", "json"]) == EXIT_COMPATIBILITY_FAILURE
    )
    unknown_report = json.loads(capsys.readouterr().out)
    assert unknown_report["overall_status"] == "unknown"

    # Make 2.0.0 breaking by adding a new required input field
    v3_dir = contracts_dir / "career.application-answer" / "2.0.0"
    shutil.copytree(v1_dir, v3_dir)
    (v3_dir / "contract.toml").write_text(
        (v3_dir / "contract.toml")
        .read_text(encoding="utf-8")
        .replace('version = "1.0.0"', 'version = "2.0.0"'),
        encoding="utf-8",
    )
    input_schema_v3 = json.loads((v3_dir / "input.schema.json").read_text(encoding="utf-8"))
    input_schema_v3["properties"]["new_required"] = {"type": "string"}
    input_schema_v3["required"].append("new_required")
    (v3_dir / "input.schema.json").write_text(
        json.dumps(input_schema_v3, indent=2) + "\n", encoding="utf-8"
    )

    rc_break = main(["diff", str(v1_dir), str(v3_dir)])
    assert rc_break == EXIT_COMPATIBILITY_FAILURE
    capsys.readouterr()

    # With --policy report-only, even breaking exits 0
    rc_report_only = main(["diff", str(v1_dir), str(v3_dir), "--policy", "report-only"])
    assert rc_report_only == EXIT_SUCCESS
    capsys.readouterr()
