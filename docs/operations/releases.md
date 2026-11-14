# Release & Versioning Policy

## Current readiness

The repository implements local verification and a release workflow. No publication, protected-environment setup, trusted publisher registration or hosted workflow execution was performed by the implementation audit. The checkout had no initial Git commit at review time, so a tag/source rehearsal on this repository still needs a committed revision. Git ancestry and mutation rejection are exercised in temporary test repositories.

On November 14, 2026, the PyPI endpoint for `llm-gateway-sdk/0.1.0` returned 404. The gateway extra is tested by installing the pinned SDK Git revision alongside the candidate distribution. Publish the SDK to the intended index or retain an explicit supported Git installation recipe before claiming the extra can be installed from the index alone.

Real consumer adoption, captured legacy parity, regression suites and artifact rollback evidence are also outstanding. The fixtures in this repository are synthetic demonstrations. See the repository's `tasks/implementation-review.md` for the acceptance audit.

## Local verification and rehearsal

Update the package version in `pyproject.toml`, `prompt_contracts.__version__` and `CHANGELOG.md`, then run:

```bash
make ci-quality
make ci-generated
make ci-package
make ci-promptfoo
make ci-docs
uv run --frozen python scripts/check_release.py --tag v0.2.0 --dist-dir dist --write-checksums
```

Package release versions accept `X.Y.Z` or an `aN`, `bN` or `rcN` prerelease suffix, such as `0.3.0a1`. Contract versions remain exact `MAJOR.MINOR.PATCH` without suffixes.

For an existing tag, manually dispatch `release.yml` with its `tag` input to rehearse. Manual runs validate and build but never enter publishing jobs. The source check requires the checked-out commit to equal that tag and belong to `origin/main`:

```bash
uv run --frozen python scripts/check_release.py --tag v0.2.0 --verify-git
uv run --frozen python scripts/verify_repository_contracts.py --baseline-ref origin/main
```

## Authorized publication

An authorized `v*` tag push triggers source validation, tagged Python/OS tests, security checks, quality/docs/contracts, dependency support and real offline Promptfoo checks. The release job builds the wheel and sdist once, installs those exact distributions, and uploads them with `SHA256SUMS.txt` for 90 days.

The protected `testpypi` job downloads that artifact, checks its hashes and publishes through OIDC. Index verification compares the index's wheel/sdist digests and downloaded bytes with the verified files, then installs the downloaded wheel in a fresh environment. The protected `pypi` job downloads the same original artifact and verifies hashes before publishing; it never rebuilds. A separate job attaches those files and checksums to the GitHub release.

Before authorizing a release, verify package-name ownership, license/provenance, tag protection, the configured `Repository gate` rule, selected CodeQL severity rules, and both `testpypi`/`pypi` environments and trusted publishers. These are external setup requirements; YAML presence is not evidence they are configured.

## Contract immutability

Each released `<name>@<version>` is immutable. Any template, manifest or schema byte change requires a new contract version and lock update. CI compares against a trusted baseline; `verify_published_contracts.py` also supports comparing explicit baseline/candidate lockfiles. Rollback selects an existing package/contract pair; it does not rewrite published bytes.
