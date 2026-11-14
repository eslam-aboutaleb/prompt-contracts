"""Integration tests for lockfile generation, verification, overwrite guards, and tamper
detection (T12).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from prompt_contracts import (
    ErrorCode,
    LockMismatchError,
    PromptRegistry,
    write_lock_atomic,
)
from prompt_contracts.registry import generate_lock_for_directory


def test_lockfile_generation_overwrite_protection_and_tamper_detection(
    examples_dir: Path, tmp_path: Path
) -> None:
    contracts_copy = tmp_path / "contracts"
    shutil.copytree(examples_dir / "contracts", contracts_copy)
    lock_file = tmp_path / "contracts.lock.json"

    generated, _ = generate_lock_for_directory(contracts_copy)
    write_lock_atomic(generated, lock_file)
    assert len(generated.contracts) == 1
    assert lock_file.is_file()

    # Loading with matching lockfile succeeds
    reg = PromptRegistry.from_directory(contracts_copy, lock_file=lock_file)
    assert len(reg) == 1

    # Modifying a file on disk without updating lockfile causes verification failure
    user_md = contracts_copy / "career.application-answer" / "1.0.0" / "user.md"
    user_md.write_text(
        user_md.read_text(encoding="utf-8") + "\nTampered content.\n",
        encoding="utf-8",
    )
    with pytest.raises(LockMismatchError) as mismatch_exc:
        PromptRegistry.from_directory(contracts_copy, lock_file=lock_file)
    assert mismatch_exc.value.code == ErrorCode.LOCK_DIGEST_MISMATCH

    # Overwriting existing lockfile with different digest without allow_update fails
    updated_lock, _ = generate_lock_for_directory(contracts_copy)
    with pytest.raises(LockMismatchError) as overwrite_exc:
        write_lock_atomic(updated_lock, lock_file, allow_update=False)
    assert overwrite_exc.value.code == ErrorCode.LOCK_OVERWRITE_REFUSED

    # Updating lockfile with allow_update=True succeeds
    write_lock_atomic(updated_lock, lock_file, allow_update=True)
    reg2 = PromptRegistry.from_directory(contracts_copy, lock_file=lock_file)
    assert len(reg2) == 1


def test_lock_verification_rejects_unlocked_bundle_directory(
    examples_dir: Path, tmp_path: Path
) -> None:
    contracts_copy = tmp_path / "contracts"
    shutil.copytree(examples_dir / "contracts", contracts_copy)
    lock_file = tmp_path / "contracts.lock.json"
    generated, _ = generate_lock_for_directory(contracts_copy)
    write_lock_atomic(generated, lock_file)

    # Add a new version directory not present in lockfile
    extra_dir = contracts_copy / "career.application-answer" / "1.1.0"
    shutil.copytree(
        contracts_copy / "career.application-answer" / "1.0.0",
        extra_dir,
    )
    manifest_path = extra_dir / "contract.toml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace('version = "1.0.0"', 'version = "1.1.0"'),
        encoding="utf-8",
    )

    with pytest.raises(LockMismatchError) as extra_exc:
        PromptRegistry.from_directory(contracts_copy, lock_file=lock_file)
    assert extra_exc.value.code == ErrorCode.LOCK_ENTRY_MISSING


def test_parse_lock_bytes_and_lock_model_validation_edge_cases(tmp_path: Path) -> None:
    from prompt_contracts.errors import UnsupportedFormatError
    from prompt_contracts.identity.lock import (
        ContractLock,
        LockEntry,
        parse_lock_bytes,
        read_lock_file,
    )

    valid_digest = "sha256:" + "a" * 64
    e1 = LockEntry(
        name="study.quiz",
        version="1.0.0",
        path="contracts/study.quiz/1.0.0",
        bundle_digest=valid_digest,
    )
    assert e1.to_dict()["name"] == "study.quiz"

    with pytest.raises(LockMismatchError):
        LockEntry(
            name="study.quiz",
            version="1.0.0",
            path="contracts/study.quiz/1.0.0",
            bundle_digest="md5:invalid",
        )

    with pytest.raises(UnsupportedFormatError):
        ContractLock(contracts=(e1,), lock_format=2)

    with pytest.raises(UnsupportedFormatError):
        ContractLock(contracts=(e1,), digest_algorithm="sha512")

    with pytest.raises(LockMismatchError):
        ContractLock(contracts=(e1, e1))

    e2_colliding_path = LockEntry(
        name="study.quiz",
        version="1.1.0",
        path="contracts/STUDY.QUIZ/1.0.0",
        bundle_digest=valid_digest,
    )
    with pytest.raises(LockMismatchError):
        ContractLock(contracts=(e1, e2_colliding_path))

    # parse_lock_bytes invalid structures
    for bad_json in [
        "[]",
        '{"lock_format": 1, "digest_algorithm": "pc-bundle-v1", "contracts": [], "extra": 1}',
        '{"lock_format": 1}',
        '{"lock_format": 1, "digest_algorithm": "pc-bundle-v1", "contracts": {}}',
        '{"lock_format": 1, "digest_algorithm": "pc-bundle-v1", "contracts": [123]}',
        (
            '{"lock_format": 1, "digest_algorithm": "pc-bundle-v1", '
            '"contracts": [{"name": "a.b", "version": "1.0.0", "path": "a", '
            '"bundle_digest": "' + valid_digest + '", "extra": 1}]}'
        ),
        '{"lock_format": 1, "digest_algorithm": "pc-bundle-v1", "contracts": [{"name": "a.b"}]}',
        (
            '{"lock_format": 1, "digest_algorithm": "pc-bundle-v1", '
            '"contracts": [{"name": 1, "version": "1.0.0", "path": "a", '
            '"bundle_digest": "' + valid_digest + '"}]}'
        ),
        (
            '{"lock_format": 1, "digest_algorithm": "pc-bundle-v1", '
            '"contracts": [{"name": "BAD", "version": "1.0.0", "path": "a", '
            '"bundle_digest": "' + valid_digest + '"}]}'
        ),
    ]:
        with pytest.raises(LockMismatchError):
            parse_lock_bytes(bad_json)

    for unsupported_json in [
        '{"lock_format": 2, "digest_algorithm": "pc-bundle-v1", "contracts": []}',
        '{"lock_format": 1, "digest_algorithm": "blake2", "contracts": []}',
    ]:
        with pytest.raises(UnsupportedFormatError):
            parse_lock_bytes(unsupported_json)

    with pytest.raises(LockMismatchError):
        read_lock_file(tmp_path / "missing.lock.json")

    # Idempotent write_lock_atomic when identical
    lock = ContractLock(contracts=(e1,))
    target = tmp_path / "same.lock.json"
    write_lock_atomic(lock, target)
    write_lock_atomic(lock, target, allow_update=False)
