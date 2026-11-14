"""Snapshot loader connecting resource readers, manifest validation, schemas, and templates."""

from __future__ import annotations

from pathlib import Path

from prompt_contracts.contract import Contract
from prompt_contracts.errors import (
    ErrorCode,
    ManifestError,
    PathPolicyError,
    ResourceLimitError,
    TemplateSyntaxError,
    UnsupportedSchemaError,
)
from prompt_contracts.identity.digest import compute_bundle_digest
from prompt_contracts.loading.manifest import MANIFEST_FILENAME, parse_manifest_bytes
from prompt_contracts.loading.resources import (
    BundleResourceReader,
    DirectoryBundleReader,
    PackageResourceBundleReader,
)
from prompt_contracts.rendering.parser import (
    parse_template,
    validate_template_variables_against_schema,
)
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    MessageTemplate,
    OutputMode,
    OutputSpec,
    RuntimePolicy,
    validate_logical_relative_path,
)
from prompt_contracts.validation.json_io import parse_strict_json
from prompt_contracts.validation.profile import CompiledSchema, compile_schema_profile

__all__ = [
    "discover_bundle_directories",
    "load_contract_bundle",
    "load_contract_from_directory",
    "load_contract_from_package",
]


def load_contract_bundle(
    reader: BundleResourceReader,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> Contract:
    """Load, validate, and compile an immutable :class:`Contract` from ``reader``.

    Reads each referenced file once into an in-memory byte snapshot, verifies complete
    asset closure (failing on any unreferenced file in the bundle directory), computes
    ``pc-bundle-v1`` identity from those exact bytes, and compiles schemas and templates.
    """
    present_files = reader.list_files(policy=policy)
    present_set = set(present_files)
    if MANIFEST_FILENAME not in present_set:
        raise PathPolicyError(
            f"Bundle is missing required '{MANIFEST_FILENAME}'",
            code=ErrorCode.ASSET_NOT_FOUND,
            source_path=MANIFEST_FILENAME,
        )

    manifest_bytes = reader.read_bytes(
        MANIFEST_FILENAME,
        max_bytes=policy.max_manifest_bytes,
    )
    manifest = parse_manifest_bytes(manifest_bytes, policy=policy, source_path=MANIFEST_FILENAME)
    ref_str = str(manifest.ref)

    referenced = set(manifest.referenced_files)
    missing = sorted(referenced - present_set)
    if missing:
        raise PathPolicyError(
            f"Manifest references missing bundle file(s): {missing}",
            code=ErrorCode.ASSET_NOT_FOUND,
            contract_ref=ref_str,
            source_path=missing[0],
        )

    unreferenced = sorted(present_set - referenced)
    if unreferenced:
        raise PathPolicyError(
            f"Unreferenced file(s) found inside runtime contract directory: {unreferenced}",
            code=ErrorCode.UNREFERENCED_BUNDLE_ASSET,
            contract_ref=ref_str,
            source_path=unreferenced[0],
        )

    snapshot: dict[str, bytes] = {MANIFEST_FILENAME: manifest_bytes}
    total_bytes = len(manifest_bytes)
    if total_bytes > policy.max_bundle_bytes:
        raise ResourceLimitError(
            f"Bundle size ({total_bytes} bytes) exceeds limit ({policy.max_bundle_bytes} bytes)",
            code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
            contract_ref=ref_str,
        )

    schema_files = {manifest.input_schema}
    if manifest.output_schema is not None:
        schema_files.add(manifest.output_schema)

    for rel_path in manifest.referenced_files:
        if rel_path == MANIFEST_FILENAME:
            continue
        file_limit = (
            policy.max_schema_bytes if rel_path in schema_files else policy.max_template_bytes
        )
        file_bytes = reader.read_bytes(
            rel_path,
            max_bytes=file_limit,
            contract_ref=ref_str,
        )
        total_bytes += len(file_bytes)
        if total_bytes > policy.max_bundle_bytes:
            raise ResourceLimitError(
                f"Cumulative bundle size ({total_bytes} bytes) "
                f"exceeds limit ({policy.max_bundle_bytes} bytes)",
                code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
                contract_ref=ref_str,
                source_path=rel_path,
            )
        snapshot[rel_path] = file_bytes

    bundle_digest = compute_bundle_digest(snapshot)

    raw_input_schema = parse_strict_json(
        snapshot[manifest.input_schema],
        max_bytes=policy.max_schema_bytes,
        max_depth=policy.max_nesting_depth,
        error_cls=UnsupportedSchemaError,
        contract_ref=ref_str,
        source_path=manifest.input_schema,
    )
    if not isinstance(raw_input_schema, dict):
        raise UnsupportedSchemaError(
            "Input schema must be a JSON object",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=ref_str,
            source_path=manifest.input_schema,
        )
    compiled_input = compile_schema_profile(
        raw_input_schema,
        is_input_schema=True,
        policy=policy,
        contract_ref=ref_str,
        source_path=manifest.input_schema,
    )

    compiled_output: CompiledSchema | None = None
    if manifest.output_mode == OutputMode.JSON:
        assert manifest.output_schema is not None
        raw_output_schema = parse_strict_json(
            snapshot[manifest.output_schema],
            max_bytes=policy.max_schema_bytes,
            max_depth=policy.max_nesting_depth,
            error_cls=UnsupportedSchemaError,
            contract_ref=ref_str,
            source_path=manifest.output_schema,
        )
        if not isinstance(raw_output_schema, dict):
            raise UnsupportedSchemaError(
                "Output schema must be a JSON object",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=ref_str,
                source_path=manifest.output_schema,
            )
        compiled_output = compile_schema_profile(
            raw_output_schema,
            is_input_schema=False,
            policy=policy,
            contract_ref=ref_str,
            source_path=manifest.output_schema,
        )
        output_spec = OutputSpec(
            mode=OutputMode.JSON,
            schema_file=manifest.output_schema,
            schema=compiled_output.raw_schema,
        )
    else:
        output_spec = OutputSpec(
            mode=OutputMode.TEXT,
            min_length=manifest.output_min_length,
            max_length=manifest.output_max_length,
        )

    compiled_templates: list[MessageTemplate] = []
    for role, file_rel in manifest.messages:
        raw_tmpl_bytes = snapshot[file_rel]
        try:
            raw_tmpl_text = raw_tmpl_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            raise TemplateSyntaxError(
                f"Template file {file_rel!r} is not valid UTF-8",
                code=ErrorCode.TEMPLATE_SYNTAX_INVALID,
                contract_ref=ref_str,
                source_path=file_rel,
            ) from None
        tokens = parse_template(
            raw_tmpl_text,
            source_path=file_rel,
            contract_ref=ref_str,
        )
        compiled_templates.append(
            MessageTemplate(
                role=role,
                file=file_rel,
                raw_text=raw_tmpl_text,
                tokens=tokens,
            )
        )

    validate_template_variables_against_schema(
        compiled_templates,
        compiled_input.raw_schema,
        contract_ref=ref_str,
    )

    return Contract(
        ref=manifest.ref,
        format_version=manifest.format_version,
        description=manifest.description,
        renderer=manifest.renderer,
        bundle_digest=bundle_digest,
        policy=policy,
        messages=tuple(compiled_templates),
        output_spec=output_spec,
        _compiled_input_schema=compiled_input,
        _compiled_output_schema=compiled_output,
        _asset_bytes=snapshot,
    )


def load_contract_from_directory(
    bundle_dir: Path,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> Contract:
    """Load a contract bundle from a local filesystem directory."""
    reader = DirectoryBundleReader(Path(bundle_dir))
    return load_contract_bundle(reader, policy=policy)


def load_contract_from_package(
    package: str,
    resource_path: str = "",
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> Contract:
    """Load a contract bundle from an installed Python package resource."""
    reader = PackageResourceBundleReader(package, resource_path)
    return load_contract_bundle(reader, policy=policy)


def discover_bundle_directories(root: Path) -> tuple[tuple[str, Path], ...]:
    """Discover contract bundle directories containing ``contract.toml`` under ``root``.

    Returns sorted ``(logical_lock_path, filesystem_path)`` pairs. When ``root.name ==
    'contracts'``,
    the logical lock path is prefixed with ``contracts/`` so ``prompt-contracts lock contracts/``
    produces portable paths matching ``contracts/<name>/<version>``.
    """
    root_path = Path(root)
    if root_path.is_symlink():
        raise PathPolicyError(
            "Contracts root directory cannot be a symlink",
            code=ErrorCode.PATH_SYMLINK_REJECTED,
        )
    if not root_path.exists() or not root_path.is_dir():
        raise PathPolicyError(
            "Contracts root directory does not exist",
            code=ErrorCode.ASSET_NOT_FOUND,
        )

    if (root_path / MANIFEST_FILENAME).is_file():
        return ((root_path.name, root_path),)

    manifests: list[Path] = []

    pending = [root_path]
    while pending:
        cur = pending.pop()
        folded_names: set[str] = set()
        for child in sorted(cur.iterdir(), key=lambda p: p.name):
            folded = child.name.casefold()
            if folded in folded_names:
                raise PathPolicyError(
                    "Case-folding collision in contracts tree",
                    code=ErrorCode.PATH_CASE_COLLISION,
                )
            folded_names.add(folded)
            if child.is_symlink():
                raise PathPolicyError(
                    f"Symlink is not permitted in contracts tree: {child.name!r}",
                    code=ErrorCode.PATH_SYMLINK_REJECTED,
                )
            if child.is_dir():
                validate_logical_relative_path(child.relative_to(root_path).as_posix())
                if (child / MANIFEST_FILENAME).exists():
                    manifests.append(child)
                else:
                    pending.append(child)
    if not manifests:
        raise ManifestError(
            "No contract bundles (containing contract.toml) found under directory",
            code=ErrorCode.ASSET_NOT_FOUND,
        )

    results: list[tuple[str, Path]] = []
    for bundle_dir in manifests:
        rel_posix = bundle_dir.relative_to(root_path).as_posix()
        if root_path.name == "contracts" and not rel_posix.startswith("contracts/"):
            logical = f"contracts/{rel_posix}"
        else:
            logical = rel_posix
        results.append((logical, bundle_dir))

    results.sort(key=lambda item: item[0])
    return tuple(results)
