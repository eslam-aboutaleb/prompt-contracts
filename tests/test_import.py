"""Verify public package surface, import isolation, and boundary invariants (T03)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import prompt_contracts


def test_public_exports_and_version() -> None:
    assert prompt_contracts.__version__ == "0.2.0"
    for symbol in prompt_contracts.__all__:
        assert hasattr(prompt_contracts, symbol), f"Missing export: {symbol}"


def test_core_import_does_not_load_optional_adapters_or_gateway_sdk(
    repo_root: Path,
) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys, prompt_contracts; "
                "assert 'llm_gateway_sdk' not in sys.modules; "
                "assert 'prompt_contracts.adapters.gateway' not in sys.modules; "
                "assert 'prompt_contracts.adapters.promptfoo' not in sys.modules"
            ),
        ],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr


def test_import_boundaries_script(repo_root: Path) -> None:
    script = repo_root / "scripts" / "check_import_boundaries.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--src", str(repo_root / "src")],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
