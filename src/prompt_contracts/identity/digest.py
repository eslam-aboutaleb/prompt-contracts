"""Deterministic byte-based bundle digest algorithm (``pc-bundle-v1``)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from prompt_contracts.errors import ErrorCode, PathPolicyError
from prompt_contracts.types import BUNDLE_DIGEST_ALGORITHM, validate_logical_relative_path

__all__ = [
    "BUNDLE_DIGEST_ALGORITHM",
    "BUNDLE_DIGEST_PREFIX",
    "BundleAssetRecord",
    "build_bundle_records",
    "compute_bundle_digest",
]

BUNDLE_DIGEST_PREFIX = b"prompt-contracts.bundle.v1\n"


@dataclass(frozen=True, slots=True)
class BundleAssetRecord:
    """Single hashed runtime asset record participating in ``pc-bundle-v1``."""

    path: str
    size: int
    sha256: str

    def to_dict(self) -> dict[str, str | int]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size": self.size,
        }


def build_bundle_records(assets: Mapping[str, bytes]) -> tuple[BundleAssetRecord, ...]:
    """Construct lexicographically sorted :class:`BundleAssetRecord` items for ``assets``."""
    if not assets:
        raise PathPolicyError(
            "Cannot compute bundle digest for an empty asset set",
            code=ErrorCode.ASSET_NOT_FOUND,
        )
    records: list[BundleAssetRecord] = []
    seen_casefold: set[str] = set()
    for raw_path, content in assets.items():
        norm_path = validate_logical_relative_path(raw_path)
        folded = norm_path.casefold()
        if folded in seen_casefold:
            raise PathPolicyError(
                f"Case-folding logical path collision in bundle: {norm_path!r}",
                code=ErrorCode.PATH_CASE_COLLISION,
                source_path=norm_path,
            )
        seen_casefold.add(folded)
        if not isinstance(content, bytes):
            raise TypeError(f"Asset content for {norm_path!r} must be bytes")
        file_hash = hashlib.sha256(content).hexdigest()
        records.append(
            BundleAssetRecord(
                path=norm_path,
                size=len(content),
                sha256=file_hash,
            )
        )
    records.sort(key=lambda r: r.path)
    return tuple(records)


def compute_bundle_digest(assets: Mapping[str, bytes]) -> str:
    """Compute ``sha256:<64-lowercase-hex>`` using ``pc-bundle-v1`` over ``assets``."""
    records = build_bundle_records(assets)
    encoded_records = json.dumps(
        [r.to_dict() for r in records],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(BUNDLE_DIGEST_PREFIX + encoded_records).hexdigest()
    return f"sha256:{digest}"
