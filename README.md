# prompt-contracts

Explicit, versioned, immutable prompt contracts for Python LLM applications.

`prompt-contracts` turns prompts and their input/output schemas into immutable, lock-verified, testable software artifacts—without coupling your application to an external prompt server, database, provider client, or agent framework.

The [implementation audit](tasks/implementation-review.md) records local verification and the remaining consumer adoption and release acceptance work.

## Key Capabilities

- **Immutable Contract Bundles (`format_version = 1`)**: Self-contained directories with `contract.toml`, ordered message templates (`system`, `user`, `assistant`), `input.schema.json`, and `output.schema.json`.
- **Single-Pass Non-Re-Entrant Rendering (`placeholders-v1`)**: Substitutes required schema-validated variables in one pass (`{{variable}}`), supports literal double braces via `{{{{` and `}}}}`, passes lone `{` / `}` characters verbatim, and never re-evaluates untrusted input data.
- **Byte-Based Identity & Lockfiles (`pc-bundle-v1`)**: Computes deterministic `sha256:<64-hex>` digests over all referenced bundle files and verifies `contracts.lock.json` on load from disk or `importlib.resources`.
- **Strict JSON Schema Draft 2020-12 Validation**: Validates inputs pre-request and outputs post-response without silent coercion, Markdown fence stripping, or duplicate-key ambiguity.
- **Directional Compatibility Analyzer**: Compares contract versions directionally (`I_old <= I_new` for inputs, `O_new <= O_old` for outputs) with `compatible` / `breaking` / `unknown` statuses and `behavioral_review_required`.
- **Privacy by Construction**: Domain exceptions suppress exception chaining and never include rejected values, unknown property names, or secrets in `str()`, `repr()`, or JSON diagnostics.
- **Optional Adapters**:
  - `prompt_contracts.adapters.gateway`: Request/response mapper for `llm-gateway-sdk` (`GatewayClient` and `AsyncGatewayClient`).
  - `prompt_contracts.adapters.promptfoo`: Production-renderer evaluation bridge for Promptfoo custom Python providers.

## Installation

```bash
# From this repository checkout (core has no transport/SDK dependencies)
pip install .

# Until the SDK is available on your package index, install the tested revision
pip install "llm-gateway-sdk @ git+https://github.com/eslam-aboutaleb/llm-gateway-sdk.git@3da8548e528ec6ed404ef2b115f0568db83fa7bd"
pip install ".[gateway]"
```

The examples below run from the repository checkout. Index installation with `pip install prompt-contracts` is a release-time step; see [release readiness](docs/operations/releases.md).

## Quickstart

```python
import json
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
    json.dumps(
        {
            "answer": "I maintained PostgreSQL schema migrations in production.",
            "evidence_ids": ["fact-1"],
            "needs_review": False,
        }
    )
)
```

## CLI Usage

```bash
# Validate manifests, schemas, templates, and asset closure
prompt-contracts lint examples/contracts

# Generate or update contracts.lock.json atomically
prompt-contracts lock examples/contracts --output examples/contracts.lock.json --update

# Verify contract bundles against contracts.lock.json
prompt-contracts verify examples/contracts --lock examples/contracts.lock.json

# Render messages from a JSON input file (or '-' for stdin)
prompt-contracts render examples/contracts \
  --lock examples/contracts.lock.json \
  --ref career.application-answer@1.0.0 \
  --input-file examples/inputs/application-answer.json

# Analyze directional compatibility between two contract versions
prompt-contracts diff \
  tests/fixtures/consumers/ace_your_interview/contracts/study.topic-language-advisor/1.0.0 \
  tests/fixtures/consumers/ace_your_interview/contracts/study.topic-language-advisor/1.1.0
```

## Development & Verification

```bash
make ci-install
make ci-quality
make ci-generated
make ci-package
make ci-promptfoo
make ci-docs
make benchmark
```

## License

MIT License — see [LICENSE](LICENSE).
