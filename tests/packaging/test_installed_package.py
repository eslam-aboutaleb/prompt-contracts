"""Tests for wheel/sdist contents and isolated installation outside the repo checkout (T15,
AC-30).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from scripts.verify_distribution import (
    inspect_sdist,
    inspect_wheel,
    smoke_test_wheel_install,
)


def test_build_and_verify_wheel_and_sdist_in_isolated_environment(
    repo_root: Path, tmp_path: Path
) -> None:
    dist_dir = tmp_path / "dist"
    proc = subprocess.run(
        ["uv", "build", "--out-dir", str(dist_dir)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr

    wheels = sorted(dist_dir.glob("prompt_contracts-*.whl"))
    sdists = sorted(dist_dir.glob("prompt_contracts-*.tar.gz"))
    assert len(wheels) == 1
    assert len(sdists) == 1

    assert inspect_wheel(wheels[0]) == []
    assert inspect_sdist(sdists[0]) == []
    assert smoke_test_wheel_install(wheels[0], repo_root) == []
    assert smoke_test_wheel_install(sdists[0], repo_root) == []
    assert smoke_test_wheel_install(wheels[0], repo_root, with_gateway=True) == []
