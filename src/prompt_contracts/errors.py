"""Domain-specific error hierarchy with stable codes and sanitized diagnostics.

All errors raised by ``prompt_contracts`` suppress raw exception chaining and exclude
rejected input/output values, credentials, and raw provider bodies from ``str()``,
``repr()``, and serialized dictionary/JSON representations.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

__all__ = [
    "ContractIdentityConflict",
    "ErrorCode",
    "IncompleteCompletionError",
    "InputValidationError",
    "LockMismatchError",
    "ManifestError",
    "OutputValidationError",
    "PathPolicyError",
    "PromptContractError",
    "ProviderCapabilityError",
    "ResourceLimitError",
    "TemplateSyntaxError",
    "UnsupportedFormatError",
    "UnsupportedSchemaError",
    "ValidationIssue",
]


class ErrorCode:
    """Stable machine-readable error codes for CLI, telemetry, and test assertions."""

    # Manifest & Format
    MANIFEST_INVALID_TOML = "PC_MANIFEST_INVALID_TOML"
    MANIFEST_SCHEMA_INVALID = "PC_MANIFEST_SCHEMA_INVALID"
    MANIFEST_UNKNOWN_FIELD = "PC_MANIFEST_UNKNOWN_FIELD"
    UNSUPPORTED_FORMAT_VERSION = "PC_UNSUPPORTED_FORMAT_VERSION"
    UNSUPPORTED_RENDERER = "PC_UNSUPPORTED_RENDERER"
    INVALID_CONTRACT_REF = "PC_INVALID_CONTRACT_REF"

    # Path & Bundle Closure
    PATH_TRAVERSAL_OR_UNSAFE = "PC_PATH_TRAVERSAL_OR_UNSAFE"
    PATH_SYMLINK_REJECTED = "PC_PATH_SYMLINK_REJECTED"
    PATH_CASE_COLLISION = "PC_PATH_CASE_COLLISION"
    ASSET_NOT_FOUND = "PC_ASSET_NOT_FOUND"
    UNREFERENCED_BUNDLE_ASSET = "PC_UNREFERENCED_BUNDLE_ASSET"

    # Resource Limits
    RESOURCE_SIZE_EXCEEDED = "PC_RESOURCE_SIZE_EXCEEDED"
    RESOURCE_COUNT_EXCEEDED = "PC_RESOURCE_COUNT_EXCEEDED"
    NESTING_DEPTH_EXCEEDED = "PC_NESTING_DEPTH_EXCEEDED"
    SCHEMA_EXPANSION_EXCEEDED = "PC_SCHEMA_EXPANSION_EXCEEDED"
    POLICY_LIMIT_INVALID = "PC_POLICY_LIMIT_INVALID"

    # JSON & Schema Profile
    JSON_SYNTAX_INVALID = "PC_JSON_SYNTAX_INVALID"
    JSON_DUPLICATE_KEY = "PC_JSON_DUPLICATE_KEY"
    JSON_NONFINITE_NUMBER = "PC_JSON_NONFINITE_NUMBER"
    SCHEMA_KEYWORD_UNSUPPORTED = "PC_SCHEMA_KEYWORD_UNSUPPORTED"
    SCHEMA_REF_EXTERNAL_OR_INVALID = "PC_SCHEMA_REF_EXTERNAL_OR_INVALID"
    SCHEMA_REF_CYCLE = "PC_SCHEMA_REF_CYCLE"
    SCHEMA_STRUCTURE_INVALID = "PC_SCHEMA_STRUCTURE_INVALID"

    # Template & Rendering
    TEMPLATE_SYNTAX_INVALID = "PC_TEMPLATE_SYNTAX_INVALID"
    TEMPLATE_UNDECLARED_VARIABLE = "PC_TEMPLATE_UNDECLARED_VARIABLE"
    TEMPLATE_OPTIONAL_VARIABLE = "PC_TEMPLATE_OPTIONAL_VARIABLE"

    # Input & Output Validation
    INPUT_NOT_OBJECT = "PC_INPUT_NOT_OBJECT"
    INPUT_VALUE_INVALID = "PC_INPUT_VALUE_INVALID"
    INPUT_SCHEMA_VIOLATION = "PC_INPUT_SCHEMA_VIOLATION"
    OUTPUT_FENCE_OR_PROSE_REJECTED = "PC_OUTPUT_FENCE_OR_PROSE_REJECTED"
    OUTPUT_SCHEMA_VIOLATION = "PC_OUTPUT_SCHEMA_VIOLATION"
    OUTPUT_TEXT_LENGTH_VIOLATION = "PC_OUTPUT_TEXT_LENGTH_VIOLATION"

    # Identity, Registry & Locks
    IDENTITY_CONFLICT = "PC_IDENTITY_CONFLICT"
    REGISTRY_FROZEN = "PC_REGISTRY_FROZEN"
    CONTRACT_NOT_FOUND = "PC_CONTRACT_NOT_FOUND"
    LOCK_INVALID = "PC_LOCK_INVALID"
    LOCK_DIGEST_MISMATCH = "PC_LOCK_DIGEST_MISMATCH"
    LOCK_ENTRY_MISSING = "PC_LOCK_ENTRY_MISSING"
    LOCK_OVERWRITE_REFUSED = "PC_LOCK_OVERWRITE_REFUSED"

    # Gateway & Evaluation Adapters
    COMPLETION_CHOICE_COUNT = "PC_COMPLETION_CHOICE_COUNT"
    COMPLETION_TRUNCATED = "PC_COMPLETION_TRUNCATED"
    COMPLETION_REFUSED_OR_FILTERED = "PC_COMPLETION_REFUSED_OR_FILTERED"
    COMPLETION_UNEXPECTED_TOOL_CALL = "PC_COMPLETION_UNEXPECTED_TOOL_CALL"
    COMPLETION_EMPTY_CONTENT = "PC_COMPLETION_EMPTY_CONTENT"
    CAPABILITY_UNSUPPORTED = "PC_CAPABILITY_UNSUPPORTED"
    ADAPTER_CONTRACT_MISMATCH = "PC_ADAPTER_CONTRACT_MISMATCH"


def _sanitize_pointer(pointer: str, *, max_len: int = 256) -> str:
    """Ensure schema/data pointers are bounded and contain no control characters."""
    cleaned = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in str(pointer or "$"))
    if len(cleaned) > max_len:
        return cleaned[: max_len - 3] + "..."
    return cleaned or "$"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """Sanitized validation diagnostic excluding rejected runtime values."""

    code: str
    message: str
    data_path: str = "$"
    schema_path: str = "$"

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", str(self.code))
        object.__setattr__(self, "message", str(self.message))
        object.__setattr__(self, "data_path", _sanitize_pointer(self.data_path))
        object.__setattr__(self, "schema_path", _sanitize_pointer(self.schema_path))

    def to_dict(self) -> dict[str, str]:
        """Return a deterministic JSON-compatible dictionary."""
        return {
            "code": self.code,
            "data_path": self.data_path,
            "message": self.message,
            "schema_path": self.schema_path,
        }


class PromptContractError(Exception):
    """Base class for all prompt-contracts errors.

    Subclasses set ``default_code`` and ``exit_code``. Instances always suppress raw
    exception context so rejected inputs, model outputs, or secrets cannot leak via
    chained tracebacks or ``repr()``.
    """

    default_code: str = "PC_INTERNAL_ERROR"
    exit_code: int = 3

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        contract_ref: str | None = None,
        source_path: str | None = None,
        line: int | None = None,
        column: int | None = None,
        issues: Sequence[ValidationIssue] = (),
        truncated_issue_count: int = 0,
    ) -> None:
        self.code: str = code or self.default_code
        self.safe_message: str = str(message)
        self.contract_ref: str | None = str(contract_ref) if contract_ref else None
        self.source_path: str | None = (
            _sanitize_pointer(source_path, max_len=256) if source_path else None
        )
        self.line: int | None = int(line) if line is not None else None
        self.column: int | None = int(column) if column is not None else None
        self.issues: tuple[ValidationIssue, ...] = tuple(issues)
        self.truncated_issue_count: int = max(0, int(truncated_issue_count))
        super().__init__(self._format_display())
        self.__cause__ = None
        self.__context__ = None
        self.__suppress_context__ = True

    def _format_display(self) -> str:
        parts = [f"[{self.code}] {self.safe_message}"]
        if self.contract_ref:
            parts.append(f"contract={self.contract_ref}")
        if self.source_path:
            loc = self.source_path
            if self.line is not None:
                loc = f"{loc}:{self.line}"
                if self.column is not None:
                    loc = f"{loc}:{self.column}"
            parts.append(f"source={loc}")
        if self.issues:
            parts.append(f"issues={len(self.issues)}")
        if self.truncated_issue_count > 0:
            parts.append(f"truncated_issues={self.truncated_issue_count}")
        return " (".join([parts[0], ", ".join(parts[1:]) + ")"]) if len(parts) > 1 else parts[0]

    def __str__(self) -> str:
        return self._format_display()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(code={self.code!r}, "
            f"message={self.safe_message!r}, "
            f"contract_ref={self.contract_ref!r}, "
            f"source_path={self.source_path!r}, "
            f"line={self.line!r}, "
            f"column={self.column!r}, "
            f"issue_count={len(self.issues)})"
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize error diagnostics without exposing rejected runtime data."""
        payload: dict[str, Any] = {
            "error_type": self.__class__.__name__,
            "code": self.code,
            "message": self.safe_message,
        }
        if self.contract_ref is not None:
            payload["contract_ref"] = self.contract_ref
        if self.source_path is not None:
            payload["source_path"] = self.source_path
        if self.line is not None:
            payload["line"] = self.line
        if self.column is not None:
            payload["column"] = self.column
        if self.issues:
            payload["issues"] = [issue.to_dict() for issue in self.issues]
        if self.truncated_issue_count > 0:
            payload["truncated_issue_count"] = self.truncated_issue_count
        return payload

    def to_json(self) -> str:
        """Return compact deterministic JSON error representation."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


class ManifestError(PromptContractError):
    """Raised when ``contract.toml`` is malformed or violates manifest rules."""

    default_code = ErrorCode.MANIFEST_SCHEMA_INVALID
    exit_code = 3


class UnsupportedFormatError(PromptContractError):
    """Raised when ``format_version``, ``lock_format``, or ``renderer`` is unsupported."""

    default_code = ErrorCode.UNSUPPORTED_FORMAT_VERSION
    exit_code = 3


class UnsupportedSchemaError(PromptContractError):
    """Raised when a schema uses keywords or references outside the supported profile."""

    default_code = ErrorCode.SCHEMA_KEYWORD_UNSUPPORTED
    exit_code = 3


class PathPolicyError(PromptContractError):
    """Raised when a path escapes the root, uses symlinks, or leaves unreferenced files."""

    default_code = ErrorCode.PATH_TRAVERSAL_OR_UNSAFE
    exit_code = 3


class ContractIdentityConflict(PromptContractError):
    """Raised when registering the same contract ref with a different digest or mutating frozen
    state.
    """

    default_code = ErrorCode.IDENTITY_CONFLICT
    exit_code = 4


class LockMismatchError(PromptContractError):
    """Raised when a lockfile is malformed, missing an entry, or mismatches bundle bytes."""

    default_code = ErrorCode.LOCK_DIGEST_MISMATCH
    exit_code = 4


class InputValidationError(PromptContractError):
    """Raised when contract render inputs fail type or schema validation."""

    default_code = ErrorCode.INPUT_SCHEMA_VIOLATION
    exit_code = 3


class TemplateSyntaxError(PromptContractError):
    """Raised when a template contains malformed braces or unsupported placeholder syntax."""

    default_code = ErrorCode.TEMPLATE_SYNTAX_INVALID
    exit_code = 3


class OutputValidationError(PromptContractError):
    """Raised when a model output fails strict JSON parsing, length bounds, or output schema."""

    default_code = ErrorCode.OUTPUT_SCHEMA_VIOLATION
    exit_code = 3


class IncompleteCompletionError(PromptContractError):
    """Raised when a gateway response is truncated, filtered/refused, empty, or invokes tools."""

    default_code = ErrorCode.COMPLETION_EMPTY_CONTENT
    exit_code = 3


class ProviderCapabilityError(PromptContractError):
    """Raised when a contract cannot be represented under the requested gateway capability
    profile.
    """

    default_code = ErrorCode.CAPABILITY_UNSUPPORTED
    exit_code = 3


class ResourceLimitError(PromptContractError):
    """Raised when any manifest, schema, template, bundle, input, or output exceeds policy
    limits.
    """

    default_code = ErrorCode.RESOURCE_SIZE_EXCEEDED
    exit_code = 3
