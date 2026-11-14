# ADR-0004: Bounded JSON Schema Draft 2020-12 Profile

## Status
Accepted

## Context
Unrestricted JSON Schema allows arbitrary remote `$ref` retrieval, cyclic references, regex backtracking (`pattern`), and non-deterministic keywords that are either unsafe at runtime or rejected by provider structured-output endpoints.

## Decision
Enforce a deterministic JSON Schema Draft 2020-12 subset (`SUPPORTED_SCHEMA_KEYWORDS`), block remote `$ref` retrieval, allow only acyclic local `#/$defs/<Name>` references within an expanded node ceiling (`max_expanded_schema_nodes = 5000`), and require explicit opt-in for local-only validation when a schema exceeds strict provider capabilities.

## Consequences
Schema compilation and validation are bounded and offline. Provider schema support is checked separately by the gateway adapter; an accepted local schema is not automatically representable by every provider.
