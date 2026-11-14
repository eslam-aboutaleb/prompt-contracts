"""Unit tests for filesystem path safety, symlink rejection, and asset closure (T06, AC-04)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from prompt_contracts.errors import ErrorCode, PathPolicyError
from prompt_contracts.loading.loader import load_contract_from_directory
from prompt_contracts.loading.paths import resolve_confined_filesystem_path


def _write_valid_bundle(bundle_dir: Path) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "contract.toml").write_text(
        "format_version = 1\n"
        'name = "demo.path-test"\n'
        'version = "1.0.0"\n'
        'description = "Path safety test."\n'
        'renderer = "placeholders-v1"\n'
        'input_schema = "input.schema.json"\n\n'
        "[output]\n"
        'mode = "json"\n'
        'schema = "output.schema.json"\n\n'
        "[[messages]]\n"
        'role = "user"\n'
        'file = "user.md"\n',
        encoding="utf-8",
    )
    (bundle_dir / "user.md").write_text("Hello {{name}}", encoding="utf-8")
    (bundle_dir / "input.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["name"],
                "properties": {"name": {"type": "string"}},
            }
        ),
        encoding="utf-8",
    )
    (bundle_dir / "output.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["greeting"],
                "properties": {"greeting": {"type": "string"}},
            }
        ),
        encoding="utf-8",
    )


def test_loader_rejects_unreferenced_extra_file_in_bundle(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "demo.path-test" / "1.0.0"
    _write_valid_bundle(bundle_dir)
    (bundle_dir / "stray_notes.txt").write_text("unreferenced", encoding="utf-8")

    with pytest.raises(PathPolicyError) as exc_info:
        load_contract_from_directory(bundle_dir)
    assert exc_info.value.code == ErrorCode.UNREFERENCED_BUNDLE_ASSET


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink test")
def test_loader_rejects_symlink_inside_bundle(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "demo.path-test" / "1.0.0"
    _write_valid_bundle(bundle_dir)
    outside = tmp_path / "outside.md"
    outside.write_text("Hello {{name}}", encoding="utf-8")
    (bundle_dir / "user.md").unlink()
    (bundle_dir / "user.md").symlink_to(outside)

    with pytest.raises(PathPolicyError) as exc_info:
        load_contract_from_directory(bundle_dir)
    assert exc_info.value.code == ErrorCode.PATH_SYMLINK_REJECTED


def test_resolve_confined_filesystem_path_rejects_traversal(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    with pytest.raises(PathPolicyError) as exc_info:
        resolve_confined_filesystem_path(bundle_dir, "../outside.txt")
    assert exc_info.value.code == ErrorCode.PATH_TRAVERSAL_OR_UNSAFE


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink test")
def test_path_helpers_reject_root_symlinks_missing_dirs_and_size_limits(tmp_path: Path) -> None:
    from prompt_contracts.errors import ResourceLimitError
    from prompt_contracts.loading.paths import (
        read_bounded_file_bytes,
        scan_bundle_directory_files,
    )
    from prompt_contracts.types import RuntimePolicy

    missing_dir = tmp_path / "does_not_exist"
    with pytest.raises(PathPolicyError):
        resolve_confined_filesystem_path(missing_dir, "a.txt")
    with pytest.raises(PathPolicyError):
        scan_bundle_directory_files(missing_dir)

    real_dir = tmp_path / "real_bundle"
    _write_valid_bundle(real_dir)
    sym_dir = tmp_path / "sym_bundle"
    sym_dir.symlink_to(real_dir)

    with pytest.raises(PathPolicyError):
        resolve_confined_filesystem_path(sym_dir, "user.md")
    with pytest.raises(PathPolicyError):
        scan_bundle_directory_files(sym_dir)

    with pytest.raises(ResourceLimitError):
        scan_bundle_directory_files(real_dir, policy=RuntimePolicy(max_bundle_files=2))

    # Nested directory scan works
    nested_dir = real_dir / "sub"
    nested_dir.mkdir()
    (nested_dir / "extra.txt").write_text("hi", encoding="utf-8")
    files = scan_bundle_directory_files(real_dir)
    assert "sub/extra.txt" in files

    # read_bounded_file_bytes checks
    sym_file = tmp_path / "sym_user.md"
    sym_file.symlink_to(real_dir / "user.md")
    with pytest.raises(PathPolicyError):
        read_bounded_file_bytes(sym_file, max_bytes=100, logical_path="user.md")

    with pytest.raises(PathPolicyError):
        read_bounded_file_bytes(tmp_path / "missing.md", max_bytes=100, logical_path="missing.md")

    with pytest.raises(PathPolicyError):
        read_bounded_file_bytes(real_dir, max_bytes=100, logical_path="dir")

    with pytest.raises(ResourceLimitError):
        read_bounded_file_bytes(real_dir / "user.md", max_bytes=2, logical_path="user.md")
