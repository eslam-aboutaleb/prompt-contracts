# Errors, Resource Limits & Privacy

## Domain Exception Hierarchy

All library exceptions inherit from `PromptContractError` and carry a machine-readable `ErrorCode`:

| Exception | Default Code | CLI Exit Code |
|---|---|---|
| `ManifestError` | `PC_MANIFEST_SCHEMA_INVALID` | `3` |
| `UnsupportedFormatError` | `PC_UNSUPPORTED_FORMAT_VERSION` | `3` |
| `UnsupportedSchemaError` | `PC_SCHEMA_KEYWORD_UNSUPPORTED` | `3` |
| `PathPolicyError` | `PC_PATH_TRAVERSAL_OR_UNSAFE` | `3` |
| `TemplateSyntaxError` | `PC_TEMPLATE_SYNTAX_INVALID` | `3` |
| `InputValidationError` | `PC_INPUT_SCHEMA_VIOLATION` | `3` |
| `OutputValidationError` | `PC_OUTPUT_SCHEMA_VIOLATION` | `3` |
| `IncompleteCompletionError` | `PC_COMPLETION_EMPTY_CONTENT` | `3` |
| `ProviderCapabilityError` | `PC_CAPABILITY_UNSUPPORTED` | `3` |
| `ResourceLimitError` | `PC_RESOURCE_SIZE_EXCEEDED` | `3` |
| `ContractIdentityConflict` | `PC_IDENTITY_CONFLICT` | `4` |
| `LockMismatchError` | `PC_LOCK_DIGEST_MISMATCH` | `4` |

## Zero-Leakage Privacy Invariant

- `PromptContractError` sets `__cause__ = None`, `__context__ = None`, and `__suppress_context__ = True`.
- `ValidationIssue` records only `code`, `data_path`, `schema_path`, and a safe structural `message`.
- Rejected input values, unknown property names on closed objects, raw model outputs, and secrets are never included in `str(err)`, `repr(err)`, `err.to_dict()`, `err.to_json()`, or CLI output.
- `ExecutionMetadata` records contract identity (`contract_name`, `contract_version`, `bundle_digest`, `policy_id`), timings, token counts, and safe primitive generation options while rejecting sensitive or raw-content option keys.
