"""TOML manifest parser and format validator for ``contract.toml``."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass

from prompt_contracts.errors import (
    ErrorCode,
    ManifestError,
    ResourceLimitError,
    UnsupportedFormatError,
)
from prompt_contracts.loading.paths import validate_logical_relative_path
from prompt_contracts.rendering.parser import SUPPORTED_RENDERER_ID
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    ContractRef,
    MessageRole,
    OutputMode,
    RuntimePolicy,
)

__all__ = [
    "MANIFEST_FILENAME",
    "SUPPORTED_FORMAT_VERSION",
    "ParsedManifest",
    "parse_manifest_bytes",
]

MANIFEST_FILENAME = "contract.toml"
SUPPORTED_FORMAT_VERSION = 1

_ALLOWED_TOP_KEYS = frozenset(
    {
        "format_version",
        "name",
        "version",
        "description",
        "renderer",
        "input_schema",
        "output",
        "messages",
    }
)
_REQUIRED_TOP_KEYS = frozenset(
    {
        "format_version",
        "name",
        "version",
        "renderer",
        "input_schema",
        "output",
        "messages",
    }
)
_ALLOWED_OUTPUT_JSON_KEYS = frozenset({"mode", "schema"})
_ALLOWED_OUTPUT_TEXT_KEYS = frozenset({"mode", "min_length", "max_length"})
_ALLOWED_MESSAGE_KEYS = frozenset({"role", "file"})


@dataclass(frozen=True, slots=True)
class ParsedManifest:
    """Validated structure of ``contract.toml``."""

    format_version: int
    ref: ContractRef
    description: str | None
    renderer: str
    input_schema: str
    output_mode: OutputMode
    output_schema: str | None
    output_min_length: int | None
    output_max_length: int | None
    messages: tuple[tuple[MessageRole, str], ...]

    @property
    def referenced_files(self) -> tuple[str, ...]:
        """Ordered unique logical paths referenced by this manifest, including ``contract.toml``."""
        seen: dict[str, None] = {MANIFEST_FILENAME: None, self.input_schema: None}
        if self.output_schema is not None:
            seen[self.output_schema] = None
        for _, msg_file in self.messages:
            seen[msg_file] = None
        return tuple(seen.keys())


def parse_manifest_bytes(
    raw_bytes: bytes,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    source_path: str = MANIFEST_FILENAME,
) -> ParsedManifest:
    """Decode and validate ``contract.toml`` bytes under ``policy``."""
    if len(raw_bytes) > policy.max_manifest_bytes:
        raise ResourceLimitError(
            f"Manifest size ({len(raw_bytes)} bytes) exceeds "
            f"limit ({policy.max_manifest_bytes} bytes)",
            code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
            source_path=source_path,
        )
    try:
        raw_text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ManifestError(
            "Manifest is not valid UTF-8",
            code=ErrorCode.MANIFEST_INVALID_TOML,
            source_path=source_path,
        ) from None

    try:
        data = tomllib.loads(raw_text)
    except tomllib.TOMLDecodeError:
        raise ManifestError(
            "Invalid TOML syntax or duplicate key in contract manifest",
            code=ErrorCode.MANIFEST_INVALID_TOML,
            source_path=source_path,
        ) from None

    unknown_top = set(data.keys()) - _ALLOWED_TOP_KEYS
    if unknown_top:
        raise ManifestError(
            f"Unknown field(s) in contract manifest: {sorted(unknown_top)}",
            code=ErrorCode.MANIFEST_UNKNOWN_FIELD,
            source_path=source_path,
        )
    missing_top = _REQUIRED_TOP_KEYS - set(data.keys())
    if missing_top:
        raise ManifestError(
            f"Missing required field(s) in contract manifest: {sorted(missing_top)}",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            source_path=source_path,
        )

    fmt_ver = data["format_version"]
    if type(fmt_ver) is not int:
        raise ManifestError(
            "Manifest 'format_version' must be an integer",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            source_path=source_path,
        )
    if fmt_ver != SUPPORTED_FORMAT_VERSION:
        raise UnsupportedFormatError(
            f"Unsupported manifest format_version: {fmt_ver} (expected {SUPPORTED_FORMAT_VERSION})",
            code=ErrorCode.UNSUPPORTED_FORMAT_VERSION,
            source_path=source_path,
        )

    raw_name = data["name"]
    raw_version = data["version"]
    if type(raw_name) is not str or type(raw_version) is not str:
        raise ManifestError(
            "Manifest 'name' and 'version' must be strings",
            code=ErrorCode.INVALID_CONTRACT_REF,
            source_path=source_path,
        )
    ref = ContractRef(name=raw_name, version=raw_version)
    ref_str = str(ref)

    description = data.get("description")
    if description is not None and (
        type(description) is not str or not (1 <= len(description) <= 2000)
    ):
        raise ManifestError(
            "Manifest 'description' must be a non-empty string of at most 2000 characters",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            contract_ref=ref_str,
            source_path=source_path,
        )

    renderer = data["renderer"]
    if type(renderer) is not str:
        raise ManifestError(
            "Manifest 'renderer' must be a string",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            contract_ref=ref_str,
            source_path=source_path,
        )
    if renderer != SUPPORTED_RENDERER_ID:
        raise UnsupportedFormatError(
            f"Unsupported renderer {renderer!r} (expected {SUPPORTED_RENDERER_ID!r})",
            code=ErrorCode.UNSUPPORTED_RENDERER,
            contract_ref=ref_str,
            source_path=source_path,
        )

    raw_input_schema = data["input_schema"]
    if type(raw_input_schema) is not str:
        raise ManifestError(
            "Manifest 'input_schema' must be a relative path string",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            contract_ref=ref_str,
            source_path=source_path,
        )
    input_schema_path = validate_logical_relative_path(raw_input_schema, contract_ref=ref_str)

    raw_output = data["output"]
    if not isinstance(raw_output, dict) or "mode" not in raw_output:
        raise ManifestError(
            "Manifest '[output]' table must be an object specifying 'mode'",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            contract_ref=ref_str,
            source_path=source_path,
        )
    raw_mode = raw_output["mode"]
    if raw_mode == "json":
        output_mode = OutputMode.JSON
        unknown_out = set(raw_output.keys()) - _ALLOWED_OUTPUT_JSON_KEYS
        if unknown_out:
            raise ManifestError(
                "Unknown or incompatible field(s) in [output] "
                f"for mode='json': {sorted(unknown_out)}",
                code=ErrorCode.MANIFEST_UNKNOWN_FIELD,
                contract_ref=ref_str,
                source_path=source_path,
            )
        if "schema" not in raw_output or type(raw_output["schema"]) is not str:
            raise ManifestError(
                "Manifest [output] with mode='json' requires a 'schema' path string",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=ref_str,
                source_path=source_path,
            )
        output_schema_path: str | None = validate_logical_relative_path(
            raw_output["schema"], contract_ref=ref_str
        )
        output_min_len: int | None = None
        output_max_len: int | None = None
    elif raw_mode == "text":
        output_mode = OutputMode.TEXT
        unknown_out = set(raw_output.keys()) - _ALLOWED_OUTPUT_TEXT_KEYS
        if unknown_out:
            raise ManifestError(
                "Unknown or incompatible field(s) in [output] "
                f"for mode='text': {sorted(unknown_out)}",
                code=ErrorCode.MANIFEST_UNKNOWN_FIELD,
                contract_ref=ref_str,
                source_path=source_path,
            )
        min_l = raw_output.get("min_length")
        max_l = raw_output.get("max_length")
        if (
            type(min_l) is not int
            or type(max_l) is not int
            or min_l < 0
            or max_l < 1
            or min_l > max_l
        ):
            raise ManifestError(
                "Manifest [output] with mode='text' requires "
                "integer min_length (>= 0) <= max_length (>= 1)",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=ref_str,
                source_path=source_path,
            )
        output_schema_path = None
        output_min_len = min_l
        output_max_len = max_l
    else:
        raise ManifestError(
            f"Unsupported output mode {raw_mode!r}; expected 'json' or 'text'",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            contract_ref=ref_str,
            source_path=source_path,
        )

    raw_messages = data["messages"]
    if not isinstance(raw_messages, list) or len(raw_messages) == 0:
        raise ManifestError(
            "Manifest 'messages' must be a non-empty array of tables",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            contract_ref=ref_str,
            source_path=source_path,
        )
    if len(raw_messages) > policy.max_messages:
        raise ResourceLimitError(
            f"Manifest defines {len(raw_messages)} messages, "
            f"exceeding limit of {policy.max_messages}",
            code=ErrorCode.RESOURCE_COUNT_EXCEEDED,
            contract_ref=ref_str,
            source_path=source_path,
        )

    parsed_messages: list[tuple[MessageRole, str]] = []
    for idx, msg in enumerate(raw_messages):
        if not isinstance(msg, dict):
            raise ManifestError(
                f"Manifest message at index {idx} must be a table",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=ref_str,
                source_path=source_path,
            )
        unknown_msg = set(msg.keys()) - _ALLOWED_MESSAGE_KEYS
        if unknown_msg:
            raise ManifestError(
                f"Unknown field(s) in [[messages]] entry {idx}: {sorted(unknown_msg)}",
                code=ErrorCode.MANIFEST_UNKNOWN_FIELD,
                contract_ref=ref_str,
                source_path=source_path,
            )
        if "role" not in msg or "file" not in msg:
            raise ManifestError(
                f"Manifest [[messages]] entry {idx} requires 'role' and 'file'",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=ref_str,
                source_path=source_path,
            )
        raw_role = msg["role"]
        raw_file = msg["file"]
        if raw_role not in ("system", "user", "assistant"):
            raise ManifestError(
                f"Unsupported message role {raw_role!r} at index {idx}",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=ref_str,
                source_path=source_path,
            )
        if type(raw_file) is not str:
            raise ManifestError(
                f"Message 'file' at index {idx} must be a string",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=ref_str,
                source_path=source_path,
            )
        norm_file = validate_logical_relative_path(raw_file, contract_ref=ref_str)
        if norm_file in (MANIFEST_FILENAME, input_schema_path, output_schema_path):
            raise ManifestError(
                f"Message template file {norm_file!r} cannot alias the manifest or schema files",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=ref_str,
                source_path=source_path,
            )
        parsed_messages.append((MessageRole(raw_role), norm_file))

    if output_schema_path is not None and output_schema_path == input_schema_path:
        raise ManifestError(
            "Manifest 'input_schema' and 'output.schema' must reference distinct files",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
            contract_ref=ref_str,
            source_path=source_path,
        )

    return ParsedManifest(
        format_version=fmt_ver,
        ref=ref,
        description=description,
        renderer=renderer,
        input_schema=input_schema_path,
        output_mode=output_mode,
        output_schema=output_schema_path,
        output_min_length=output_min_len,
        output_max_length=output_max_len,
        messages=tuple(parsed_messages),
    )
