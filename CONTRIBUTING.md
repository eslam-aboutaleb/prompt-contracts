# Contributing to prompt-contracts

Thank you for contributing to `prompt-contracts`.

## Local Setup

1. Install Python `3.12+`, `uv`, and Node `22+` (for Promptfoo offline evaluation checks).
2. Sync the locked Python environment and pinned Promptfoo CLI:
   ```bash
   make ci-install
   npm --prefix tools/promptfoo ci --no-audit --no-fund
   ```

## Quality Gates

Before opening a pull request, run all local verification targets:

```bash
make ci-quality
make ci-generated
make ci-package
make ci-promptfoo
make ci-docs
make benchmark
```

## Architectural Rules

- **Import Boundaries**: Core modules under `src/prompt_contracts/` must never import `prompt_contracts.adapters`, `prompt_contracts.cli`, `llm_gateway_sdk`, or `promptfoo`. Run `uv run --frozen python scripts/check_import_boundaries.py --src src` to verify.
- **Data Privacy**: Never include rejected runtime values, unknown property names, or raw model outputs in exception messages, `repr()`, or logs.
- **Contract Immutability**: Never mutate a published `(name, version)` contract bundle in place; create a new semantic version directory and update `contracts.lock.json`.
