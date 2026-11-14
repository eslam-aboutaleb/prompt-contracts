# Rollback Runbook

## Rolling Back a Contract Version in a Consumer Application

Because contract versions live side by side in the locked catalog (`contracts/<name>/<version>/`) and are verified by `contracts.lock.json`, rolling back a prompt change requires **no template edits and no lockfile regeneration**:

1. Keep both the previous known-good version (e.g. `1.0.0`) and the newer version (e.g. `1.1.0`) in `contracts/` and `contracts.lock.json`.
2. Switch the consumer's configured version pin from `1.1.0` back to `1.0.0`.
3. Verify that `ExecutionMetadata.contract_ref` and `ExecutionMetadata.bundle_digest` report the `1.0.0` digest.

## Rolling Back a Library Release

If a `prompt-contracts` package release on PyPI exhibits a regression:

1. Pin consumer repositories to the previous known-good version in `pyproject.toml` / `uv.lock`.
2. Yank the affected version on PyPI (never delete or overwrite a published version).
3. Ship a forward patch release (`X.Y.(Z+1)`) with a regression test.
