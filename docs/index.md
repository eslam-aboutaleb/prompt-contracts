# prompt-contracts

`prompt-contracts` is an offline-first Python library for defining, locking, rendering, validating, and diffing explicit, versioned, immutable prompt contracts in LLM applications.

## Core Design Principles

1. **Zero Transport or Framework Lock-In**: The core runtime requires no API keys, network access, database, gateway client, agent framework, or Node installation.
2. **Immutable Snapshot Loading**: Contract bundles (`contract.toml`, message templates, and JSON Schemas) are loaded once into immutable byte snapshots, checked for complete asset closure, and verified against `pc-bundle-v1` SHA-256 lockfiles.
3. **Single-Pass Opaque Rendering (`placeholders-v1`)**: Template variables (`{{variable_name}}`) are substituted in a single non-re-entrant pass. Untrusted user strings containing `{{...}}` or role markers are never re-parsed.
4. **Strict Pre-Request and Post-Response Validation**: Inputs and outputs are validated against a deterministic JSON Schema Draft 2020-12 profile without silent coercion, Markdown fence stripping, or auto-repair.
5. **Privacy by Construction**: Domain exceptions (`PromptContractError` and subclasses) suppress exception chaining and never include rejected input/output values, unknown property names, or secrets in `str()`, `repr()`, or serialized reports.

## Quickstart

```python
from pathlib import Path
from prompt_contracts import ContractRef, PromptRegistry

registry = PromptRegistry.from_directory(
    root=Path("examples"),
    lock_file="contracts.lock.json",
)
registry.freeze()

contract = registry.get(ContractRef("career.application-answer", "1.0.0"))
rendered = contract.render(
    {
        "question": "Describe your database experience.",
        "verified_facts": "fact-1: Maintained PostgreSQL migrations.",
    }
)
validated = contract.validate_output(
    '{"answer":"I maintained PostgreSQL migrations.","evidence_ids":["fact-1"],"needs_review":false}'
)
```

## Documentation Sections

- [Contract Format](contract-format.md)
- [Single-Pass Rendering](rendering.md)
- [Identity & Lockfiles](identity-and-locks.md)
- [Compatibility Analyzer](compatibility.md)
- [Errors & Privacy](errors-and-privacy.md)
- [llm-gateway-sdk Adapter](integrations/gateway-sdk.md)
- [Promptfoo Evaluation Bridge](integrations/promptfoo.md)
