"""End-to-end tests running the pinned Promptfoo CLI offline (T29, AC-21, AC-34)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from prompt_contracts import PromptRegistry
from prompt_contracts.adapters.gateway import GatewayCapabilities, to_gateway_request


def _promptfoo_bin(repo_root: Path) -> Path:
    bin_path = repo_root / "tools" / "promptfoo" / "node_modules" / ".bin" / "promptfoo"
    assert bin_path.exists(), f"Promptfoo binary not installed at {bin_path}"
    return bin_path


@pytest.mark.promptfoo
def test_real_promptfoo_cli_passes_offline_suite_and_fails_negative_case(
    repo_root: Path, examples_dir: Path, tmp_path: Path
) -> None:
    promptfoo = _promptfoo_bin(repo_root)
    env = {
        **os.environ,
        "PROMPTFOO_DISABLE_TELEMETRY": "1",
        "PROMPTFOO_DISABLE_UPDATE": "1",
        "CI": "true",
        "PROMPTFOO_PYTHON": sys.executable,
    }

    # 1. Positive suite passes with exit code 0
    out_json = tmp_path / "promptfoo_pass.json"
    proc_pass = subprocess.run(
        [
            str(promptfoo),
            "eval",
            "--no-cache",
            "--no-write",
            "--no-progress-bar",
            "-c",
            str(examples_dir / "promptfoo" / "promptfooconfig.yaml"),
            "-o",
            str(out_json),
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_pass.returncode == 0, f"{proc_pass.stdout}\n{proc_pass.stderr}"
    assert out_json.is_file()
    report = json.loads(out_json.read_text(encoding="utf-8"))
    contract = PromptRegistry.from_directory(
        examples_dir, lock_file=examples_dir / "contracts.lock.json"
    ).get("career.application-answer@1.0.0")
    results = report["results"]["results"]
    assert len(results) == 2
    for row in results:
        assert row["success"] is True
        rendered = contract.render(row["vars"])
        metadata = row["response"]["metadata"]
        assert metadata["rendered_messages"] == rendered.to_messages_list()
        expected_request = to_gateway_request(
            rendered, contract=contract, capabilities=GatewayCapabilities.strict_json_schema()
        )
        assert metadata["gateway_kwargs"] == expected_request.to_kwargs()

    # 2. Negative suite with schema-violating _mock_response fails with non-zero exit code
    neg_cases = tmp_path / "neg_cases.yaml"
    neg_cases.write_text(
        '- description: "Schema-violating response must fail evaluation"\n'
        "  vars:\n"
        '    question: "Describe your database experience."\n'
        '    verified_facts: "fact-1: Maintained PostgreSQL migrations."\n'
        "    _mock_response: '{\"answer\": 12345}'\n"
        "  assert:\n"
        "    - type: is-json\n",
        encoding="utf-8",
    )
    neg_config = tmp_path / "neg_promptfooconfig.yaml"
    neg_config.write_text(
        'description: "Negative test config"\n'
        "prompts:\n"
        '  - "__PROMPT_CONTRACTS_SENTINEL__"\n'
        "providers:\n"
        f"  - id: file://{examples_dir / 'promptfoo' / 'provider.py'}\n"
        "    config:\n"
        '      contracts_root: "."\n'
        '      lock_file: "contracts.lock.json"\n'
        '      contract_ref: "career.application-answer@1.0.0"\n'
        '      mode: "offline"\n'
        "evaluateOptions:\n"
        "  cache: false\n"
        "  maxConcurrency: 1\n"
        f"tests: file://{neg_cases}\n",
        encoding="utf-8",
    )
    proc_fail = subprocess.run(
        [
            str(promptfoo),
            "eval",
            "--no-cache",
            "--no-write",
            "--no-progress-bar",
            "-c",
            str(neg_config),
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_fail.returncode != 0

    # A missing input must fail as a provider error, before the scripted responder.
    neg_cases.write_text(
        '- vars:\n    question: "Missing facts"\n  assert:\n    - type: is-json\n',
        encoding="utf-8",
    )
    missing_report = tmp_path / "missing.json"
    missing = subprocess.run(
        [
            str(promptfoo),
            "eval",
            "--no-cache",
            "--no-write",
            "--no-progress-bar",
            "-c",
            str(neg_config),
            "-o",
            str(missing_report),
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert missing.returncode != 0
    row = json.loads(missing_report.read_text(encoding="utf-8"))["results"]["results"][0]
    assert row["success"] is False
    assert "PC_INPUT_SCHEMA_VIOLATION" in json.dumps(row)
