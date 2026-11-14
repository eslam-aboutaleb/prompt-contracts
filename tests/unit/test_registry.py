"""Unit tests for PromptRegistry lookup, freeze, idempotent registration, and conflict
detection (T12).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from prompt_contracts import (
    Contract,
    ContractIdentityConflict,
    ContractRef,
    ErrorCode,
    PromptContractError,
    PromptRegistry,
)


def test_relative_lock_path_is_resolved_against_root_not_working_directory(
    examples_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "contracts.lock.json").write_text("invalid shadow lock", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    registry = PromptRegistry.from_directory(examples_dir, lock_file="contracts.lock.json")
    assert "career.application-answer@1.0.0" in registry


def test_registry_lookup_idempotent_register_conflict_and_freeze(
    examples_dir: Path, tmp_path: Path
) -> None:
    bundle_dir = examples_dir / "contracts" / "career.application-answer" / "1.0.0"
    contract = Contract.from_directory(bundle_dir)

    reg = PromptRegistry()
    assert len(reg) == 0
    reg.register(contract)
    # Idempotent registration of identical digest succeeds
    reg.register(contract)
    assert len(reg) == 1
    assert ContractRef("career.application-answer", "1.0.0") in reg
    assert "career.application-answer@1.0.0" in reg

    fetched = reg.get("career.application-answer@1.0.0")
    assert fetched.bundle_digest == contract.bundle_digest
    fetched_by_ref = reg.get(ContractRef("career.application-answer", "1.0.0"))
    assert fetched_by_ref is fetched

    with pytest.raises(PromptContractError) as not_found_exc:
        reg.get("career.application-answer@9.9.9")
    assert not_found_exc.value.code == ErrorCode.CONTRACT_NOT_FOUND

    # Mutate copy of bundle with same (name, version) and verify conflict detection
    mutated_dir = tmp_path / "career.application-answer" / "1.0.0"
    shutil.copytree(bundle_dir, mutated_dir)
    (mutated_dir / "user.md").write_text(
        (mutated_dir / "user.md").read_text(encoding="utf-8") + "\nExtra line.\n",
        encoding="utf-8",
    )
    mutated_contract = Contract.from_directory(mutated_dir)
    with pytest.raises(ContractIdentityConflict) as conflict_exc:
        reg.register(mutated_contract)
    assert conflict_exc.value.code == ErrorCode.IDENTITY_CONFLICT

    # Freeze registry and verify subsequent registration fails
    reg.freeze()
    assert reg.is_frozen is True
    with pytest.raises(ContractIdentityConflict) as frozen_exc:
        reg.register(contract)
    assert frozen_exc.value.code == ErrorCode.REGISTRY_FROZEN


def test_registry_collection_helpers_and_lock_verification_errors(
    examples_dir: Path, tmp_path: Path
) -> None:
    from prompt_contracts.errors import LockMismatchError, PathPolicyError
    from prompt_contracts.identity.lock import ContractLock, LockEntry
    from prompt_contracts.registry import verify_directory_against_lock

    reg = PromptRegistry.from_unlocked_directory(examples_dir / "contracts")
    assert reg.policy is not None
    assert len(reg.refs()) == 1
    assert len(reg.contracts()) == 1
    assert "not-a-valid-ref" not in reg
    assert 12345 not in reg

    with pytest.raises(LockMismatchError):
        verify_directory_against_lock(examples_dir / "contracts", ContractLock(contracts=()))

    missing_lock = ContractLock(
        contracts=(
            LockEntry(
                name="demo.missing",
                version="1.0.0",
                path="demo.missing/1.0.0",
                bundle_digest="sha256:" + "0" * 64,
            ),
        )
    )
    with pytest.raises(LockMismatchError):
        verify_directory_against_lock(examples_dir / "contracts", missing_lock)

    wrong_ref_lock = ContractLock(
        contracts=(
            LockEntry(
                name="demo.wrong",
                version="1.0.0",
                path="career.application-answer/1.0.0",
                bundle_digest="sha256:" + "0" * 64,
            ),
        )
    )
    with pytest.raises(LockMismatchError):
        verify_directory_against_lock(examples_dir / "contracts", wrong_ref_lock)

    with pytest.raises(PathPolicyError):
        PromptRegistry.from_package_resources("nonexistent_package_xyz_123")
