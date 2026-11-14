"""Hypothesis property tests for pc-bundle-v1 digest collision resistance and sensitivity (T11)."""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from prompt_contracts.identity.digest import compute_bundle_digest


@settings(max_examples=60, deadline=None)
@given(
    content_a=st.binary(min_size=1, max_size=256),
    content_b=st.binary(min_size=1, max_size=256),
)
def test_bundle_digest_sensitive_to_single_byte_or_path_difference(
    content_a: bytes, content_b: bytes
) -> None:
    d_same_1 = compute_bundle_digest({"contract.toml": content_a, "user.md": content_b})
    d_same_2 = compute_bundle_digest({"user.md": content_b, "contract.toml": content_a})
    assert d_same_1 == d_same_2

    flipped = bytes([content_b[0] ^ 0x01]) + content_b[1:]
    d_flipped = compute_bundle_digest({"contract.toml": content_a, "user.md": flipped})
    assert d_flipped != d_same_1

    d_renamed = compute_bundle_digest({"contract.toml": content_a, "system.md": content_b})
    assert d_renamed != d_same_1
