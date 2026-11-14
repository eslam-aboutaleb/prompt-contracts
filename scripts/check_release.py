"""Validate release tag, package version consistency, changelog entry, and artifact checksums."""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import prompt_contracts

RELEASE_VERSION_PATTERN = (
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
    r"(?:(?:a|b|rc)(?:0|[1-9][0-9]*))?"
)
RELEASE_VERSION_RE = re.compile(RELEASE_VERSION_PATTERN)
RELEASE_TAG_RE = re.compile("v" + RELEASE_VERSION_PATTERN)


def validate_git_source(repo: Path, tag: str, main_ref: str = "origin/main") -> list[str]:
    """Require the checked-out tag commit to belong to the trusted main branch."""
    normalized = normalize_git_tag(tag)
    if not RELEASE_TAG_RE.fullmatch(normalized):
        return ["Invalid release tag"]

    def resolve(ref: str) -> str | None:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else None

    head, tagged, main = resolve("HEAD"), resolve(f"refs/tags/{normalized}"), resolve(main_ref)
    if not head or not tagged or not main:
        return ["Release HEAD, tag, or trusted main branch cannot be resolved"]
    if head != tagged:
        return ["Checked-out source does not match the release tag commit"]
    ancestry = subprocess.run(
        ["git", "merge-base", "--is-ancestor", head, main],
        cwd=repo,
        check=False,
    )
    return [] if ancestry.returncode == 0 else ["Release commit is not on the trusted main branch"]


def normalize_git_tag(raw_tag: str) -> str:
    """Strip ``refs/tags/`` prefix if present."""
    if raw_tag.startswith("refs/tags/"):
        return raw_tag[len("refs/tags/") :]
    return raw_tag


def validate_release_state(
    *,
    pyproject_path: Path,
    package_version: str,
    tag: str | None = None,
    changelog_path: Path | None = None,
    dist_dir: Path | None = None,
    write_checksums: bool = False,
) -> list[str]:
    """Validate version/tag parity and optional distribution artifacts."""
    errors: list[str] = []

    if not pyproject_path.is_file():
        return [f"pyproject.toml not found at {pyproject_path}"]

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project_table = data.get("project", {})
    pyproject_version = str(project_table.get("version", ""))

    if not RELEASE_VERSION_RE.fullmatch(pyproject_version):
        errors.append(
            f"pyproject.toml version {pyproject_version!r} must be X.Y.Z "
            "with an optional aN/bN/rcN prerelease suffix"
        )

    if not RELEASE_VERSION_RE.fullmatch(package_version):
        errors.append(
            f"prompt_contracts.__version__ {package_version!r} must be X.Y.Z "
            "with an optional aN/bN/rcN prerelease suffix"
        )

    if pyproject_version != package_version:
        errors.append(
            f"Version mismatch: pyproject.toml has {pyproject_version!r} "
            f"but prompt_contracts.__version__ is {package_version!r}"
        )

    if tag is not None:
        normalized_tag = normalize_git_tag(tag)
        if not RELEASE_TAG_RE.fullmatch(normalized_tag):
            errors.append(
                f"Release tag {normalized_tag!r} must be vX.Y.Z "
                "with an optional aN/bN/rcN prerelease suffix"
            )
        expected_tag = f"v{pyproject_version}"
        if normalized_tag != expected_tag:
            errors.append(
                f"Release tag {normalized_tag!r} does not match expected tag {expected_tag!r}"
            )

    if changelog_path is not None and not changelog_path.is_file():
        errors.append("Required release changelog is missing")
    elif changelog_path is not None:
        changelog_text = changelog_path.read_text(encoding="utf-8")
        if (
            f"[{pyproject_version}]" not in changelog_text
            and f"## {pyproject_version}" not in changelog_text
        ):
            errors.append(
                f"CHANGELOG.md at {changelog_path} does not "
                f"contain a release section for {pyproject_version}"
            )

    if dist_dir is not None:
        if not dist_dir.is_dir():
            errors.append(f"Distribution directory not found: {dist_dir}")
        else:
            expected_wheel = f"prompt_contracts-{pyproject_version}-py3-none-any.whl"
            expected_sdist = f"prompt_contracts-{pyproject_version}.tar.gz"
            wheel_path = dist_dir / expected_wheel
            sdist_path = dist_dir / expected_sdist
            if not wheel_path.is_file():
                errors.append(f"Expected wheel missing in {dist_dir}: {expected_wheel}")
            if not sdist_path.is_file():
                errors.append(f"Expected sdist missing in {dist_dir}: {expected_sdist}")

            if write_checksums and not errors and wheel_path.is_file() and sdist_path.is_file():
                checksum_lines: list[str] = []
                for artifact in (wheel_path, sdist_path):
                    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
                    checksum_lines.append(f"{digest}  {artifact.name}")
                (dist_dir / "SHA256SUMS.txt").write_text(
                    "\n".join(checksum_lines) + "\n", encoding="utf-8"
                )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check release version parity, tag syntax, and dist artifacts."
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default=None,
        help="Optional Git release tag (e.g. v0.2.0 or refs/tags/v0.2.0).",
    )
    parser.add_argument(
        "--changelog",
        type=Path,
        default=Path("CHANGELOG.md"),
        help="Path to CHANGELOG.md.",
    )
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=None,
        help="Optional dist directory to validate built artifacts.",
    )
    parser.add_argument(
        "--write-checksums",
        action="store_true",
        help="Write SHA256SUMS.txt inside --dist-dir.",
    )
    parser.add_argument("--verify-git", action="store_true", help="Verify tag source and ancestry.")
    parser.add_argument("--main-ref", default="origin/main")
    args = parser.parse_args(argv)

    errors = validate_release_state(
        pyproject_path=args.pyproject,
        package_version=prompt_contracts.__version__,
        tag=args.tag,
        changelog_path=args.changelog,
        dist_dir=args.dist_dir,
        write_checksums=args.write_checksums,
    )
    if args.verify_git:
        if args.tag is None:
            errors.append("Git source verification requires --tag")
        else:
            errors.extend(
                validate_git_source(args.pyproject.resolve().parent, args.tag, args.main_ref)
            )
    if errors:
        for err in errors:
            sys.stderr.write(f"RELEASE CHECK ERROR: {err}\n")
        return 1

    sys.stdout.write(
        f"Release check passed for prompt-contracts v{prompt_contracts.__version__}.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
