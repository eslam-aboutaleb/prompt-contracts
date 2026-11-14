"""``prompt_contracts`` — Explicit, versioned, immutable prompt contracts for LLM applications.

Core runtime boundary:
- :class:`ContractRef`, :class:`RuntimePolicy`, :class:`Contract`, :class:`RenderedPrompt`
- :class:`PromptRegistry`, :class:`ContractLock`, :class:`LockEntry`
- :class:`CompatibilityReport`, :func:`compare_contracts`
- :class:`ExecutionMetadata`, :class:`ValidationIssue`, and sanitized domain exceptions.
"""

from __future__ import annotations

from prompt_contracts.compatibility import (
    CompatibilityDirection,
    CompatibilityFinding,
    CompatibilityPolicy,
    CompatibilityReport,
    CompatibilityRuleId,
    CompatibilityStatus,
    compare_contracts,
)
from prompt_contracts.contract import Contract
from prompt_contracts.errors import (
    ContractIdentityConflict,
    ErrorCode,
    IncompleteCompletionError,
    InputValidationError,
    LockMismatchError,
    ManifestError,
    OutputValidationError,
    PathPolicyError,
    PromptContractError,
    ProviderCapabilityError,
    ResourceLimitError,
    TemplateSyntaxError,
    UnsupportedFormatError,
    UnsupportedSchemaError,
    ValidationIssue,
)
from prompt_contracts.identity import (
    BUNDLE_DIGEST_ALGORITHM,
    ContractLock,
    LockEntry,
    compute_bundle_digest,
    read_lock_file,
    write_lock_atomic,
)
from prompt_contracts.registry import PromptRegistry
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    ContractRef,
    ExecutionMetadata,
    JSONPrimitive,
    JSONValue,
    MessageRole,
    MessageTemplate,
    OutputMode,
    OutputSpec,
    RenderedMessage,
    RenderedPrompt,
    RuntimePolicy,
    TemplateToken,
    TokenKind,
)

__version__ = "0.2.0"

__all__ = [
    "BUNDLE_DIGEST_ALGORITHM",
    "DEFAULT_RUNTIME_POLICY",
    "CompatibilityDirection",
    "CompatibilityFinding",
    "CompatibilityPolicy",
    "CompatibilityReport",
    "CompatibilityRuleId",
    "CompatibilityStatus",
    "Contract",
    "ContractIdentityConflict",
    "ContractLock",
    "ContractRef",
    "ErrorCode",
    "ExecutionMetadata",
    "IncompleteCompletionError",
    "InputValidationError",
    "JSONPrimitive",
    "JSONValue",
    "LockEntry",
    "LockMismatchError",
    "ManifestError",
    "MessageRole",
    "MessageTemplate",
    "OutputMode",
    "OutputSpec",
    "OutputValidationError",
    "PathPolicyError",
    "PromptContractError",
    "PromptRegistry",
    "ProviderCapabilityError",
    "RenderedMessage",
    "RenderedPrompt",
    "ResourceLimitError",
    "RuntimePolicy",
    "TemplateSyntaxError",
    "TemplateToken",
    "TokenKind",
    "UnsupportedFormatError",
    "UnsupportedSchemaError",
    "ValidationIssue",
    "__version__",
    "compare_contracts",
    "compute_bundle_digest",
    "read_lock_file",
    "write_lock_atomic",
]
