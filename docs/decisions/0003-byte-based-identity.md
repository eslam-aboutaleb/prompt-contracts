# ADR-0003: Byte-Based Bundle Identity (`pc-bundle-v1`)

## Status
Accepted

## Context
Semantic AST-normalized digests can mask formatting changes or differ across parser versions, making it harder to guarantee that an installed package or disk directory contains the exact bytes reviewed in git.

## Decision
Compute `pc-bundle-v1` digests over the exact raw bytes and sizes of all referenced files in a contract bundle, sorted by normalized relative POSIX path, and verify them via `contracts.lock.json`.

## Consequences
Any modification to any referenced file in a bundle deterministically changes its `sha256:<64-hex>` digest and is caught by `prompt-contracts verify`.
