# ADR-0001: Offline Core Runtime Boundary

## Status
Accepted

## Context
Prompt management libraries frequently couple template rendering with provider SDK clients, databases, or evaluation frameworks, forcing every consumer to install heavy transitive dependencies or configure API keys just to render and validate prompts.

## Decision
Keep the core `prompt_contracts` package strictly offline with only two runtime dependencies (`jsonschema` and `referencing`). Keep `llm-gateway-sdk` and Promptfoo bridges in `prompt_contracts.adapters` with zero eager imports in `prompt_contracts.adapters.__init__`.

## Consequences
Core contract loading, lock verification, rendering, output validation, and compatibility diffing work offline with zero network calls or external services.
