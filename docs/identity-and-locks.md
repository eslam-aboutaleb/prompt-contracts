# Identity & Lockfiles (`pc-bundle-v1`)

## Byte-Based Bundle Digest

Contract identity is computed over the exact raw UTF-8 bytes of all referenced files in the bundle using `pc-bundle-v1`:

1. Normalize relative POSIX paths (`contract.toml`, `input.schema.json`, templates, etc.) and sort lexicographically by UTF-8 code points.
2. Construct a list of records `[{"path": rel_path, "sha256": file_sha256_hex, "size": byte_len}, ...]`.
3. Serialize records as compact JSON (`separators=(",", ":")`) and prefix with `b"prompt-contracts.bundle.v1\n"`.
4. Compute `sha256:<64-lowercase-hex>`.

Any byte modification—including whitespace, key ordering, or comments—changes the `bundle_digest`.

## Lockfiles (`contracts.lock.json`)

Production registries load contracts with lock verification via `PromptRegistry.from_directory(root, lock_file=...)` or `PromptRegistry.from_package_resources(package, lock_resource=...)`:

```bash
# Generate lockfile initially
uv run prompt-contracts lock examples/contracts --output examples/contracts.lock.json

# Verify contracts against lockfile in CI
uv run prompt-contracts verify examples/contracts --lock examples/contracts.lock.json
```

### Lock Verification Guarantees

- Every locked entry must exist on disk and match its `bundle_digest`.
- Every bundle directory on disk must appear in the lockfile (no unlocked bundles).
- `prompt-contracts lock` writes atomically via a temporary sibling file and `os.replace`, and refuses to overwrite an existing lockfile with differing digests unless `--update` is passed.
