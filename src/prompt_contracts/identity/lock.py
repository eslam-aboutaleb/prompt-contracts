"""Strict lockfile parsing, verification, and atomic generation."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prompt_contracts.errors import ErrorCode, LockMismatchError, UnsupportedFormatError
from prompt_contracts.types import (
    BUNDLE_DIGEST_ALGORITHM,
    DEFAULT_RUNTIME_POLICY,
    ContractRef,
    RuntimePolicy,
    validate_logical_relative_path,
)
from prompt_contracts.validation.json_io import parse_strict_json

__all__ = [
    "DIGEST_RE",
    "LOCK_FORMAT_VERSION",
    "ContractLock",
    "LockEntry",
    "parse_lock_bytes",
    "read_lock_file",
    "serialize_lock",
    "write_lock_atomic",
]

LOCK_FORMAT_VERSION = 1
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALLOWED_LOCK_TOP_KEYS = frozenset({"lock_format", "digest_algorithm", "contracts"})
_ALLOWED_LOCK_ENTRY_KEYS = frozenset({"name", "version", "path", "bundle_digest"})


@dataclass(frozen=True, slots=True, order=True)
class LockEntry:
    """Single locked contract version entry."""

    name: str
    version: str
    path: str
    bundle_digest: str

    def __post_init__(self) -> None:
        # Validate name & version using ContractRef
        _ = ContractRef(self.name, self.version)
        norm_path = validate_logical_relative_path(self.path)
        object.__setattr__(self, "path", norm_path)
        if type(self.bundle_digest) is not str or not DIGEST_RE.fullmatch(self.bundle_digest):
            raise LockMismatchError(
                f"Invalid bundle_digest format for {self.name}@{self.version}",
                code=ErrorCode.LOCK_INVALID,
                contract_ref=f"{self.name}@{self.version}",
            )

    @property
    def ref(self) -> ContractRef:
        return ContractRef(self.name, self.version)

    def to_dict(self) -> dict[str, str]:
        return {
            "bundle_digest": self.bundle_digest,
            "name": self.name,
            "path": self.path,
            "version": self.version,
        }


@dataclass(frozen=True, slots=True)
class ContractLock:
    """Validated immutable representation of ``contracts.lock.json``."""

    contracts: tuple[LockEntry, ...]
    lock_format: int = LOCK_FORMAT_VERSION
    digest_algorithm: str = BUNDLE_DIGEST_ALGORITHM

    def __post_init__(self) -> None:
        if type(self.lock_format) is not int or self.lock_format != LOCK_FORMAT_VERSION:
            raise UnsupportedFormatError(
                f"Unsupported lock_format: {self.lock_format!r} (expected {LOCK_FORMAT_VERSION})",
                code=ErrorCode.UNSUPPORTED_FORMAT_VERSION,
            )
        if self.digest_algorithm != BUNDLE_DIGEST_ALGORITHM:
            raise UnsupportedFormatError(
                f"Unsupported digest_algorithm: {self.digest_algorithm!r} "
                f"(expected {BUNDLE_DIGEST_ALGORITHM!r})",
                code=ErrorCode.UNSUPPORTED_FORMAT_VERSION,
            )
        sorted_entries = tuple(sorted(self.contracts, key=lambda e: (e.name, e.version)))
        seen_refs: set[ContractRef] = set()
        seen_paths: set[str] = set()
        for entry in sorted_entries:
            if entry.ref in seen_refs:
                raise LockMismatchError(
                    f"Duplicate contract entry in lockfile: {entry.ref}",
                    code=ErrorCode.LOCK_INVALID,
                    contract_ref=str(entry.ref),
                )
            seen_refs.add(entry.ref)
            folded_path = entry.path.casefold()
            if folded_path in seen_paths:
                raise LockMismatchError(
                    f"Duplicate or case-colliding path in lockfile: {entry.path!r}",
                    code=ErrorCode.LOCK_INVALID,
                    contract_ref=str(entry.ref),
                )
            seen_paths.add(folded_path)
        object.__setattr__(self, "contracts", sorted_entries)

    def by_ref(self) -> Mapping[ContractRef, LockEntry]:
        """Return mapping from :class:`ContractRef` to :class:`LockEntry`."""
        return {entry.ref: entry for entry in self.contracts}

    def to_dict(self) -> dict[str, Any]:
        return {
            "lock_format": self.lock_format,
            "digest_algorithm": self.digest_algorithm,
            "contracts": [
                {
                    "name": e.name,
                    "version": e.version,
                    "path": e.path,
                    "bundle_digest": e.bundle_digest,
                }
                for e in self.contracts
            ],
        }


def parse_lock_bytes(
    raw: bytes | str,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    source_path: str | None = None,
) -> ContractLock:
    """Parse and validate a lockfile document from bytes or string."""
    parsed = parse_strict_json(
        raw,
        max_bytes=policy.max_schema_bytes,
        max_depth=policy.max_nesting_depth,
        error_cls=LockMismatchError,
        source_path=source_path,
    )
    if not isinstance(parsed, dict):
        raise LockMismatchError(
            "Lockfile root must be a JSON object",
            code=ErrorCode.LOCK_INVALID,
            source_path=source_path,
        )
    unknown_top = set(parsed.keys()) - _ALLOWED_LOCK_TOP_KEYS
    if unknown_top:
        raise LockMismatchError(
            f"Unknown field(s) in lockfile root: {sorted(unknown_top)}",
            code=ErrorCode.LOCK_INVALID,
            source_path=source_path,
        )
    missing_top = _ALLOWED_LOCK_TOP_KEYS - set(parsed.keys())
    if missing_top:
        raise LockMismatchError(
            f"Missing required field(s) in lockfile root: {sorted(missing_top)}",
            code=ErrorCode.LOCK_INVALID,
            source_path=source_path,
        )

    lock_format = parsed["lock_format"]
    if type(lock_format) is not int or lock_format != LOCK_FORMAT_VERSION:
        raise UnsupportedFormatError(
            f"Unsupported lock_format in lockfile: {lock_format!r}",
            code=ErrorCode.UNSUPPORTED_FORMAT_VERSION,
            source_path=source_path,
        )

    digest_algo = parsed["digest_algorithm"]
    if type(digest_algo) is not str or digest_algo != BUNDLE_DIGEST_ALGORITHM:
        raise UnsupportedFormatError(
            f"Unsupported digest_algorithm in lockfile: {digest_algo!r}",
            code=ErrorCode.UNSUPPORTED_FORMAT_VERSION,
            source_path=source_path,
        )

    raw_contracts = parsed["contracts"]
    if not isinstance(raw_contracts, list):
        raise LockMismatchError(
            "Lockfile 'contracts' must be a JSON array",
            code=ErrorCode.LOCK_INVALID,
            source_path=source_path,
        )

    entries: list[LockEntry] = []
    for idx, item in enumerate(raw_contracts):
        if not isinstance(item, dict):
            raise LockMismatchError(
                f"Lockfile contract entry at index {idx} must be a JSON object",
                code=ErrorCode.LOCK_INVALID,
                source_path=source_path,
            )
        unknown_keys = set(item.keys()) - _ALLOWED_LOCK_ENTRY_KEYS
        if unknown_keys:
            raise LockMismatchError(
                f"Unknown field(s) in lockfile entry {idx}: {sorted(unknown_keys)}",
                code=ErrorCode.LOCK_INVALID,
                source_path=source_path,
            )
        missing_keys = _ALLOWED_LOCK_ENTRY_KEYS - set(item.keys())
        if missing_keys:
            raise LockMismatchError(
                f"Missing required field(s) in lockfile entry {idx}: {sorted(missing_keys)}",
                code=ErrorCode.LOCK_INVALID,
                source_path=source_path,
            )
        for k in _ALLOWED_LOCK_ENTRY_KEYS:
            if type(item[k]) is not str:
                raise LockMismatchError(
                    f"Field {k!r} in lockfile entry {idx} must be a string",
                    code=ErrorCode.LOCK_INVALID,
                    source_path=source_path,
                )
        try:
            entries.append(
                LockEntry(
                    name=item["name"],
                    version=item["version"],
                    path=item["path"],
                    bundle_digest=item["bundle_digest"],
                )
            )
        except Exception as exc:
            if isinstance(exc, LockMismatchError):
                raise
            raise LockMismatchError(
                f"Invalid lockfile entry at index {idx}: "
                f"{getattr(exc, 'safe_message', 'validation failed')}",
                code=ErrorCode.LOCK_INVALID,
                source_path=source_path,
            ) from None

    return ContractLock(
        contracts=tuple(entries),
        lock_format=lock_format,
        digest_algorithm=digest_algo,
    )


def read_lock_file(
    path: Path,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> ContractLock:
    """Read and parse a lockfile from ``path``."""
    if not path.exists() or not path.is_file():
        raise LockMismatchError(
            "Lockfile does not exist or is not a regular file",
            code=ErrorCode.LOCK_INVALID,
            source_path=path.name,
        )
    if path.is_symlink():
        raise LockMismatchError(
            "Lockfile cannot be a symlink",
            code=ErrorCode.LOCK_INVALID,
            source_path=path.name,
        )
    raw_bytes = path.read_bytes()
    return parse_lock_bytes(raw_bytes, policy=policy, source_path=path.name)


def serialize_lock(lock: ContractLock) -> str:
    """Serialize ``lock`` deterministically with 2-space indentation and trailing newline."""
    return json.dumps(lock.to_dict(), indent=2, ensure_ascii=True) + "\n"


def write_lock_atomic(
    lock: ContractLock,
    target_path: Path,
    *,
    allow_update: bool = False,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> None:
    """Write ``lock`` atomically via a temporary sibling file and ``os.replace``.

    If ``target_path`` already exists and differs from ``lock``, raises
    :class:`LockMismatchError` unless ``allow_update=True``.
    """
    serialized = serialize_lock(lock).encode("utf-8")
    if target_path.exists():
        if target_path.is_symlink():
            raise LockMismatchError(
                "Refusing to write lockfile over a symlink",
                code=ErrorCode.LOCK_OVERWRITE_REFUSED,
                source_path=target_path.name,
            )
        existing_bytes = target_path.read_bytes()
        if existing_bytes == serialized:
            return
        if not allow_update:
            raise LockMismatchError(
                "Existing lockfile differs from generated lock; "
                "pass --update (or allow_update=True) to replace it",
                code=ErrorCode.LOCK_OVERWRITE_REFUSED,
                source_path=target_path.name,
            )
        # Validate existing lock is not corrupted unless updating intentionally
        _ = parse_lock_bytes(existing_bytes, policy=policy, source_path=target_path.name)

    parent = target_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".contracts-lock-", suffix=".tmp", dir=str(parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        tmp_path.replace(target_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise
