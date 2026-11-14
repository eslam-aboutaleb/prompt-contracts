"""Run the offline suite with minimum or latest supported dependency versions."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("floor", "latest"), required=True)
    args = parser.parse_args(argv)
    repo = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory(prefix="pc_dependency_") as tmp:
        environment = Path(tmp) / "venv"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        # Sync the locked development tools without changing the caller's environment/lock.
        subprocess.run(
            ["uv", "sync", "--frozen", "--all-groups", "--extra", "gateway"],
            cwd=repo,
            env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(environment)},
            check=True,
        )
        dependencies = (
            ["jsonschema==4.23.0", "referencing==0.35.0"]
            if args.mode == "floor"
            else [
                "jsonschema>=4.23.0,<5",
                "referencing>=0.35.0,<1",
                "llm-gateway-sdk @ git+https://github.com/eslam-aboutaleb/llm-gateway-sdk.git@main",
            ]
        )
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--upgrade", *dependencies],
            cwd=repo,
            check=True,
        )
        subprocess.run(["uv", "pip", "check", "--python", str(python)], check=True)
        subprocess.run(
            [
                str(python),
                "-m",
                "pytest",
                "-m",
                "not live and not promptfoo",
                "--ignore=tests/packaging",
            ],
            cwd=repo,
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
