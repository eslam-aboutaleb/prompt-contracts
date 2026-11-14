"""Unit tests for pc-bundle-v1 byte-based digest computation (T11, AC-10)."""

from __future__ import annotations

from prompt_contracts.identity.digest import compute_bundle_digest


def test_compute_bundle_digest_matches_golden_vector() -> None:
    files = {
        "contract.toml": b'schema_version = "1"\n',
        "user.md": b"Hello {{name}}\n",
    }
    digest = compute_bundle_digest(files)
    # Independently calculated from the versioned canonical record format.
    assert digest == "sha256:c4c4f2f9bd7f24da5b961cd99f4309b5ca7154b90b791a43b9fdef52c2a876ab"
    assert digest.startswith("sha256:")
    assert len(digest) == 71
    # Verify exact repeatability across map ordering
    files_reversed = {
        "user.md": b"Hello {{name}}\n",
        "contract.toml": b'schema_version = "1"\n',
    }
    assert compute_bundle_digest(files_reversed) == digest


def test_compute_bundle_digest_changes_on_any_byte_change() -> None:
    base = {
        "contract.toml": b'schema_version = "1"\n',
        "user.md": b"Hello {{name}}\n",
        "input.schema.json": b'{"type": "object"}\n',
    }
    d0 = compute_bundle_digest(base)

    # Whitespace/comment change in TOML changes byte-based digest
    changed_toml = dict(base)
    changed_toml["contract.toml"] = b'# comment\nschema_version = "1"\n'
    assert compute_bundle_digest(changed_toml) != d0

    # Key order change in JSON file changes byte-based digest
    changed_json = dict(base)
    changed_json["input.schema.json"] = b'{"type": "object", "$defs": {}}\n'
    assert compute_bundle_digest(changed_json) != d0
