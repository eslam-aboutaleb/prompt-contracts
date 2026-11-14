"""Filesystem and ``importlib.resources`` bundle readers with path confinement."""

from __future__ import annotations

import importlib.resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Protocol

from prompt_contracts.errors import ErrorCode, PathPolicyError, ResourceLimitError
from prompt_contracts.loading.paths import (
    read_bounded_file_bytes,
    resolve_confined_filesystem_path,
    scan_bundle_directory_files,
    validate_logical_relative_path,
)
from prompt_contracts.types import DEFAULT_RUNTIME_POLICY, RuntimePolicy

__all__ = [
    "BundleResourceReader",
    "DirectoryBundleReader",
    "PackageResourceBundleReader",
    "resolve_traversable_subpath",
]


class BundleResourceReader(Protocol):
    """Protocol for reading bounded runtime assets from a directory or package resource."""

    def list_files(
        self,
        *,
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
        contract_ref: str | None = None,
    ) -> tuple[str, ...]:
        """Return sorted logical relative paths of all regular files in the bundle."""
        ...

    def read_bytes(
        self,
        logical_path: str,
        *,
        max_bytes: int,
        contract_ref: str | None = None,
    ) -> bytes:
        """Read ``logical_path`` up to ``max_bytes``."""
        ...


class DirectoryBundleReader:
    """Reads a contract bundle from a local filesystem directory."""

    def __init__(self, bundle_root: Path) -> None:
        self.bundle_root = Path(bundle_root)

    def list_files(
        self,
        *,
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
        contract_ref: str | None = None,
    ) -> tuple[str, ...]:
        return scan_bundle_directory_files(
            self.bundle_root,
            policy=policy,
            contract_ref=contract_ref,
        )

    def read_bytes(
        self,
        logical_path: str,
        *,
        max_bytes: int,
        contract_ref: str | None = None,
    ) -> bytes:
        target = resolve_confined_filesystem_path(
            self.bundle_root,
            logical_path,
            contract_ref=contract_ref,
        )
        return read_bounded_file_bytes(
            target,
            max_bytes=max_bytes,
            logical_path=logical_path,
            contract_ref=contract_ref,
        )


def resolve_traversable_subpath(
    root: Traversable,
    logical_path: str,
    *,
    contract_ref: str | None = None,
) -> Traversable:
    """Navigate a :class:`Traversable` tree safely using a validated logical path."""
    norm = validate_logical_relative_path(logical_path, contract_ref=contract_ref)
    current = root
    for segment in norm.split("/"):
        current = current.joinpath(segment)
        if isinstance(current, Path) and current.is_symlink():
            raise PathPolicyError(
                f"Symlink detected in package resource at {norm!r}",
                code=ErrorCode.PATH_SYMLINK_REJECTED,
                contract_ref=contract_ref,
                source_path=norm,
            )
    return current


class PackageResourceBundleReader:
    """Reads a contract bundle packaged inside an installed Python distribution via
    ``importlib.resources``.
    """

    def __init__(self, package: str, resource_path: str = "") -> None:
        if type(package) is not str or not package:
            raise PathPolicyError(
                "Package name must be a non-empty string",
                code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            )
        try:
            pkg_root = importlib.resources.files(package)
        except Exception:
            raise PathPolicyError(
                f"Unable to locate Python package {package!r}",
                code=ErrorCode.ASSET_NOT_FOUND,
            ) from None

        if resource_path:
            self._root = resolve_traversable_subpath(pkg_root, resource_path)
        else:
            self._root = pkg_root

    def list_files(
        self,
        *,
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
        contract_ref: str | None = None,
    ) -> tuple[str, ...]:
        if isinstance(self._root, Path):
            return scan_bundle_directory_files(
                self._root,
                policy=policy,
                contract_ref=contract_ref,
            )

        if not self._root.is_dir():
            raise PathPolicyError(
                "Package resource bundle root does not exist or is not a directory",
                code=ErrorCode.ASSET_NOT_FOUND,
                contract_ref=contract_ref,
            )

        discovered: list[str] = []
        seen_casefold: set[str] = set()

        def _walk(node: Traversable, rel_parts: tuple[str, ...]) -> None:
            entries = sorted(node.iterdir(), key=lambda item: item.name)
            local_casefold: set[str] = set()
            for entry in entries:
                name = entry.name
                folded_name = name.casefold()
                if folded_name in local_casefold:
                    raise PathPolicyError(
                        f"Case-folding filename collision in package resource: {name!r}",
                        code=ErrorCode.PATH_CASE_COLLISION,
                        contract_ref=contract_ref,
                    )
                local_casefold.add(folded_name)
                rel_str = "/".join((*rel_parts, name))
                norm_rel = validate_logical_relative_path(rel_str, contract_ref=contract_ref)
                if entry.is_dir():
                    _walk(entry, (*rel_parts, name))
                elif entry.is_file():
                    folded_full = norm_rel.casefold()
                    if folded_full in seen_casefold:
                        raise PathPolicyError(
                            f"Case-folding path collision in package resource: {norm_rel!r}",
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

        _walk(self._root, ())
        discovered.sort()
        return tuple(discovered)

    def read_bytes(
        self,
        logical_path: str,
        *,
        max_bytes: int,
        contract_ref: str | None = None,
    ) -> bytes:
        target = resolve_traversable_subpath(
            self._root,
            logical_path,
            contract_ref=contract_ref,
        )
        if isinstance(target, Path):
            return read_bounded_file_bytes(
                target,
                max_bytes=max_bytes,
                logical_path=logical_path,
                contract_ref=contract_ref,
            )
        if not target.is_file():
            raise PathPolicyError(
                f"Referenced package resource asset not found: {logical_path!r}",
                code=ErrorCode.ASSET_NOT_FOUND,
                contract_ref=contract_ref,
                source_path=logical_path,
            )
        with target.open("rb") as handle:
            data = handle.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ResourceLimitError(
                f"Package resource asset {logical_path!r} exceeds limit ({max_bytes} bytes)",
                code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
                contract_ref=contract_ref,
                source_path=logical_path,
            )
        return data
