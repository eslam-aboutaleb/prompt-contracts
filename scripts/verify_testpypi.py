"""Verify TestPyPI serves the candidate bytes, then install its wheel in a fresh environment."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


def verify_index_artifacts(version: str, dist_dir: Path) -> list[tuple[str, bytes]]:
    """Require both index artifacts to match the locally verified distributions."""
    from urllib.parse import urlsplit

    # The CLI also validates the version, before using it in a network URL.
    endpoint = f"https://test.pypi.org/pypi/prompt-contracts/{version}/json"
    for attempt in range(6):
        try:
            with urlopen(endpoint, timeout=30) as response:
                metadata = json.load(response)
            break
        except HTTPError as exc:
            if exc.code != 404 or attempt == 5:
                raise
            time.sleep(5)
    candidates = {
        f"prompt_contracts-{version}-py3-none-any.whl",
        f"prompt_contracts-{version}.tar.gz",
    }
    artifacts: list[tuple[str, bytes]] = []
    for entry in metadata["urls"]:
        name = entry["filename"]
        if name not in candidates:
            continue
        url = urlsplit(entry["url"])
        if url.scheme != "https" or url.hostname != "test-files.pythonhosted.org":
            raise ValueError("Unexpected TestPyPI artifact origin")
        expected = hashlib.sha256((dist_dir / name).read_bytes()).hexdigest()
        if expected != entry["digests"]["sha256"]:
            raise ValueError("TestPyPI artifact digest differs from verified candidate")
        with urlopen(entry["url"], timeout=30) as response:  # noqa: S310
            content = response.read()
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError("Downloaded TestPyPI bytes differ from verified candidate")
        artifacts.append((name, content))
    if {name for name, _ in artifacts} != candidates or len(artifacts) != 2:
        raise ValueError("TestPyPI does not contain exactly the two candidate artifacts")
    return artifacts


def main(argv: list[str] | None = None) -> int:
    import re

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--dist-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
        r"(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?",
        args.version,
    ):
        parser.error("version must be an exact X.Y.Z release or aN/bN/rcN prerelease")
    artifacts = verify_index_artifacts(args.version, args.dist_dir)
    with tempfile.TemporaryDirectory(prefix="pc_testpypi_") as tmp:
        root = Path(tmp)
        wheel = next((name, content) for name, content in artifacts if name.endswith(".whl"))
        wheel_path = root / wheel[0]
        wheel_path.write_bytes(wheel[1])
        environment = root / "venv"
        subprocess.run(["uv", "venv", "--python", sys.executable, str(environment)], check=True)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(wheel_path)], check=True
        )
        subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                "import prompt_contracts; print(prompt_contracts.__version__)",
            ],
            cwd=root,
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
