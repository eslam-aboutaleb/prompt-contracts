"""Explicit, lock-verified, freezable prompt contract registry."""

from __future__ import annotations

import importlib.resources
from importlib.resources.abc import Traversable
from pathlib import Path

from prompt_contracts.contract import Contract
from prompt_contracts.errors import (
    ContractIdentityConflict,
    ErrorCode,
    LockMismatchError,
    PathPolicyError,
    PromptContractError,
    ResourceLimitError,
)
from prompt_contracts.identity.lock import (
    ContractLock,
    LockEntry,
    parse_lock_bytes,
    read_lock_file,
)
from prompt_contracts.loading.loader import (
    discover_bundle_directories,
    load_contract_bundle,
    load_contract_from_directory,
)
from prompt_contracts.loading.manifest import MANIFEST_FILENAME
from prompt_contracts.loading.resources import (
    PackageResourceBundleReader,
    resolve_traversable_subpath,
)
from prompt_contracts.types import DEFAULT_RUNTIME_POLICY, ContractRef, RuntimePolicy

__all__ = [
    "PromptRegistry",
    "generate_lock_for_directory",
    "verify_directory_against_lock",
]


def _discover_package_bundles(root: Traversable, *, prefix: str = "") -> set[str]:
    """Discover the catalog independently of the lock, including zipped resources."""
    found: set[str] = set()
    pending = [(root, prefix)]
    while pending:
        node, relative = pending.pop()
        if isinstance(node, Path) and node.is_symlink():
            raise PathPolicyError(
                "Symlink is not permitted in package contracts tree",
                code=ErrorCode.PATH_SYMLINK_REJECTED,
            )
        if node.joinpath(MANIFEST_FILENAME).is_file():
            found.add(relative)
            continue
        for child in node.iterdir():
            if isinstance(child, Path) and child.is_symlink():
                raise PathPolicyError(
                    "Symlink is not permitted in package contracts tree",
                    code=ErrorCode.PATH_SYMLINK_REJECTED,
                )
            if child.is_dir() and child.name != "__pycache__":
                child_path = f"{relative}/{child.name}".strip("/")
                # Path validation also bounds traversal depth through its length ceiling.
                resolve_traversable_subpath(root, child_path.removeprefix(prefix + "/"))
                pending.append((child, child_path))
    return found


def _resolve_bundle_dir_for_lock_entry(root: Path, entry_path: str) -> Path:
    """Resolve a lock entry's logical path against ``root`` (supporting both repo root and
    ``contracts/`` root).
    """
    candidate = root / entry_path
    if (candidate / MANIFEST_FILENAME).exists():
        return candidate
    if root.name == "contracts" and entry_path.startswith("contracts/"):
        stripped = entry_path.removeprefix("contracts/")
        alt_candidate = root / stripped
        if (alt_candidate / MANIFEST_FILENAME).exists():
            return alt_candidate
    return candidate


def generate_lock_for_directory(
    root: Path | str,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> tuple[ContractLock, tuple[Contract, ...]]:
    """Discover, load, and validate all contracts under ``root`` and construct a
    :class:`ContractLock`.
    """
    root_path = Path(root)
    discovered = discover_bundle_directories(root_path)
    entries: list[LockEntry] = []
    contracts: list[Contract] = []
    seen_refs: dict[ContractRef, str] = {}

    for logical_path, bundle_dir in discovered:
        contract = load_contract_from_directory(bundle_dir, policy=policy)
        if contract.ref in seen_refs:
            raise ContractIdentityConflict(
                f"Duplicate contract {contract.ref} found at "
                f"{logical_path!r} and {seen_refs[contract.ref]!r}",
                code=ErrorCode.IDENTITY_CONFLICT,
                contract_ref=str(contract.ref),
            )
        seen_refs[contract.ref] = logical_path
        contracts.append(contract)
        entries.append(
            LockEntry(
                name=contract.name,
                version=contract.version,
                path=logical_path,
                bundle_digest=contract.bundle_digest,
            )
        )

    lock = ContractLock(contracts=tuple(entries))
    return lock, tuple(contracts)


def verify_directory_against_lock(
    root: Path | str,
    lock: ContractLock,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> tuple[Contract, ...]:
    """Verify every contract on disk under ``root`` against ``lock``, failing on missing, extra, or
    mutated bundles.
    """
    root_path = Path(root)
    if not lock.contracts:
        raise LockMismatchError(
            "Lockfile contains zero contract entries",
            code=ErrorCode.LOCK_INVALID,
        )

    # Check if there is a contracts/ subdirectory or if root itself holds bundles
    search_root = (
        root_path / "contracts"
        if (root_path / "contracts").is_dir() and not (root_path / MANIFEST_FILENAME).exists()
        else root_path
    )
    discovered = discover_bundle_directories(search_root)
    discovered_by_dir: dict[Path, str] = {b_dir.resolve(): logical for logical, b_dir in discovered}

    verified_contracts: list[Contract] = []
    matched_dirs: set[Path] = set()

    for entry in lock.contracts:
        bundle_dir = _resolve_bundle_dir_for_lock_entry(root_path, entry.path)
        if not bundle_dir.exists() or not bundle_dir.is_dir():
            raise LockMismatchError(
                f"Locked contract {entry.ref} directory not found at {entry.path!r}",
                code=ErrorCode.LOCK_ENTRY_MISSING,
                contract_ref=str(entry.ref),
                source_path=entry.path,
            )
        contract = load_contract_from_directory(bundle_dir, policy=policy)
        if contract.ref != entry.ref:
            raise LockMismatchError(
                f"Manifest identity {contract.ref} at {entry.path!r} "
                f"does not match lockfile entry {entry.ref}",
                code=ErrorCode.LOCK_DIGEST_MISMATCH,
                contract_ref=str(entry.ref),
                source_path=entry.path,
            )
        if contract.bundle_digest != entry.bundle_digest:
            raise LockMismatchError(
                f"Bundle digest mismatch for {entry.ref}: lock expected "
                f"{entry.bundle_digest}, computed {contract.bundle_digest}",
                code=ErrorCode.LOCK_DIGEST_MISMATCH,
                contract_ref=str(entry.ref),
                source_path=entry.path,
            )
        matched_dirs.add(bundle_dir.resolve())
        verified_contracts.append(contract)

    unlocked_dirs = [
        logical
        for resolved_dir, logical in discovered_by_dir.items()
        if resolved_dir not in matched_dirs
    ]
    if unlocked_dirs:
        raise LockMismatchError(
            "Unlocked contract bundle(s) present on disk but "
            f"missing from lockfile: {sorted(unlocked_dirs)}",
            code=ErrorCode.LOCK_ENTRY_MISSING,
            source_path=unlocked_dirs[0],
        )

    return tuple(verified_contracts)


class PromptRegistry:
    """Explicit, non-global collection of verified :class:`Contract` objects.

    Supports idempotent registration of identical digests, rejects conflicting digests
    for the same ``(name, version)``, and can be permanently frozen after startup.
    """

    def __init__(
        self,
        *,
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    ) -> None:
        self._policy = policy
        self._contracts: dict[ContractRef, Contract] = {}
        self._frozen = False

    @property
    def policy(self) -> RuntimePolicy:
        return self._policy

    @property
    def is_frozen(self) -> bool:
        return self._frozen

    def freeze(self) -> PromptRegistry:
        """Permanently prevent further registration on this registry instance."""
        self._frozen = True
        return self

    def register(self, contract: Contract) -> Contract:
        """Register a verified :class:`Contract`.

        Idempotent if the same ``ContractRef`` and ``bundle_digest`` are already
        registered; raises :class:`ContractIdentityConflict` if frozen or if a different
        digest is already registered under ``contract.ref``.
        """
        if self._frozen:
            raise ContractIdentityConflict(
                "Cannot register a contract on a frozen PromptRegistry",
                code=ErrorCode.REGISTRY_FROZEN,
                contract_ref=str(contract.ref),
            )
        existing = self._contracts.get(contract.ref)
        if existing is not None:
            if existing.bundle_digest != contract.bundle_digest:
                raise ContractIdentityConflict(
                    f"Conflicting bundle digest registered for {contract.ref}",
                    code=ErrorCode.IDENTITY_CONFLICT,
                    contract_ref=str(contract.ref),
                )
            return existing
        self._contracts[contract.ref] = contract
        return contract

    def get(self, ref: ContractRef | str) -> Contract:
        """Retrieve a contract by exact :class:`ContractRef` or ``<name>@<version>`` string."""
        parsed_ref = ref if isinstance(ref, ContractRef) else ContractRef.parse(ref)
        contract = self._contracts.get(parsed_ref)
        if contract is None:
            raise PromptContractError(
                f"Contract {parsed_ref} is not registered",
                code=ErrorCode.CONTRACT_NOT_FOUND,
                contract_ref=str(parsed_ref),
            )
        return contract

    def __contains__(self, ref: object) -> bool:
        if isinstance(ref, ContractRef):
            return ref in self._contracts
        if isinstance(ref, str):
            try:
                parsed = ContractRef.parse(ref)
            except Exception:
                return False
            return parsed in self._contracts
        return False

    def __len__(self) -> int:
        return len(self._contracts)

    def refs(self) -> tuple[ContractRef, ...]:
        """Return all registered :class:`ContractRef` keys in sorted order."""
        return tuple(sorted(self._contracts.keys()))

    def contracts(self) -> tuple[Contract, ...]:
        """Return all registered :class:`Contract` objects sorted by reference."""
        return tuple(self._contracts[r] for r in self.refs())

    @classmethod
    def from_directory(
        cls,
        root: Path | str,
        *,
        lock_file: Path | str,
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    ) -> PromptRegistry:
        """Construct a registry from ``root`` and verify every bundle against ``lock_file``."""
        root_path = Path(root)
        lock_path = Path(lock_file)
        if not lock_path.is_absolute():
            lock_path = root_path / lock_path
        lock = read_lock_file(lock_path, policy=policy)
        verified = verify_directory_against_lock(root_path, lock, policy=policy)
        registry = cls(policy=policy)
        for contract in verified:
            registry.register(contract)
        return registry

    @classmethod
    def from_unlocked_directory(
        cls,
        root: Path | str,
        *,
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    ) -> PromptRegistry:
        """Construct an unlocked registry from ``root`` for authoring and offline unit tests."""
        _, contracts = generate_lock_for_directory(Path(root), policy=policy)
        registry = cls(policy=policy)
        for contract in contracts:
            registry.register(contract)
        return registry

    @classmethod
    def from_package_resources(
        cls,
        package: str,
        *,
        lock_resource: str = "contracts.lock.json",
        resource_root: str = "",
        policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    ) -> PromptRegistry:
        """Construct a lock-verified registry from an installed Python package via
        ``importlib.resources``.
        """
        try:
            pkg_files = importlib.resources.files(package)
        except Exception:
            raise PathPolicyError(
                f"Unable to locate Python package {package!r}",
                code=ErrorCode.ASSET_NOT_FOUND,
            ) from None

        base_root = (
            resolve_traversable_subpath(pkg_files, resource_root) if resource_root else pkg_files
        )
        lock_node = resolve_traversable_subpath(base_root, lock_resource)
        if not lock_node.is_file():
            raise LockMismatchError(
                f"Package lock resource {lock_resource!r} not found in {package!r}",
                code=ErrorCode.LOCK_INVALID,
                source_path=lock_resource,
            )
        with lock_node.open("rb") as handle:
            lock_bytes = handle.read(policy.max_schema_bytes + 1)
        if len(lock_bytes) > policy.max_schema_bytes:
            raise ResourceLimitError(
                "Package lock resource exceeds the configured byte limit",
                code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
                source_path=lock_resource,
            )
        lock = parse_lock_bytes(lock_bytes, policy=policy, source_path=lock_resource)
        if not lock.contracts:
            raise LockMismatchError(
                "Package lockfile contains zero contract entries",
                code=ErrorCode.LOCK_INVALID,
                source_path=lock_resource,
            )

        catalog = base_root.joinpath("contracts")
        if catalog.is_dir():
            discovered = _discover_package_bundles(catalog, prefix="contracts")
        else:
            discovered = _discover_package_bundles(base_root)
        if discovered != {entry.path for entry in lock.contracts}:
            raise LockMismatchError(
                "Package contract catalog does not match the locked bundle paths",
                code=ErrorCode.LOCK_ENTRY_MISSING,
                source_path=lock_resource,
            )

        registry = cls(policy=policy)
        for entry in lock.contracts:
            subpath = f"{resource_root}/{entry.path}".strip("/") if resource_root else entry.path
            reader = PackageResourceBundleReader(package, subpath)
            contract = load_contract_bundle(reader, policy=policy)
            if contract.ref != entry.ref:
                raise LockMismatchError(
                    f"Package resource manifest {contract.ref} "
                    f"does not match lock entry {entry.ref}",
                    code=ErrorCode.LOCK_DIGEST_MISMATCH,
                    contract_ref=str(entry.ref),
                )
            if contract.bundle_digest != entry.bundle_digest:
                raise LockMismatchError(
                    f"Package resource digest mismatch for {entry.ref}",
                    code=ErrorCode.LOCK_DIGEST_MISMATCH,
                    contract_ref=str(entry.ref),
                )
            registry.register(contract)
        return registry
