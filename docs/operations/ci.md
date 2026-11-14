# CI & Verification Operations

| Target | Purpose |
|---|---|
| `make ci-install` | Sync locked Python development dependencies. Node dependencies are installed only by the evaluation target. |
| `make ci-quality` | Ruff, formatting, strict mypy, import boundaries, and the offline Python suite with at least 90% combined statement/branch coverage. |
| `make ci-generated` | Validate reference editor schemas against bundled manifests/locks, lint example contracts, and verify example/synthetic fixture locks. |
| `make ci-package` | Build wheel/sdist, check metadata, actually install each in a fresh environment, install a separate consumer wheel, and exercise installed resources/CLI outside checkout. The gateway extra is checked with the pinned SDK Git revision. |
| `make ci-promptfoo` | Run `npm ci` for the exact pinned runner, then real CLI tests proving message/schema parity and failed input/output cases with caching disabled. Requires Node 22. |
| `make ci-docs` | Build the documentation with MkDocs strict mode. |
| `make benchmark` | Record environment, 1,000 warm iterations, cold-load samples and peak heap. Shared-runner latency is informational. |

Ordinary pytest runs exclude `live` and `promptfoo` markers. Select the real CLI integration explicitly with `pytest -m promptfoo tests/adapters/test_promptfoo_cli.py` after installing its Node tooling. The dedicated CI job is mandatory; it is not an optional skip in the repository gate.

The workflow covers pull requests, merge groups, main pushes and manual runs. Shared Python checks cover Python 3.11–3.14 on Linux; the repository portability job covers Python 3.12 on Windows/macOS. Every required job appears in the configured `Repository gate`, which accepts only `success`. The test suite executes that gate's actual Python code with failure, cancellation and skipped-job fixtures.

`verify_repository_contracts.py --baseline-ref <trusted-ref>` reads every existing `contracts.lock.json` from the trusted Git baseline and rejects removed catalogs, missing identities and changed digests. CI also verifies the candidate files against their locks, so regenerating a lock does not conceal mutation. A GitHub initial-push all-zero baseline has no previous catalog; unresolved nonzero refs fail.

Dependency support jobs use separate environments, leave `uv.lock` unchanged, check dependency consistency and run the offline suite. The floor is `jsonschema==4.23.0`, `referencing==0.35.0`, and the pinned SDK `0.1.0` Git revision. The latest job resolves core dependencies within their declared bounds and SDK `main`; a version outside the package constraints fails the dependency check. Scheduled maintenance also runs `uv audit --locked` and retains its benchmark report.

Hosted execution, actual emitted check names, branch/ruleset protection and the controlled failing-check drill on GitHub remain operator acceptance work. Local actionlint and gate tests establish repository behavior, not that GitHub protection is configured.
