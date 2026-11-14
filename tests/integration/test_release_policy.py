"""Tests for release tag/version validation and published contract immutability (T24,
AC-12, AC-32).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from scripts.check_release import validate_git_source, validate_release_state
from scripts.verify_published_contracts import verify_published_immutability
from scripts.verify_repository_contracts import verify_repository_contracts


def test_release_git_source_and_catalog_protection(tmp_path: Path, examples_dir: Path) -> None:
    """Exercise actual Git refs and regenerated locks, including deleted catalogs."""

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    git("init", "--initial-branch=main")
    git("config", "user.email", "synthetic@example.test")
    git("config", "user.name", "Synthetic Test")
    catalog = tmp_path / "contracts.lock.json"
    catalog.write_bytes((examples_dir / "contracts.lock.json").read_bytes())
    git("add", ".")
    git("commit", "-m", "test: initial catalog")
    baseline = git("rev-parse", "HEAD")
    git("tag", "v0.2.0")
    assert validate_git_source(tmp_path, "v0.2.0", "main") == []
    assert verify_repository_contracts(tmp_path, baseline) == []
    assert verify_repository_contracts(tmp_path, "missing-ref")
    data = json.loads(catalog.read_text(encoding="utf-8"))
    data["contracts"][0]["bundle_digest"] = "sha256:" + "f" * 64
    catalog.write_text(json.dumps(data), encoding="utf-8")
    assert verify_repository_contracts(tmp_path, baseline)
    catalog.unlink()
    assert verify_repository_contracts(tmp_path, baseline)

    git("checkout", "-b", "unmerged")
    (tmp_path / "new.txt").write_text("new", encoding="utf-8")
    git("add", ".")
    git("commit", "-m", "test: unmerged release source")
    git("tag", "v0.3.0")
    assert validate_git_source(tmp_path, "v0.3.0", "main")
    assert validate_git_source(tmp_path, "v0.2.0", "main")


def test_missing_changelog_blocks_checksums(repo_root: Path, tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "prompt_contracts-0.2.0-py3-none-any.whl").write_bytes(b"wheel")
    (dist / "prompt_contracts-0.2.0.tar.gz").write_bytes(b"sdist")
    errors = validate_release_state(
        pyproject_path=repo_root / "pyproject.toml",
        package_version="0.2.0",
        tag="v0.2.0",
        changelog_path=tmp_path / "missing.md",
        dist_dir=dist,
        write_checksums=True,
    )
    assert errors
    assert not (dist / "SHA256SUMS.txt").exists()


def test_release_pipeline_accepts_integration_prerelease_versions(tmp_path: Path) -> None:
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nversion = "0.3.0a1"\n', encoding="utf-8")
    assert (
        validate_release_state(pyproject_path=project, package_version="0.3.0a1", tag="v0.3.0a1")
        == []
    )


def test_validate_release_state_accepts_matching_tag_and_rejects_mismatch(
    repo_root: Path,
) -> None:
    pyproject = repo_root / "pyproject.toml"
    assert (
        validate_release_state(
            pyproject_path=pyproject,
            package_version="0.2.0",
            tag="v0.2.0",
        )
        == []
    )
    assert (
        validate_release_state(
            pyproject_path=pyproject,
            package_version="0.2.0",
            tag="refs/tags/v0.2.0",
        )
        == []
    )

    errors_tag = validate_release_state(
        pyproject_path=pyproject,
        package_version="0.2.0",
        tag="v0.9.9",
    )
    assert any("does not match expected tag" in e for e in errors_tag)

    errors_ver = validate_release_state(
        pyproject_path=pyproject,
        package_version="0.1.0",
        tag="v0.2.0",
    )
    assert any("Version mismatch" in e for e in errors_ver)


def test_verify_published_immutability_detects_in_place_mutation_and_deletion(
    examples_dir: Path, tmp_path: Path
) -> None:
    baseline_lock = examples_dir / "contracts.lock.json"

    # Identical lock passes
    assert verify_published_immutability(baseline_lock, baseline_lock) == []

    # Candidate lock adding a new version 1.1.0 while preserving 1.0.0 passes
    lock_data = json.loads(baseline_lock.read_text(encoding="utf-8"))
    lock_with_v2 = dict(lock_data)
    lock_with_v2["contracts"] = [
        *list(lock_data["contracts"]),
        {
            "name": "career.application-answer",
            "version": "1.1.0",
            "path": "contracts/career.application-answer/1.1.0",
            "bundle_digest": "sha256:" + "c" * 64,
        },
    ]
    candidate_additive = tmp_path / "candidate_additive.lock.json"
    candidate_additive.write_text(json.dumps(lock_with_v2), encoding="utf-8")
    assert verify_published_immutability(baseline_lock, candidate_additive) == []

    # Candidate lock mutating existing 1.0.0 digest fails
    lock_mutated = dict(lock_data)
    lock_mutated["contracts"] = [
        {
            "name": "career.application-answer",
            "version": "1.0.0",
            "path": "contracts/career.application-answer/1.0.0",
            "bundle_digest": "sha256:" + ("f" * 64),
        }
    ]
    candidate_mutated = tmp_path / "candidate_mutated.lock.json"
    candidate_mutated.write_text(json.dumps(lock_mutated), encoding="utf-8")
    violations = verify_published_immutability(baseline_lock, candidate_mutated)
    assert any("mutated in place" in v for v in violations)

    # Candidate lock deleting 1.0.0 fails
    lock_deleted = dict(lock_data)
    lock_deleted["contracts"] = [
        {
            "name": "career.application-answer",
            "version": "2.0.0",
            "path": "contracts/career.application-answer/2.0.0",
            "bundle_digest": "sha256:" + ("e" * 64),
        }
    ]
    candidate_deleted = tmp_path / "candidate_deleted.lock.json"
    candidate_deleted.write_text(json.dumps(lock_deleted), encoding="utf-8")
    del_violations = verify_published_immutability(baseline_lock, candidate_deleted)
    assert any("deleted from candidate lockfile" in v for v in del_violations)
