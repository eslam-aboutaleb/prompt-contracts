# ADR-0005: Conservative Directional Compatibility Analyzer

## Status
Accepted

## Context
Symmetric schema diffs treat input and output changes identically, even though relaxing an input schema is backward-compatible for callers while relaxing an output schema breaks downstream consumers.

## Decision
Evaluate compatibility directionally (`I_old <= I_new` for inputs, `O_new <= O_old` for outputs) using a three-valued status (`compatible`, `breaking`, `unknown`) plus an orthogonal `behavioral_review_required` flag whenever message templates, roles, or placeholders change.

## Consequences
CI gates (`prompt-contracts diff`) accurately block breaking or unprovable schema changes while surfacing template wording changes for human/evaluation review.
