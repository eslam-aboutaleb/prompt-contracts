## Summary

- Describe the contract, runtime, adapter, or tooling change.

## Contract & Compatibility Impact

- [ ] No existing published `(name, version)` contract bundles were mutated in place.
- [ ] `uv run --frozen prompt-contracts verify` passes on all locked contract catalogs.
- [ ] If adding a new contract version, `uv run --frozen prompt-contracts diff` was reviewed.

## Verification

- [ ] `make ci-quality`
- [ ] `make ci-generated`
- [ ] `make ci-package`
- [ ] `make ci-promptfoo`
- [ ] `make ci-docs`
