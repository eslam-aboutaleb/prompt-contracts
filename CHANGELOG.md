# Changelog

All notable changes to `prompt-contracts` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-11-14

### Added
- Core immutable contract model (`Contract`, `ContractRef`, `RuntimePolicy`, `RenderedPrompt`, `RenderedMessage`, `ExecutionMetadata`).
- `contract.toml` (`format_version = 1`) parser, root-confined path validator, symlink/traversal guards, and complete bundle asset-closure verification.
- Single-pass `placeholders-v1` template compiler and renderer with `{{{{` / `}}}}` escapes, lone brace passthrough, and required input property binding.
- Bounded JSON Schema Draft 2020-12 profile compiler and validator with local `#/$defs/...` expansion, cycle detection, and strict JSON parser rejecting duplicate keys, non-finite numbers, Markdown fences, and excess nesting depth.
- `pc-bundle-v1` byte-based SHA-256 bundle digest computation, atomic `contracts.lock.json` generation, and `PromptRegistry` supporting directory, unlocked directory, and `importlib.resources` package loading.
- Directional contract compatibility analyzer (`compare_contracts`, `CompatibilityReport`) and `prompt-contracts diff` CLI command.
- `prompt_contracts.adapters.gateway` request/response mapper for `llm-gateway-sdk` (`GatewayCapabilities.strict_json_schema()` and `GatewayCapabilities.local_validation()`).
- `prompt_contracts.adapters.promptfoo` production-renderer evaluation bridge and pinned Promptfoo offline evaluation harness (`tools/promptfoo/`).
- Sanitized domain exception hierarchy (`PromptContractError` and subclasses) guaranteeing zero leakage of rejected input/output values or secrets.
- Synthetic consumer-style fixtures and rollback drills (not evidence of application adoption) for **Ace Your Interview** (`study.topic-language-advisor`) and **Job-Hunting Assistant** (`career.answer-generation`).

### Audit fixes
- Make compatibility proofs conservative for open properties, constants, boolean/number values, and required names outside property declarations.
- Enforce input/rendering/lock/diagnostic resource limits incrementally and translate Unicode/integer parser failures into safe errors.
- Verify complete package-resource catalogs, including ZIP imports; resolve relative registry locks against the configured root. CLI lock arguments remain relative to the working directory.
- Exclude raw rendered input/request data from Promptfoo metadata unless `include_rendered_prompt=True` is explicitly selected for synthetic parity checks.
- Replace tautological digest and process-only parity checks with independent regressions, and correct the editor reference schemas.
- Install actual wheel/sdist/consumer artifacts in clean environments; repair CI gates, dependency checks and release artifact promotion. Hosted/operator and real-consumer acceptance remain outstanding.
