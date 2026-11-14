"""Byte-based bundle identity (``pc-bundle-v1``) and atomic lockfile management."""

from __future__ import annotations

from prompt_contracts.identity.digest import (
    BUNDLE_DIGEST_ALGORITHM,
    BUNDLE_DIGEST_PREFIX,
    BundleAssetRecord,
    build_bundle_records,
    compute_bundle_digest,
)
from prompt_contracts.identity.lock import (
    LOCK_FORMAT_VERSION,
    ContractLock,
    LockEntry,
    parse_lock_bytes,
    read_lock_file,
    serialize_lock,
    write_lock_atomic,
)

__all__ = [
    "BUNDLE_DIGEST_ALGORITHM",
    "BUNDLE_DIGEST_PREFIX",
    "LOCK_FORMAT_VERSION",
    "BundleAssetRecord",
    "ContractLock",
    "LockEntry",
    "build_bundle_records",
    "compute_bundle_digest",
    "parse_lock_bytes",
    "read_lock_file",
    "serialize_lock",
    "write_lock_atomic",
]
