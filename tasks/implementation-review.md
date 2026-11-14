# Implementation review — November 14, 2026

## Verdict and scope

The library's runtime, compatibility analyzer, adapters, CLI and local packaging paths are implemented. The audit found and fixed correctness, resource-boundary, privacy, test and workflow gaps. No unfinished runtime TODO/NotImplemented stubs were found. Protocol method ellipses describe interfaces; scripted offline responders are intentional test implementations.

The complete delivery plan is **not accepted yet**. Real consumer migrations and hosted/operator release evidence remain outstanding. Completed synthetic examples cannot satisfy those requirements. The backlog now distinguishes local implementation from that external acceptance work.

Review covered `tasks/plan.md`, `tasks/todo.md`, source modules, tests, examples, reference schemas, packaging scripts, workflows, benchmark and documentation. Consumer checkouts were inspected read-only; neither consumer was modified. No commit, tag, push, publication or external application write was performed.

## Findings fixed

| Priority | Gap | Result and regression evidence |
|---|---|---|
| P1 | Compatibility could certify narrowing an open object's optional property, ignore changed siblings of `const`, conflate booleans/numbers, or miss required names outside properties. | Conservative comparisons and independent accepted-instance witnesses in `tests/compatibility/test_soundness_regressions.py`. Unprovable cases return `unknown`; the CLI test verifies exit 5. |
| P1 | The renderer joined all repeated input expansions before checking its byte limit. Input freezing also copied/serialized oversized data before enforcing the input ceiling. | Rendering checks each token before joining; input snapshots spend a compact-JSON byte budget while traversing. Tests verify early failure and exact UTF-8 budgets. |
| P1 | Invalid Unicode and oversized integer conversion could escape as raw Python exceptions. Immutable containers accepted by the snapshot layer failed subsequent schema validation. | Safe domain errors and validation of a detached JSON snapshot; Unicode, integer and immutable-container regressions cover these paths. |
| P1 | Package registry lock reads were unbounded and extra package bundles were not detected. Relative filesystem lock selection depended on the current directory. | Bounded lock reads, independent catalog discovery including real ZIP imports, extra-bundle rejection, and root-relative lock selection. CLI paths retain command-line working-directory semantics. |
| P1 | Provider finish reasons leaked arbitrary provider text; Promptfoo metadata automatically copied rendered input and request data. | Sanitized finish-reason diagnostics; raw parity data requires explicit opt-in. Ordinary bridge metadata excludes it. |
| P1 | CI called shared workflows with invalid/missing inputs, omitted merge-group coverage and had no final gate. | Correct input contracts, supported Python/OS jobs, explicit dependency checks, and a `Repository gate` requiring success from every mandatory job. Tests execute its actual code for failure, cancellation and unexpected skip. |
| P1 | Release workflow used a token-oriented reusable publisher that rebuilt artifacts; tag ancestry and protected catalog checks were absent. | Repository-owned tagged verification, source ancestry checks, trusted-baseline comparison, build-once artifacts/checksums, TestPyPI byte verification and OIDC promotion of the same original artifacts. Manual dispatch is verification-only. No hosted execution is claimed. |
| P2 | Packaging “installation” unpacked a wheel and synthesized a shell CLI; it never installed the sdist and was not portable to Windows. | Fresh virtual environments actually install wheel/sdist and an independently built consumer wheel. Installed CLI/resources, package version parity, core-only isolation and the gateway extra are exercised. |
| P2 | Digest golden test accepted any result. Real Promptfoo CLI test checked process status without inspecting message/schema parity. | Fixed independent digest vector; actual CLI report messages/request kwargs are compared with direct production rendering. Negative input/output cases must fail. |
| P2 | Editor schemas overescaped semantic-version dots and accepted incomplete/mixed output modes. | Correct patterns, conditional output requirements and reference-schema checks against every bundled manifest/lock. |
| P2 | Validation diagnostics retained every raw error before truncating; stdin was read without a bound. | Bounded-memory error selection with exact omitted counts, and bounded stdin reads with regression tests. |
| P2 | Missing floor/latest dependency checks and locked audits; benchmark thresholds contradicted the plan and fixtures lacked recorded exact sizes. | Isolated floor/latest checks, scheduled locked audit, informational shared-runner latency, exact fixture byte counts and a saved local benchmark report. |
| P2 | Documentation/backlog claimed actual migrations, unsupported roles/schema forms and completed release setup. | Corrected docs, explicitly synthetic fixture provenance, reopened consumer/release tasks, and a working pinned-Git SDK installation recipe. |

## Acceptance mapping

“Local” means tested in this checkout, not demonstrated in a deployed consumer or on all hosted platforms.

| Acceptance IDs | Evidence/status |
|---|---|
| AC-01–AC-04 | Local load/render/output and strict input tests; sync/async SDK spies verify pre-request rejection. |
| AC-05–AC-08 | Renderer properties, syntax corpus, schema-profile/ref/depth tests, offline egress guard. |
| AC-09–AC-11 | Fixed digest golden, identity properties, registry conflicts and lock mutation checks. |
| AC-12 | Local regenerated-lock/deleted-catalog rejection against real temporary Git histories; wired to trusted CI baseline. Hosted branch protection remains unverified. |
| AC-13–AC-15 | Path/resource/ZIP/snapshot/defensive-copy tests. Local macOS checks passed; Windows/Linux execution remains a hosted-CI requirement. |
| AC-16–AC-20 | Text/JSON parsing, strict malformed-data handling, completion-status corpus and explicit gateway capability tests. |
| AC-21 | Error privacy regressions, provider finish-reason redaction, and opt-in Promptfoo parity metadata. |
| AC-22–AC-23 | Real isolated wheel/sdist/consumer installation and SDK sync/async tests, with floor/latest dependency checks. SDK index availability is unresolved. |
| AC-24–AC-26 | Directional rule corpus, independent acceptance witnesses, property tests and CLI breaking/unknown policy checks. |
| AC-27–AC-28 | Required dedicated real Promptfoo CLI parity plus negative input/output report checks, with caching disabled. |
| AC-29 | **Incomplete.** Neither application depends on or delegates to this package. Existing fixtures differ from the actual current flows and are labeled synthetic. See both migration guides. |
| AC-30 | Local actual wheel/sdist/core/extra installation and packaged resources; no published artifact was tested. |
| AC-31 | Local actual-gate failure/skip/cancellation fixtures and actionlint. Hosted failing-check/ruleset drill is outstanding. |
| AC-32 | Local tag/version/prerelease/changelog/source-ancestry tests and artifact checksums; release source rehearsal on this repository is outstanding. |
| AC-33 | PR live responder invocation is blocked; ordinary tests exclude live execution and publication jobs only accept tag pushes. Real CLI uses scripted responses. |
| AC-34 | Runnable examples, reference checks, installed consumer smoke and strict MkDocs build. |
| AC-35 | Actual local cold/warm/heap report in `benchmarks/results/2026-11-14-local.json`, including environment, dependency versions and exact fixture sizes. |

## Verification

Baseline before fixes: 173 tests passed, 91.00% combined statement/branch coverage. This baseline missed the issues above.

Executed during the audit:

- `make ci-quality` — Ruff, formatting, strict mypy, import boundaries, offline tests and coverage.
- `make ci-generated`, `make ci-package`, `make ci-docs` — passed.
- `PATH=/opt/homebrew/opt/node@22/bin:$PATH make ci-promptfoo` — locked npm installation and real CLI parity/input/output rejection test passed.
- `scripts/check_dependency_support.py --mode floor` / `--mode latest` — passed in isolated Python 3.12 environments. Minimum core dependencies and the pinned SDK, and latest supported core dependencies/SDK main, were checked without editing the lock.
- Offline suites also passed on local Python 3.11.17 (floor), 3.13.16 (floor) and 3.14.8 (latest). Python 3.12.12 is the primary quality/package environment. Counts vary because regressions were added during the audit; **the final primary run passed 227 tests, with 1 real-CLI test deliberately deselected for its dedicated job, and 91.86% combined statement/branch coverage.**
- `actionlint .github/workflows/ci.yml .github/workflows/release.yml .github/workflows/maintenance.yml` — passed.
- `uv audit --locked` — no known vulnerabilities or adverse statuses in 77 audited packages at execution time. This does not audit the Node harness.
- `benchmarks/runtime.py --iterations 1000` — saved local report; the cold bundle is 102,400 bytes, the verified catalog 110,053 bytes, and rendered/output fixtures 10,240 bytes each. These are machine-specific measurements.

## Outstanding work

1. Refresh/capture both real consumer flows, author matching application-owned contracts, pin the candidate artifact/dependency/contract locks, delegate production paths, run actual consumer suites, and demonstrate artifact rollback. T01 and T18–T23 are reopened; no fabricated legacy-parity result remains.
2. Commit the repository, run the hosted CI/portability and release rehearsal, and verify the actual gate/ruleset, CodeQL policy, protected tags/environments and trusted publishers. T24/T33/T34 have local implementations but incomplete hosted/operator acceptance.
3. Establish SDK package-index availability or retain the explicit Git installation policy, confirm distribution-name ownership and release provenance, and finish real consumer evidence/runbooks (T32).
4. Publish only under separately authorized release work and verify the index artifacts and downstream adoption (T35). No external release action was attempted here.
