"""Root-confined path validation, portable naming rules, and bounded byte reading."""

from __future__ import annotations

import stat
from pathlib import Path

from prompt_contracts.errors import ErrorCode, PathPolicyError, ResourceLimitError
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    PORTABLE_SEGMENT_RE,
    WINDOWS_RESERVED_NAMES,
    RuntimePolicy,
    validate_logical_relative_path,
)

__all__ = [
    "PORTABLE_SEGMENT_RE",
    "WINDOWS_RESERVED_NAMES",
    "read_bounded_file_bytes",
    "resolve_confined_filesystem_path",
    "scan_bundle_directory_files",
    "validate_logical_relative_path",
]


def resolve_confined_filesystem_path(
    bundle_root: Path,
    logical_path: str,
    *,
    contract_ref: str | None = None,
) -> Path:
    """Resolve ``logical_path`` inside ``bundle_root`` while rejecting symlinks and escapes."""
    norm_rel = validate_logical_relative_path(logical_path, contract_ref=contract_ref)
    if bundle_root.is_symlink():
        raise PathPolicyError(
            "Bundle root directory cannot be a symlink",
            code=ErrorCode.PATH_SYMLINK_REJECTED,
            contract_ref=contract_ref,
        )
    if not bundle_root.exists() or not bundle_root.is_dir():
        raise PathPolicyError(
            "Bundle root directory does not exist",
            code=ErrorCode.ASSET_NOT_FOUND,
            contract_ref=contract_ref,
        )

    resolved_root = bundle_root.resolve()
    current = bundle_root
    for part in norm_rel.split("/"):
        current = current / part
        if current.is_symlink():
            raise PathPolicyError(
                f"Symlink detected inside contract bundle at {norm_rel!r}",
                code=ErrorCode.PATH_SYMLINK_REJECTED,
                contract_ref=contract_ref,
                source_path=norm_rel,
            )

    try:
        resolved_target = current.resolve()
    except OSError:
        raise PathPolicyError(
            f"Unable to resolve bundle asset path {norm_rel!r}",
            code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            contract_ref=contract_ref,
            source_path=norm_rel,
        ) from None

    if not resolved_target.is_relative_to(resolved_root) or resolved_target == resolved_root:
        raise PathPolicyError(
            f"Asset path {norm_rel!r} escapes bundle root",
            code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            contract_ref=contract_ref,
            source_path=norm_rel,
        )
    return current


def scan_bundle_directory_files(
    bundle_root: Path,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    contract_ref: str | None = None,
) -> tuple[str, ...]:
    """Discover all files inside ``bundle_root``, enforcing symlink, collision, and count
    policies.
    """
    if bundle_root.is_symlink():
        raise PathPolicyError(
            "Bundle root directory cannot be a symlink",
            code=ErrorCode.PATH_SYMLINK_REJECTED,
            contract_ref=contract_ref,
        )
    if not bundle_root.exists() or not bundle_root.is_dir():
        raise PathPolicyError(
            "Bundle root directory does not exist",
            code=ErrorCode.ASSET_NOT_FOUND,
            contract_ref=contract_ref,
        )

    discovered: list[str] = []
    seen_casefold: set[str] = set()

    def _walk_dir(current_dir: Path, rel_parts: tuple[str, ...]) -> None:
        try:
            entries = sorted(current_dir.iterdir(), key=lambda p: p.name)
        except OSError:
            raise PathPolicyError(
                "Unable to list bundle directory",
                code=ErrorCode.ASSET_NOT_FOUND,
                contract_ref=contract_ref,
            ) from None

        local_casefold: set[str] = set()
        for entry in entries:
            name = entry.name
            folded_name = name.casefold()
            if folded_name in local_casefold:
                raise PathPolicyError(
                    f"Case-folding filename collision detected for {name!r}",
                    code=ErrorCode.PATH_CASE_COLLISION,
                    contract_ref=contract_ref,
                )
            local_casefold.add(folded_name)

            rel_str = "/".join((*rel_parts, name))
            if entry.is_symlink():
                raise PathPolicyError(
                    f"Symlink is not permitted inside contract bundle: {rel_str!r}",
                    code=ErrorCode.PATH_SYMLINK_REJECTED,
                    contract_ref=contract_ref,
                    source_path=rel_str,
                )
            norm_rel = validate_logical_relative_path(rel_str, contract_ref=contract_ref)
            try:
                st = entry.lstat()
            except OSError:
                raise PathPolicyError(
                    f"Unable to stat bundle entry {norm_rel!r}",
                    code=ErrorCode.ASSET_NOT_FOUND,
                    contract_ref=contract_ref,
                    source_path=norm_rel,
                ) from None

            if stat.S_ISDIR(st.st_mode):
                _walk_dir(entry, (*rel_parts, name))
            elif stat.S_ISREG(st.st_mode):
                folded_full = norm_rel.casefold()
                if folded_full in seen_casefold:
                    raise PathPolicyError(
                        f"Case-folding path collision in bundle: {norm_rel!r}",
                        code=ErrorCode.PATH_CASE_COLLISION,
                        contract_ref=contract_ref,
                        source_path=norm_rel,
                    )
                seen_casefold.add(folded_full)
                discovered.append(norm_rel)
                if len(discovered) > policy.max_bundle_files:
                    raise ResourceLimitError(
                        f"Bundle file count exceeds limit of {policy.max_bundle_files} files",
                        code=ErrorCode.RESOURCE_COUNT_EXCEEDED,
                        contract_ref=contract_ref,
                    )
            else:
                raise PathPolicyError(
                    f"Non-regular file is not permitted in bundle: {norm_rel!r}",
                    code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
                    contract_ref=contract_ref,
                    source_path=norm_rel,
                )

    _walk_dir(bundle_root, ())
    discovered.sort()
    return tuple(discovered)


def read_bounded_file_bytes(
    file_path: Path,
    *,
    max_bytes: int,
    logical_path: str,
    contract_ref: str | None = None,
) -> bytes:
    """Read a regular file up to ``max_bytes``, checking ``lstat`` size before reading."""
    if file_path.is_symlink():
        raise PathPolicyError(
            f"Symlink rejected when reading {logical_path!r}",
            code=ErrorCode.PATH_SYMLINK_REJECTED,
            contract_ref=contract_ref,
            source_path=logical_path,
        )
    try:
        st = file_path.lstat()
    except FileNotFoundError:
        raise PathPolicyError(
            f"Referenced bundle asset not found: {logical_path!r}",
            code=ErrorCode.ASSET_NOT_FOUND,
            contract_ref=contract_ref,
            source_path=logical_path,
        ) from None
    except OSError:
        raise PathPolicyError(
            f"Unable to access bundle asset: {logical_path!r}",
            code=ErrorCode.ASSET_NOT_FOUND,
            contract_ref=contract_ref,
            source_path=logical_path,
        ) from None

    if not stat.S_ISREG(st.st_mode):
        raise PathPolicyError(
            f"Bundle asset is not a regular file: {logical_path!r}",
            code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            contract_ref=contract_ref,
            source_path=logical_path,
        )
    if st.st_size > max_bytes:
        raise ResourceLimitError(
            f"Asset {logical_path!r} size ({st.st_size} bytes) exceeds limit ({max_bytes} bytes)",
            code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
            contract_ref=contract_ref,
            source_path=logical_path,
        )

    with file_path.open("rb") as handle:
        data = handle.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ResourceLimitError(
            f"Asset {logical_path!r} size exceeds limit ({max_bytes} bytes)",
            code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
            contract_ref=contract_ref,
            source_path=logical_path,
        )
    return data
