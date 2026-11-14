"""Execute the actual repository gate with success/failure/skip/cancellation fixtures."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize("status", ["success", "failure", "cancelled", "skipped"])
def test_repository_gate_requires_every_mandatory_job(repo_root: Path, status: str) -> None:
    workflow = (repo_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    jobs = workflow.split("\njobs:\n", 1)[1]
    names = set(re.findall(r"^  ([a-z][a-z-]+):$", jobs, re.MULTILINE))
    gate = jobs.split("  repository-gate:\n", 1)[1]
    needs = re.search(r"needs: \[([^\]]+)\]", gate)
    assert needs is not None
    mandatory = {name.strip() for name in needs.group(1).split(",")}
    assert mandatory == names - {"repository-gate"}
    code_match = re.search(r"python - <<'PY'\n(.*?)          PY", gate, re.DOTALL)
    assert code_match is not None
    code = textwrap.dedent(code_match.group(1))
    for changed in mandatory:
        results = {name: {"result": "success"} for name in mandatory}
        results[changed]["result"] = status
        run = subprocess.run(
            [sys.executable, "-c", code],
            env={**os.environ, "RESULTS": json.dumps(results)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert (run.returncode == 0) == (status == "success"), run.stderr
