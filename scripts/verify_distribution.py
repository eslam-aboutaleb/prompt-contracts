"""Verify built wheel and sdist contents and smoke-test an isolated installation."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

REQUIRED_WHEEL_SUFFIXES: tuple[str, ...] = (
    "prompt_contracts/__init__.py",
    "prompt_contracts/__main__.py",
    "prompt_contracts/py.typed",
    "prompt_contracts/errors.py",
    "prompt_contracts/types.py",
    "prompt_contracts/contract.py",
    "prompt_contracts/registry.py",
    "prompt_contracts/schemas/contract-manifest.schema.json",
    "prompt_contracts/schemas/contract-lock.schema.json",
)

FORBIDDEN_WHEEL_PREFIXES: tuple[str, ...] = (
    "tests/",
    "tools/",
    "benchmarks/",
    "scripts/",
    "docs/",
    "tasks/",
)

REQUIRED_SDIST_SUFFIXES: tuple[str, ...] = (
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "schemas/contract-manifest.schema.json",
    "schemas/contract-lock.schema.json",
    "src/prompt_contracts/py.typed",
)


def inspect_wheel(wheel_path: Path) -> list[str]:
    """Inspect wheel archive entries and return any errors."""
    errors: list[str] = []
    with zipfile.ZipFile(wheel_path, "r") as zf:
        names = set(zf.namelist())
        for req in REQUIRED_WHEEL_SUFFIXES:
            if req not in names:
                errors.append(f"Wheel {wheel_path.name} missing required entry: {req}")
        if not any(name.endswith(("licenses/LICENSE", "/LICENSE")) for name in names):
            errors.append(f"Wheel {wheel_path.name} missing LICENSE metadata entry")
        for name in names:
            for forbidden in FORBIDDEN_WHEEL_PREFIXES:
                if name.startswith(forbidden):
                    errors.append(f"Wheel {wheel_path.name} contains forbidden entry: {name}")
    return errors


def inspect_sdist(sdist_path: Path) -> list[str]:
    """Inspect sdist archive entries and return any errors."""
    errors: list[str] = []
    with tarfile.open(sdist_path, "r:gz") as tf:
        names = [member.name for member in tf.getmembers()]
        for req in REQUIRED_SDIST_SUFFIXES:
            if not any(name.endswith(f"/{req}") or name == req for name in names):
                errors.append(f"Sdist {sdist_path.name} missing required entry: {req}")
    return errors


def smoke_test_wheel_install(
    wheel_path: Path, repo_root: Path, *, with_gateway: bool = False
) -> list[str]:
    """Install a distribution and a packaged consumer in a clean venv outside checkout.

    Despite the historical function name, both wheels and source distributions are
    accepted. Dependency/build installation may use the network; runtime is offline.
    """
    expected_version = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]["version"]
    with tempfile.TemporaryDirectory(prefix="pc_dist_verify_") as tmp_str:
        tmp_dir = Path(tmp_str).resolve()
        environment = tmp_dir / "venv"
        work_dir = tmp_dir / "work"
        work_dir.mkdir()
        commands = [
            ["uv", "venv", "--python", sys.executable, str(environment)],
        ]
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        requirements = [str(wheel_path.resolve()) + ("[gateway]" if with_gateway else "")]
        if with_gateway:
            project = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
            sdk_source = project["tool"]["uv"]["sources"]["llm-gateway-sdk"]
            requirements.append(f"llm-gateway-sdk @ git+{sdk_source['git']}@{sdk_source['rev']}")
        commands.append(["uv", "pip", "install", "--python", str(python), *requirements])
        for command in commands:
            proc = subprocess.run(
                command, cwd=work_dir, capture_output=True, text=True, check=False
            )
            if proc.returncode:
                return [f"Clean installation failed: {proc.stderr.strip()}"]

        # This is a separate built/installed distribution, not a source-path injection.
        consumer_dist = tmp_dir / "consumer-dist"
        build = subprocess.run(
            [
                "uv",
                "build",
                "--wheel",
                "--out-dir",
                str(consumer_dist),
                str(repo_root / "examples/packaged_consumer"),
            ],
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if build.returncode:
            return [f"Consumer build failed: {build.stderr.strip()}"]
        consumer_wheel = next(consumer_dist.glob("*.whl"))
        install = subprocess.run(
            ["uv", "pip", "install", "--python", str(python), "--no-deps", str(consumer_wheel)],
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if install.returncode:
            return [f"Consumer installation failed: {install.stderr.strip()}"]
        check = subprocess.run(
            [
                str(python),
                "-I",
                "-c",
                (
                    "import importlib.util, importlib.metadata, pathlib; import prompt_contracts; "
                    f"assert prompt_contracts.__version__ == {expected_version!r}; "
                    "installed_version = importlib.metadata.version('prompt-contracts'); "
                    f"assert installed_version == {expected_version!r}; "
                    "from example_consumer import load_consumer_registry; "
                    "sdk_present = importlib.util.find_spec('llm_gateway_sdk') is not None; "
                    f"assert sdk_present is {with_gateway!r}; "
                    "package_dir = pathlib.Path(prompt_contracts.__file__).resolve().parent; "
                    "assert (package_dir / 'schemas/contract-manifest.schema.json').is_file(); "
                    f"assert not package_dir.is_relative_to({str(repo_root)!r}); "
                    "c = load_consumer_registry().get('career.application-answer@1.0.0'); "
                    "inputs = {'question': 'Question?', 'verified_facts': 'fact-1'}; "
                    "assert len(c.render(inputs).messages) == 2"
                    + (
                        "; from prompt_contracts.adapters.gateway import "
                        "ensure_gateway_sdk_available; assert ensure_gateway_sdk_available()"
                        if with_gateway
                        else ""
                    )
                ),
            ],
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode:
            return [f"Installed resource smoke failed: {check.stderr.strip()}"]
        cli = environment / (
            "Scripts/prompt-contracts.exe" if sys.platform == "win32" else "bin/prompt-contracts"
        )
        result = subprocess.run(
            [str(cli), "--version"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        return [] if result.returncode == 0 else [f"Installed CLI failed: {result.stderr.strip()}"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify wheel and sdist artifacts and smoke-test isolated installation."
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=Path("dist"),
        help="Path to dist directory containing built wheel and sdist.",
    )
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    dist_dir = args.dist_dir.resolve()
    if not dist_dir.is_dir():
        sys.stderr.write(f"Distribution directory does not exist: {dist_dir}\n")
        return 1

    wheels = sorted(dist_dir.glob("prompt_contracts-*.whl"))
    sdists = sorted(dist_dir.glob("prompt_contracts-*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        sys.stderr.write(
            f"Expected 1 wheel and 1 sdist in {dist_dir}, found "
            f"{len(wheels)} wheels and {len(sdists)} sdists.\n"
        )
        return 1

    errors: list[str] = []
    errors.extend(inspect_wheel(wheels[0]))
    errors.extend(inspect_sdist(sdists[0]))
    if not errors:
        errors.extend(smoke_test_wheel_install(wheels[0], repo_root))
        errors.extend(smoke_test_wheel_install(sdists[0], repo_root))
        errors.extend(smoke_test_wheel_install(wheels[0], repo_root, with_gateway=True))

    if errors:
        for err in errors:
            sys.stderr.write(f"DIST ERROR: {err}\n")
        return 1

    sys.stdout.write(f"Distribution verification passed ({wheels[0].name}, {sdists[0].name}).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
