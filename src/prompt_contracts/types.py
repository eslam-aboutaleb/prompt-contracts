"""Immutable value types, runtime limits policy, and safe execution metadata."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, TypeAlias

from prompt_contracts.errors import (
    ErrorCode,
    InputValidationError,
    ManifestError,
    PathPolicyError,
    ResourceLimitError,
)

__all__ = [
    "BUNDLE_DIGEST_ALGORITHM",
    "CONTRACT_NAME_RE",
    "CONTRACT_VERSION_RE",
    "DEFAULT_RUNTIME_POLICY",
    "PORTABLE_SEGMENT_RE",
    "WINDOWS_RESERVED_NAMES",
    "ContractRef",
    "ExecutionMetadata",
    "JSONPrimitive",
    "JSONValue",
    "MessageRole",
    "MessageTemplate",
    "OutputMode",
    "OutputSpec",
    "RenderedMessage",
    "RenderedPrompt",
    "RuntimePolicy",
    "TemplateToken",
    "TokenKind",
    "freeze_json_value",
    "serialize_compact_json",
    "thaw_json_value",
    "validate_logical_relative_path",
]

BUNDLE_DIGEST_ALGORITHM = "pc-bundle-v1"
JSONPrimitive: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONPrimitive | Sequence["JSONValue"] | Mapping[str, "JSONValue"]

CONTRACT_NAME_RE = re.compile(r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$")
CONTRACT_VERSION_RE = re.compile(r"^(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)$")
IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
PORTABLE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._-]*$")
WINDOWS_RESERVED_NAMES: frozenset[str] = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }
)


def validate_logical_relative_path(
    raw_path: str,
    *,
    contract_ref: str | None = None,
) -> str:
    """Validate and normalize a portable POSIX logical path relative to a root."""
    if type(raw_path) is not str or not raw_path or len(raw_path) > 512:
        raise PathPolicyError(
            "Asset path must be a non-empty string of at most 512 characters",
            code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            contract_ref=contract_ref,
        )
    if "\x00" in raw_path or "\\" in raw_path or ":" in raw_path:
        raise PathPolicyError(
            "Asset path contains forbidden characters (NUL, backslash, or scheme/drive colon)",
            code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            contract_ref=contract_ref,
        )
    if raw_path.startswith("/") or raw_path.endswith("/"):
        raise PathPolicyError(
            "Asset path must be relative and cannot start or end with '/'",
            code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            contract_ref=contract_ref,
        )

    segments = raw_path.split("/")
    for seg in segments:
        if not seg or seg in (".", ".."):
            raise PathPolicyError(
                "Asset path cannot contain '.', '..', or empty segments",
                code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
                contract_ref=contract_ref,
            )
        if seg.endswith((".", " ")):
            raise PathPolicyError(
                "Asset path segment cannot end with a dot or space",
                code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
                contract_ref=contract_ref,
            )
        if not PORTABLE_SEGMENT_RE.fullmatch(seg):
            raise PathPolicyError(
                f"Asset path segment {seg!r} contains non-portable characters",
                code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
                contract_ref=contract_ref,
            )
        stem = seg.split(".", 1)[0].upper()
        if stem in WINDOWS_RESERVED_NAMES:
            raise PathPolicyError(
                f"Asset path segment {seg!r} uses a reserved platform device name",
                code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
                contract_ref=contract_ref,
            )

    return "/".join(segments)


# Spec-ceiling constants (plan section 8)
SPEC_MAX_MANIFEST_BYTES = 64 * 1024
SPEC_MAX_SCHEMA_BYTES = 256 * 1024
SPEC_MAX_TEMPLATE_BYTES = 256 * 1024
SPEC_MAX_BUNDLE_BYTES = 2 * 1024 * 1024
SPEC_MAX_BUNDLE_FILES = 64
SPEC_MAX_MESSAGES = 32
SPEC_MAX_NESTING_DEPTH = 32
SPEC_MAX_EXPANDED_SCHEMA_NODES = 5_000
SPEC_MAX_INPUT_BYTES = 1024 * 1024
SPEC_MAX_RENDERED_BYTES = 2 * 1024 * 1024
SPEC_MAX_RESPONSE_BYTES = 1024 * 1024
SPEC_MAX_REPORTED_ISSUES = 20

_FORBIDDEN_METADATA_OPTION_KEYS: frozenset[str] = frozenset(
    {
        "api_key",
        "authorization",
        "bearer",
        "content",
        "inputs",
        "messages",
        "output",
        "password",
        "prompt",
        "raw_input",
        "raw_input_hash",
        "raw_output",
        "response_text",
        "secret",
        "token",
    }
)


class MessageRole(StrEnum):
    """Supported static message roles in format v1."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class OutputMode(StrEnum):
    """Supported contract output modes in format v1."""

    JSON = "json"
    TEXT = "text"


class TokenKind(StrEnum):
    """Compiled template token categories for ``placeholders-v1``."""

    LITERAL = "literal"
    VARIABLE = "variable"


def freeze_json_value(
    value: Any,
    *,
    max_depth: int = SPEC_MAX_NESTING_DEPTH,
    max_bytes: int | None = None,
    _current_depth: int = 0,
    _seen: set[int] | None = None,
    _remaining_bytes: list[int] | None = None,
) -> Any:
    """Validate and convert a JSON-compatible Python structure into deeply immutable objects.

    Dicts become ``MappingProxyType`` with sorted string keys; lists and tuples become
    ``tuple``. Rejects arbitrary Python objects, bytes, non-string dict keys, non-finite
    floats, reference cycles, and structures exceeding ``max_depth``.
    """
    remaining = _remaining_bytes
    if remaining is None and max_bytes is not None:
        remaining = [max_bytes]

    def spend(count: int) -> None:
        if remaining is not None:
            remaining[0] -= count
            if remaining[0] < 0:
                raise ResourceLimitError(
                    "JSON value exceeds the configured byte limit",
                    code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
                )

    if type(value) is str:
        # Code points are a lower bound on UTF-8 bytes. Reject huge strings before
        # encoding or escaping them into another allocation.
        if remaining is not None and len(value) + 2 > remaining[0]:
            spend(len(value) + 2)
        try:
            if remaining is None:
                value.encode("utf-8", errors="strict")
            else:
                spend(len(json.dumps(value, ensure_ascii=False).encode("utf-8")))
        except UnicodeEncodeError:
            raise InputValidationError(
                "JSON string contains invalid UTF-8 surrogates",
                code=ErrorCode.INPUT_VALUE_INVALID,
            ) from None
        return value
    if value is None or type(value) in (bool, int):
        if remaining is not None:
            try:
                spend(len(json.dumps(value)))
            except ValueError:
                raise InputValidationError(
                    "JSON number exceeds the supported numeric representation",
                    code=ErrorCode.INPUT_VALUE_INVALID,
                ) from None
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise InputValidationError(
                "Non-finite floating-point value is not permitted in JSON data",
                code=ErrorCode.JSON_NONFINITE_NUMBER,
            )
        if remaining is not None:
            spend(len(json.dumps(value)))
        return value

    if _current_depth >= max_depth:
        raise ResourceLimitError(
            f"JSON value nesting exceeds maximum depth of {max_depth}",
            code=ErrorCode.NESTING_DEPTH_EXCEEDED,
        )

    seen = set() if _seen is None else _seen
    obj_id = id(value)
    if obj_id in seen:
        raise InputValidationError(
            "Cyclic reference detected in JSON value",
            code=ErrorCode.INPUT_VALUE_INVALID,
        )

    if isinstance(value, Mapping):
        if type(value) not in (dict, MappingProxyType):
            raise InputValidationError(
                "Unsupported mapping subtype in JSON value",
                code=ErrorCode.INPUT_VALUE_INVALID,
            )
        seen.add(obj_id)
        try:
            spend(2 + max(0, len(value) - 1) + len(value))
            frozen_dict: dict[str, Any] = {}
            for k, v in value.items():
                if type(k) is not str:
                    raise InputValidationError(
                        "JSON object keys must be strings",
                        code=ErrorCode.INPUT_VALUE_INVALID,
                    )
                freeze_json_value(k, max_depth=max_depth, _remaining_bytes=remaining)
                frozen_dict[k] = freeze_json_value(
                    v,
                    max_depth=max_depth,
                    _current_depth=_current_depth + 1,
                    _seen=seen,
                    _remaining_bytes=remaining,
                )
            return MappingProxyType(frozen_dict)
        finally:
            seen.remove(obj_id)

    if isinstance(value, (list, tuple)):
        if type(value) not in (list, tuple):
            raise InputValidationError(
                "Unsupported sequence subtype in JSON value",
                code=ErrorCode.INPUT_VALUE_INVALID,
            )
        seen.add(obj_id)
        try:
            spend(2 + max(0, len(value) - 1))
            return tuple(
                freeze_json_value(
                    item,
                    max_depth=max_depth,
                    _current_depth=_current_depth + 1,
                    _seen=seen,
                    _remaining_bytes=remaining,
                )
                for item in value
            )
        finally:
            seen.remove(obj_id)

    raise InputValidationError(
        "Unsupported non-JSON Python type in value",
        code=ErrorCode.INPUT_VALUE_INVALID,
    )


def thaw_json_value(value: Any) -> Any:
    """Return a fresh mutable deep copy (standard ``dict`` and ``list``) of a frozen JSON value."""
    if value is None or isinstance(value, (bool, str, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(k): thaw_json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [thaw_json_value(item) for item in value]
    raise TypeError(f"Cannot thaw non-JSON type: {type(value).__name__}")


def serialize_compact_json(
    value: Any,
    *,
    max_depth: int = SPEC_MAX_NESTING_DEPTH,
) -> str:
    """Serialize a validated JSON value using compact, sorted-key UTF-8 JSON."""
    frozen = freeze_json_value(value, max_depth=max_depth)
    thawed = thaw_json_value(frozen)
    try:
        return json.dumps(
            thawed,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except ValueError:
        raise InputValidationError(
            "JSON number exceeds the supported numeric representation",
            code=ErrorCode.INPUT_VALUE_INVALID,
        ) from None


@dataclass(frozen=True, slots=True, order=True)
class ContractRef:
    """Validated immutable reference to an exact contract name and semantic version."""

    name: str
    version: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not (1 <= len(self.name) <= 128):
            raise ManifestError(
                "Contract name must be a non-empty string of at most 128 characters",
                code=ErrorCode.INVALID_CONTRACT_REF,
            )
        if not CONTRACT_NAME_RE.fullmatch(self.name):
            raise ManifestError(
                "Contract name must contain only lowercase ASCII letters, digits, dots, "
                "and hyphens with no empty segments or leading/trailing punctuation",
                code=ErrorCode.INVALID_CONTRACT_REF,
            )
        if not isinstance(self.version, str) or not (5 <= len(self.version) <= 64):
            raise ManifestError(
                "Contract version must be an exact MAJOR.MINOR.PATCH string",
                code=ErrorCode.INVALID_CONTRACT_REF,
            )
        if not CONTRACT_VERSION_RE.fullmatch(self.version):
            raise ManifestError(
                "Contract version must match MAJOR.MINOR.PATCH with no leading zeroes or suffixes",
                code=ErrorCode.INVALID_CONTRACT_REF,
            )

    @classmethod
    def parse(cls, ref_str: str) -> ContractRef:
        """Parse ``<name>@<version>`` into a validated :class:`ContractRef`."""
        if not isinstance(ref_str, str) or "@" not in ref_str:
            raise ManifestError(
                "Contract reference must have the form '<name>@<version>'",
                code=ErrorCode.INVALID_CONTRACT_REF,
            )
        parts = ref_str.split("@")
        if len(parts) != 2:
            raise ManifestError(
                "Contract reference must contain exactly one '@' separator",
                code=ErrorCode.INVALID_CONTRACT_REF,
            )
        return cls(name=parts[0], version=parts[1])

    def __str__(self) -> str:
        return f"{self.name}@{self.version}"


@dataclass(frozen=True, slots=True)
class RuntimePolicy:
    """Immutable host resource limits for contract loading, rendering, and validation.

    Callers may tighten any ceiling relative to the specification defaults; attempting
    to set a non-positive ceiling or relax a ceiling beyond the specification default
    raises :class:`ResourceLimitError`.
    """

    max_manifest_bytes: int = SPEC_MAX_MANIFEST_BYTES
    max_schema_bytes: int = SPEC_MAX_SCHEMA_BYTES
    max_template_bytes: int = SPEC_MAX_TEMPLATE_BYTES
    max_bundle_bytes: int = SPEC_MAX_BUNDLE_BYTES
    max_bundle_files: int = SPEC_MAX_BUNDLE_FILES
    max_messages: int = SPEC_MAX_MESSAGES
    max_nesting_depth: int = SPEC_MAX_NESTING_DEPTH
    max_expanded_schema_nodes: int = SPEC_MAX_EXPANDED_SCHEMA_NODES
    max_input_bytes: int = SPEC_MAX_INPUT_BYTES
    max_rendered_bytes: int = SPEC_MAX_RENDERED_BYTES
    max_response_bytes: int = SPEC_MAX_RESPONSE_BYTES
    max_reported_issues: int = SPEC_MAX_REPORTED_ISSUES

    def __post_init__(self) -> None:
        ceilings = (
            ("max_manifest_bytes", self.max_manifest_bytes, SPEC_MAX_MANIFEST_BYTES),
            ("max_schema_bytes", self.max_schema_bytes, SPEC_MAX_SCHEMA_BYTES),
            ("max_template_bytes", self.max_template_bytes, SPEC_MAX_TEMPLATE_BYTES),
            ("max_bundle_bytes", self.max_bundle_bytes, SPEC_MAX_BUNDLE_BYTES),
            ("max_bundle_files", self.max_bundle_files, SPEC_MAX_BUNDLE_FILES),
            ("max_messages", self.max_messages, SPEC_MAX_MESSAGES),
            ("max_nesting_depth", self.max_nesting_depth, SPEC_MAX_NESTING_DEPTH),
            (
                "max_expanded_schema_nodes",
                self.max_expanded_schema_nodes,
                SPEC_MAX_EXPANDED_SCHEMA_NODES,
            ),
            ("max_input_bytes", self.max_input_bytes, SPEC_MAX_INPUT_BYTES),
            ("max_rendered_bytes", self.max_rendered_bytes, SPEC_MAX_RENDERED_BYTES),
            ("max_response_bytes", self.max_response_bytes, SPEC_MAX_RESPONSE_BYTES),
            ("max_reported_issues", self.max_reported_issues, SPEC_MAX_REPORTED_ISSUES),
        )
        for field_name, val, ceiling in ceilings:
            if type(val) is not int or val <= 0:
                raise ResourceLimitError(
                    f"RuntimePolicy.{field_name} must be a positive integer",
                    code=ErrorCode.POLICY_LIMIT_INVALID,
                )
            if val > ceiling:
                raise ResourceLimitError(
                    f"RuntimePolicy.{field_name} ({val}) cannot "
                    f"exceed specification ceiling ({ceiling})",
                    code=ErrorCode.POLICY_LIMIT_INVALID,
                )

    @property
    def policy_id(self) -> str:
        """Deterministic identifier for the effective runtime policy."""
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(b"prompt-contracts.policy.v1\n" + payload).hexdigest()[:16]
        return f"pc-policy-v1:{digest}"

    def to_dict(self) -> dict[str, int]:
        """Return policy limits as a dictionary."""
        return {
            "max_bundle_bytes": self.max_bundle_bytes,
            "max_bundle_files": self.max_bundle_files,
            "max_expanded_schema_nodes": self.max_expanded_schema_nodes,
            "max_input_bytes": self.max_input_bytes,
            "max_manifest_bytes": self.max_manifest_bytes,
            "max_messages": self.max_messages,
            "max_nesting_depth": self.max_nesting_depth,
            "max_rendered_bytes": self.max_rendered_bytes,
            "max_reported_issues": self.max_reported_issues,
            "max_response_bytes": self.max_response_bytes,
            "max_schema_bytes": self.max_schema_bytes,
            "max_template_bytes": self.max_template_bytes,
        }


DEFAULT_RUNTIME_POLICY = RuntimePolicy()


@dataclass(frozen=True, slots=True)
class TemplateToken:
    """Single compiled token from a ``placeholders-v1`` template."""

    kind: TokenKind
    value: str
    line: int
    column: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TokenKind):
            object.__setattr__(self, "kind", TokenKind(self.kind))
        if type(self.value) is not str:
            raise TypeError("TemplateToken.value must be a str")
        if self.kind == TokenKind.VARIABLE and not IDENTIFIER_RE.fullmatch(self.value):
            raise ValueError(f"Invalid variable identifier: {self.value!r}")


@dataclass(frozen=True, slots=True)
class MessageTemplate:
    """Compiled immutable message template."""

    role: MessageRole
    file: str
    raw_text: str
    tokens: tuple[TemplateToken, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.role, MessageRole):
            object.__setattr__(self, "role", MessageRole(self.role))
        object.__setattr__(self, "tokens", tuple(self.tokens))

    @property
    def referenced_variables(self) -> tuple[str, ...]:
        """Ordered unique variable names referenced by this template."""
        seen: dict[str, None] = {}
        for tok in self.tokens:
            if tok.kind == TokenKind.VARIABLE:
                seen[tok.value] = None
        return tuple(seen.keys())


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """Output validation specification for a contract."""

    mode: OutputMode
    schema_file: str | None = None
    schema: Mapping[str, Any] | None = None
    min_length: int | None = None
    max_length: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.mode, OutputMode):
            object.__setattr__(self, "mode", OutputMode(self.mode))
        if self.mode == OutputMode.JSON:
            if not self.schema_file or self.schema is None:
                raise ManifestError(
                    "JSON output mode requires a schema file and validated schema object",
                    code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                )
            if self.min_length is not None or self.max_length is not None:
                raise ManifestError(
                    "JSON output mode cannot specify text min_length or max_length",
                    code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                )
            object.__setattr__(self, "schema", freeze_json_value(self.schema))
        elif self.mode == OutputMode.TEXT:
            if self.schema_file is not None or self.schema is not None:
                raise ManifestError(
                    "Text output mode cannot specify a JSON schema",
                    code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                )
            if (
                type(self.min_length) is not int
                or type(self.max_length) is not int
                or self.min_length < 0
                or self.max_length < 1
                or self.min_length > self.max_length
            ):
                raise ManifestError(
                    "Text output mode requires valid integer "
                    "min_length (>= 0) <= max_length (>= 1)",
                    code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                )


@dataclass(frozen=True, slots=True)
class RenderedMessage:
    """Single rendered chat message ready for transport."""

    role: MessageRole
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, MessageRole):
            object.__setattr__(self, "role", MessageRole(self.role))
        if type(self.content) is not str:
            raise TypeError("RenderedMessage.content must be a string")

    def to_dict(self) -> dict[str, str]:
        """Return fresh ``{'role': ..., 'content': ...}`` dictionary."""
        return {"role": str(self.role), "content": self.content}


@dataclass(frozen=True, slots=True)
class RenderedPrompt:
    """Immutable ordered messages and identity produced by rendering a contract."""

    contract_ref: ContractRef
    bundle_digest: str
    renderer: str
    policy_id: str
    messages: tuple[RenderedMessage, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        if not self.messages:
            raise ValueError("RenderedPrompt requires at least one message")

    @property
    def total_utf8_bytes(self) -> int:
        """Total UTF-8 byte length across all rendered message contents."""
        return sum(len(m.content.encode("utf-8")) for m in self.messages)

    def to_messages_list(self) -> list[dict[str, str]]:
        """Return a fresh list of ``{'role': ..., 'content': ...}`` dicts for SDK calls."""
        return [m.to_dict() for m in self.messages]


@dataclass(frozen=True, slots=True)
class ExecutionMetadata:
    """Safe, opt-in execution and evaluation metadata record.

    Excludes raw inputs, rendered prompts, model outputs, credentials, and raw input
    hashes by construction.
    """

    contract_name: str
    contract_version: str
    bundle_digest: str
    policy_id: str
    library_version: str
    digest_algorithm: str = "pc-bundle-v1"
    renderer: str = "placeholders-v1"
    model_alias: str | None = None
    served_model: str | None = None
    request_id: str | None = None
    correlation_id: str | None = None
    dataset_revision: str | None = None
    input_valid: bool = True
    output_valid: bool | None = None
    render_duration_ms: float | None = None
    validation_duration_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    generation_options: Mapping[str, JSONPrimitive] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        # Validate contract identity
        _ = ContractRef(self.contract_name, self.contract_version)
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", self.bundle_digest):
            raise ManifestError(
                "ExecutionMetadata.bundle_digest must be a valid sha256:<64-hex> digest",
                code=ErrorCode.LOCK_INVALID,
            )
        if not isinstance(self.generation_options, Mapping):
            raise InputValidationError(
                "ExecutionMetadata.generation_options must be a mapping of primitive options",
                code=ErrorCode.INPUT_VALUE_INVALID,
            )
        clean_opts: dict[str, JSONPrimitive] = {}
        for k, v in self.generation_options.items():
            if type(k) is not str or not k:
                raise InputValidationError(
                    "ExecutionMetadata option keys must be non-empty strings",
                    code=ErrorCode.INPUT_VALUE_INVALID,
                )
            lowered = k.lower()
            allowed_token_keys = {"max_tokens", "max_completion_tokens", "max_output_tokens"}
            if lowered not in allowed_token_keys and (
                lowered in _FORBIDDEN_METADATA_OPTION_KEYS
                or any(
                    bad in lowered
                    for bad in (
                        "secret",
                        "token",
                        "password",
                        "api_key",
                        "prompt",
                        "input",
                        "output",
                        "message",
                    )
                )
            ):
                raise InputValidationError(
                    "Forbidden sensitive or raw-content key "
                    "in ExecutionMetadata.generation_options",
                    code=ErrorCode.INPUT_VALUE_INVALID,
                )
            if v is not None and not isinstance(v, (str, int, float, bool)):
                raise InputValidationError(
                    "ExecutionMetadata.generation_options values must be JSON primitives",
                    code=ErrorCode.INPUT_VALUE_INVALID,
                )
            if isinstance(v, float) and not math.isfinite(v):
                raise InputValidationError(
                    "Non-finite float in ExecutionMetadata.generation_options",
                    code=ErrorCode.JSON_NONFINITE_NUMBER,
                )
            if isinstance(v, str) and len(v) > 128:
                raise InputValidationError(
                    "ExecutionMetadata option string exceeds maximum safe length of 128",
                    code=ErrorCode.INPUT_VALUE_INVALID,
                )
            clean_opts[k] = v
        object.__setattr__(self, "generation_options", MappingProxyType(clean_opts))

    @property
    def contract_ref(self) -> str:
        return f"{self.contract_name}@{self.contract_version}"

    def to_dict(self) -> dict[str, Any]:
        """Return a deterministic JSON-serializable metadata dictionary."""
        result: dict[str, Any] = {
            "bundle_digest": self.bundle_digest,
            "contract_name": self.contract_name,
            "contract_ref": self.contract_ref,
            "contract_version": self.contract_version,
            "digest_algorithm": self.digest_algorithm,
            "generation_options": dict(self.generation_options),
            "input_valid": self.input_valid,
            "library_version": self.library_version,
            "policy_id": self.policy_id,
            "renderer": self.renderer,
        }
        optional_fields = (
            ("completion_tokens", self.completion_tokens),
            ("correlation_id", self.correlation_id),
            ("dataset_revision", self.dataset_revision),
            ("model_alias", self.model_alias),
            ("output_valid", self.output_valid),
            ("prompt_tokens", self.prompt_tokens),
            ("render_duration_ms", self.render_duration_ms),
            ("request_id", self.request_id),
            ("served_model", self.served_model),
            ("total_tokens", self.total_tokens),
            ("validation_duration_ms", self.validation_duration_ms),
        )
        for key, value in optional_fields:
            if value is not None:
                result[key] = value
        return result
