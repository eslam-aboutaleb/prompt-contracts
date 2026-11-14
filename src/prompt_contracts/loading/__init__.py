"""Manifest parsing, path confinement, and bundle resource loading."""

from __future__ import annotations

from prompt_contracts.loading.loader import (
    discover_bundle_directories,
    load_contract_bundle,
    load_contract_from_directory,
    load_contract_from_package,
)
from prompt_contracts.loading.manifest import (
    MANIFEST_FILENAME,
    SUPPORTED_FORMAT_VERSION,
    ParsedManifest,
    parse_manifest_bytes,
)
from prompt_contracts.loading.paths import (
    read_bounded_file_bytes,
    resolve_confined_filesystem_path,
    scan_bundle_directory_files,
    validate_logical_relative_path,
)
from prompt_contracts.loading.resources import (
    BundleResourceReader,
    DirectoryBundleReader,
    PackageResourceBundleReader,
)

__all__ = [
    "MANIFEST_FILENAME",
    "SUPPORTED_FORMAT_VERSION",
    "BundleResourceReader",
    "DirectoryBundleReader",
    "PackageResourceBundleReader",
    "ParsedManifest",
    "discover_bundle_directories",
    "load_contract_bundle",
    "load_contract_from_directory",
    "load_contract_from_package",
    "parse_manifest_bytes",
    "read_bounded_file_bytes",
    "resolve_confined_filesystem_path",
    "scan_bundle_directory_files",
    "validate_logical_relative_path",
]
