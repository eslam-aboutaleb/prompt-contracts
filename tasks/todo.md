# prompt-contracts implementation backlog

Status: local runtime, compatibility, adapter and packaging work is implemented. The November 14, 2026 audit reopened consumer adoption and release-readiness tasks; see [implementation-review.md](implementation-review.md). Synthetic fixtures do not complete real-consumer acceptance. Read [plan.md](plan.md) for normative design and acceptance IDs.

Each checkbox requires the task criteria and the project's definition of done. Commands below describe the intended implemented toolchain; they are not claims that the commands exist or have passed today. Paths are relative to the future library repository except explicitly marked consumer paths. Synthetic fixtures only.

Estimated scope uses S for roughly 1–2 coherent files and M for roughly 3–5. A lockfile generated with a manifest counts as its associated tooling artifact. Split a task further if it grows beyond a focused implementation session. Consumer changes belong in their own repositories and PRs.

## M0 — establish the contracts

### T01 — inventory the first two consumer flows

- [ ] Complete T01.
- **Deliverable:** Select one Ace generation flow and one job-assistant flow after inspecting active callers and schemas. Record the source commit, legacy metadata labels, execution commands, and how to capture message fixtures.
- **Acceptance:** (1) Each selected flow has explicit inputs, output expectations, and callers; (2) callable formatting and unsupported schema features are recorded; (3) existing domain/evaluation guarantees and rollback entry points are listed.
- **Verify:** Reproduce each flow's offline rendering using existing consumer tests or a temporary local fixture capture; record the exact commands and outcomes in the migration guides. No live user data.
- **Dependencies:** None.
- **Files:** `docs/integrations/ace-your-interview.md`, `docs/integrations/job-hunting-assistant.md`, `docs/decisions/0001-runtime-boundary.md`.
- **Scope:** M. **Criteria:** AC-29 preparation; plan sections 2, 12.

### T02 — freeze format and schema-profile decisions

- [x] Complete T02.
- **Deliverable:** Turn plan sections 7–9 into versioned format rules and reference schemas, including renderer escapes, exact-byte identity, and supported schema keywords.
- **Acceptance:** (1) Every example has an unambiguous parse/render interpretation; (2) unsupported constructs and limits are listed; (3) both initial consumer flows can be represented or their required extension is explicitly resolved.
- **Verify:** Walk the selected consumer fixtures through the proposed format; validate reference-schema examples with a small offline check once the bootstrap environment exists.
- **Dependencies:** T01.
- **Files:** `docs/contract-format.md`, `schemas/contract-manifest.schema.json`, `schemas/contract-lock.schema.json`, `docs/decisions/0002-contract-format-and-renderer.md`, `docs/decisions/0004-schema-profile.md`.
- **Scope:** M. **Criteria:** AC-06–AC-08; plan sections 7–9.

### T03 — establish the Python package and baseline checks

- [x] Complete T03.
- **Deliverable:** Minimal installable package, locked development environment, and baseline shared Python/commit checks. Later tasks add jobs as the underlying capabilities become real.
- **Acceptance:** (1) Core imports on Python 3.11–3.14; (2) `uv build` creates wheel/sdist; (3) lint/format/tests run without credentials.
- **Verify:** `uv sync --frozen --all-groups`; `uv run --frozen pytest`; `uv build`; `uv run --frozen ruff check .`.
- **Dependencies:** T02.
- **Files:** `pyproject.toml` + `uv.lock`, `src/prompt_contracts/__init__.py`, `tests/test_import.py`, `.github/workflows/ci.yml`, `Makefile`.
- **Scope:** M. **Criteria:** AC-01 baseline, AC-30 baseline.

### Checkpoint M0

- [ ] Initial flow inventory and design assumptions are reviewable.
- [x] Format/profile decisions are internally consistent and recorded.
- [x] Package builds and baseline offline CI passes.
- [x] No live credentials, external application writes, or library implementation beyond bootstrap were needed for planning.

## M1 — a complete offline runtime path

### T04 — introduce validated value types and error codes

- [x] Complete T04.
- **Deliverable:** Contract refs, messages, runtime policy, JSON value types, and sanitized exception families.
- **Acceptance:** (1) Invalid names/versions are rejected; (2) immutable types do not leak mutable state; (3) exception serialization has stable codes and no data values.
- **Verify:** `uv run --frozen pytest tests/unit/test_types.py tests/unit/test_errors.py`; `uv run --frozen mypy src/prompt_contracts`.
- **Dependencies:** T03.
- **Files:** `src/prompt_contracts/types.py`, `src/prompt_contracts/errors.py`, `src/prompt_contracts/__init__.py`, `tests/unit/test_types.py`, `tests/unit/test_errors.py`.
- **Scope:** M. **Criteria:** AC-15, AC-21 foundation.

### T05 — validate strict JSON and the schema profile

- [x] Complete T05.
- **Deliverable:** Strict bounded JSON parsing and supported-schema validation with local-only references.
- **Acceptance:** (1) Duplicate keys/nonfinite numbers/unsupported keywords fail; (2) remote and cyclic refs cannot retrieve or recurse indefinitely; (3) all documented valid schemas work.
- **Verify:** `uv run --frozen pytest tests/unit/test_json_io.py tests/unit/test_schema_profile.py` with runtime egress blocked.
- **Dependencies:** T04.
- **Files:** `src/prompt_contracts/validation/json_io.py`, `src/prompt_contracts/validation/profile.py`, `tests/unit/test_json_io.py`, `tests/unit/test_schema_profile.py`.
- **Scope:** M. **Criteria:** AC-07, AC-08, AC-17 foundations.

### T06 — validate manifests and confined asset paths

- [x] Complete T06.
- **Deliverable:** Manifest parsing and bounded, root-confined asset discovery.
- **Acceptance:** (1) Missing/unknown fields and unsupported roles fail; (2) traversal, symlinks, nonportable collisions, and unreferenced runtime assets fail; (3) limits apply before large assets are decoded.
- **Verify:** `uv run --frozen pytest tests/unit/test_manifest.py tests/unit/test_paths.py`.
- **Dependencies:** T04, T05.
- **Files:** `src/prompt_contracts/loading/manifest.py`, `src/prompt_contracts/loading/paths.py`, `tests/unit/test_manifest.py`, `tests/unit/test_paths.py`.
- **Scope:** M. **Criteria:** AC-07, AC-13.

### T07 — implement the single-pass renderer

- [x] Complete T07.
- **Deliverable:** A compiled token parser and renderer for `placeholders-v1`.
- **Acceptance:** (1) Escapes and syntax failures follow the specification; (2) input values are inserted once without expression evaluation; (3) message ordering and whitespace are preserved.
- **Verify:** `uv run --frozen pytest tests/unit/test_renderer.py tests/properties/test_rendering.py`.
- **Dependencies:** T04, T02.
- **Files:** `src/prompt_contracts/rendering/parser.py`, `src/prompt_contracts/rendering/renderer.py`, `tests/unit/test_renderer.py`, `tests/properties/test_rendering.py`.
- **Scope:** M. **Criteria:** AC-02, AC-05, AC-06.

### T08 — connect loading, input validation, and rendering

- [x] Complete T08.
- **Deliverable:** One application-facing load/render path using verified snapshot bytes and schema-checked inputs.
- **Acceptance:** (1) A valid directory renders without networking; (2) missing/unexpected/type-invalid inputs fail without coercion; (3) changed filesystem content cannot alter an already loaded snapshot.
- **Verify:** `uv run --frozen pytest tests/integration/test_render_roundtrip.py tests/unit/test_inputs.py`.
- **Dependencies:** T05, T06, T07.
- **Files:** `src/prompt_contracts/contract.py`, `src/prompt_contracts/loading/loader.py`, `src/prompt_contracts/validation/inputs.py`, `tests/integration/test_render_roundtrip.py`, `tests/unit/test_inputs.py`.
- **Scope:** M. **Criteria:** AC-01–AC-04, AC-14.

### T09 — parse and validate contract outputs

- [x] Complete T09.
- **Deliverable:** Explicit text/JSON output validation without repair or coercion.
- **Acceptance:** (1) Valid output returns the declared type; (2) fences, prose, duplicate keys, malformed JSON, and schema violations fail distinctly; (3) output limits apply before parsing.
- **Verify:** `uv run --frozen pytest tests/unit/test_outputs.py tests/integration/test_output_roundtrip.py`.
- **Dependencies:** T05, T08.
- **Files:** `src/prompt_contracts/validation/outputs.py`, `src/prompt_contracts/contract.py`, `tests/unit/test_outputs.py`, `tests/integration/test_output_roundtrip.py`.
- **Scope:** M. **Criteria:** AC-16, AC-17.

### T10 — exercise limits and privacy failure paths

- [x] Complete T10.
- **Deliverable:** Adversarial boundary corpus proving errors and default diagnostics do not expose inputs or outputs.
- **Acceptance:** (1) Depth/size/node limits produce controlled errors; (2) synthetic secret markers never occur in public diagnostics; (3) rendering and validation do not mutate supplied objects or returned contract state.
- **Verify:** `uv run --frozen pytest tests/properties/test_limits.py tests/integration/test_privacy.py tests/unit/test_errors.py`.
- **Dependencies:** T08, T09.
- **Files:** `tests/properties/test_limits.py`, `tests/integration/test_privacy.py`, `src/prompt_contracts/errors.py`, `src/prompt_contracts/validation/json_io.py`, `src/prompt_contracts/types.py`.
- **Scope:** M. **Criteria:** AC-13, AC-15, AC-21.

### Checkpoint M1

- [x] Valid and invalid load → input validation → render → output validation flows pass offline.
- [x] Property tests cover literal values, determinism, and bounded failure.
- [x] Error privacy has executable evidence.
- [x] Review public type/error contracts before identity and integrations depend on them.

## M2 — identities, locks, resources, and CLI

### T11 — define and implement byte-based identity

- [x] Complete T11.
- **Deliverable:** `pc-bundle-v1` digest implementation and portable golden vectors.
- **Acceptance:** (1) Every runtime file participates; (2) changed template/schema/manifest/order changes identity; (3) identical snapshots have identical digest across supported Python/OS environments.
- **Verify:** `uv run --frozen pytest tests/unit/test_digest.py tests/properties/test_identity.py`.
- **Dependencies:** T08.
- **Files:** `src/prompt_contracts/identity/digest.py`, `tests/unit/test_digest.py`, `tests/properties/test_identity.py`, `.gitattributes`, `docs/decisions/0003-byte-based-identity.md`.
- **Scope:** M. **Criteria:** AC-09, AC-14.

### T12 — enforce locked immutable registries

- [x] Complete T12.
- **Deliverable:** Strict lock parsing/generation, locked startup lookup, registry conflicts, freeze behavior.
- **Acceptance:** (1) Old lock plus changed bytes fails; (2) same name/version with different digest cannot register; (3) lock generation is atomic and frozen state cannot mutate.
- **Verify:** `uv run --frozen pytest tests/unit/test_registry.py tests/integration/test_locks.py`.
- **Dependencies:** T11.
- **Files:** `src/prompt_contracts/identity/lock.py`, `src/prompt_contracts/registry.py`, `tests/unit/test_registry.py`, `tests/integration/test_locks.py`.
- **Scope:** M. **Criteria:** AC-10, AC-11, AC-15.

### T13 — load installed package resources

- [x] Complete T13.
- **Deliverable:** Resource-reader support independent of the current working directory.
- **Acceptance:** (1) A trusted package resource can supply the same verified asset snapshot; (2) path policy still applies; (3) filesystem and packaged versions give the same identity.
- **Verify:** `uv run --frozen pytest tests/integration/test_resources.py`; execute from a temporary directory outside the checkout.
- **Dependencies:** T12.
- **Files:** `src/prompt_contracts/loading/resources.py`, `src/prompt_contracts/loading/loader.py`, `tests/integration/test_resources.py`, `examples/basic_render.py`.
- **Scope:** M. **Criteria:** AC-01, AC-22.

### T14 — expose lint/render/lock/verify commands

- [x] Complete T14.
- **Deliverable:** CLI commands sharing the runtime implementation and stable reporting/exit conventions.
- **Acceptance:** (1) Valid/invalid cases return documented exit codes; (2) JSON reports are deterministic and sanitized; (3) existing locks are not silently replaced.
- **Verify:** `uv run --frozen pytest tests/integration/test_cli.py`; `uv run --frozen python -m prompt_contracts --help`.
- **Dependencies:** T09, T12, T13.
- **Files:** `src/prompt_contracts/cli/main.py`, `src/prompt_contracts/cli/commands.py`, `src/prompt_contracts/cli/reporting.py`, `src/prompt_contracts/__main__.py`, `tests/integration/test_cli.py`.
- **Scope:** M. **Criteria:** AC-03, AC-11, AC-21, AC-34.

### T15 — verify distributions and import boundaries

- [x] Complete T15.
- **Deliverable:** Clean wheel/sdist installation checks and explicit public dependency boundaries.
- **Acceptance:** (1) Core wheel works without SDK or Node; (2) typing/reference resources and declared licensing metadata ship correctly, with a selected license file mandatory before public distribution; (3) tests run outside checkout and optional modules are not imported by core.
- **Verify:** `uv build`; `uv run --frozen python scripts/verify_distribution.py --dist-dir dist`; `uv run --frozen python scripts/check_import_boundaries.py`.
- **Dependencies:** T14.
- **Files:** `scripts/verify_distribution.py`, `scripts/check_import_boundaries.py`, `tests/packaging/test_installed_package.py`, `src/prompt_contracts/py.typed`, `pyproject.toml`.
- **Scope:** M. **Criteria:** AC-01, AC-22, AC-30.

### Checkpoint M2

- [x] Published-version identity cannot change unnoticed by a trusted lock.
- [x] CLI and Python API share the runtime path.
- [x] Wheel and sdist both work outside source checkout.
- [x] Any public API changes found during this checkpoint are settled before consumer migrations.

## M3 — gateway integration and actual reuse

### T16 — map rendered prompts to SDK requests

- [x] Complete T16.
- **Deliverable:** Optional gateway adapter with explicit provider capability profiles.
- **Acceptance:** (1) Returns only supported message/response-format kwargs; (2) unsupported strict schema mapping fails before transport; (3) local validation mode is opt-in and identities are checked.
- **Verify:** `uv run --frozen --extra gateway pytest tests/adapters/test_gateway_requests.py`; exercise minimum and locked SDK environments in adapter jobs.
- **Dependencies:** T15.
- **Files:** `src/prompt_contracts/adapters/gateway.py`, `tests/adapters/test_gateway_requests.py`, `pyproject.toml` + `uv.lock`, `docs/integrations/gateway-sdk.md`.
- **Scope:** M. **Criteria:** AC-19, AC-20, AC-23.

### T17 — normalize completion status and validate responses

- [x] Complete T17.
- **Deliverable:** Response mapping with a runnable fake-gateway example.
- **Acceptance:** (1) Sync/async client paths preserve host transport ownership; (2) truncation/tool calls/empty content/refusal metadata are handled as documented; (3) no repair/retry/fallback call is added.
- **Verify:** `uv run --frozen --extra gateway pytest tests/adapters/test_gateway_responses.py`; `uv run --frozen --extra gateway python examples/gateway_roundtrip.py`.
- **Dependencies:** T16.
- **Files:** `src/prompt_contracts/adapters/gateway.py`, `tests/adapters/test_gateway_responses.py`, `examples/gateway_roundtrip.py`, `docs/integrations/gateway-sdk.md`.
- **Scope:** M. **Criteria:** AC-03, AC-18, AC-23, AC-34.

### T18 — capture Ace's legacy rendering baseline

- [ ] Complete T18.
- **Deliverable:** Consumer-owned synthetic input/message goldens for the selected flow, taken before replacing its renderer.
- **Acceptance:** (1) Normal, Unicode, braces, missing-evidence, and size-boundary cases are included; (2) system/user order and exact whitespace are captured; (3) source commit and capture method are recorded.
- **Verify:** From Ace's backend, run the focused offline prompt-contract tests selected in T01; confirm fixture capture does not require a model.
- **Dependencies:** T01, T15.
- **Files:** Ace consumer: one selected-flow test, one synthetic fixture file, migration guide/evidence document.
- **Scope:** M. **Criteria:** AC-02, AC-05, AC-29 preparation.

### T19 — author Ace's first immutable contract

- [ ] Complete T19.
- **Deliverable:** One application-owned contract bundle corresponding to the captured flow.
- **Acceptance:** (1) Asset closure is complete; (2) existing formatting is representable without embedded code; (3) lint and render match the baseline for accepted inputs.
- **Verify:** In the consumer's candidate-wheel environment, run `prompt-contracts lint contracts/` and fixture parity tests. Paths are finalized by T01.
- **Dependencies:** T18, T14.
- **Files:** Ace consumer contract: `contract.toml`, system template, user template, input schema, output schema.
- **Scope:** M. **Criteria:** AC-02, AC-04, AC-07, AC-29 preparation.

### T20 — adopt the library in Ace's selected flow

- [ ] Complete T20.
- **Deliverable:** Production delegation through the new runtime, retaining existing transport/domain validation.
- **Acceptance:** (1) Dependency and contract locks pin the candidate; (2) existing caller metadata is preserved or explicitly mapped; (3) selected regression suites and rollback pass.
- **Verify:** From Ace's backend, run its focused generation/prompt tests and existing offline full backend suite using T01's recorded commands; perform an artifact rollback drill with synthetic data.
- **Dependencies:** T19, T17.
- **Files:** Ace consumer: selected registry/facade or flow file, `backend/pyproject.toml` + dependency lock, `contracts.lock.json`, selected-flow test, migration evidence document.
- **Scope:** M. **Criteria:** AC-03, AC-21, AC-22, AC-29.

### T21 — capture the job assistant's baseline

- [ ] Complete T21.
- **Deliverable:** Consumer-owned fixtures for the selected prompt and its current shared schema.
- **Acceptance:** (1) Exact legacy version labels and rendering are recorded; (2) CV evidence uses synthetic facts; (3) existing claim/review guarantees are linked to current tests.
- **Verify:** Run `make test-unit` and the focused prompt-library tests selected in T01 before migration; record the selected dataset/schema revision.
- **Dependencies:** T01, T15.
- **Files:** Job-assistant consumer: selected-flow test, synthetic baseline fixture, migration evidence document.
- **Scope:** M. **Criteria:** AC-05, AC-21, AC-29 preparation.

### T22 — author the job assistant's first contract bundle

- [ ] Complete T22.
- **Deliverable:** Versioned prompt and per-version schema assets preserving the current flow.
- **Acceptance:** (1) Shared schema copied into immutable version closure; (2) missing placeholders are explicitly required inputs; (3) accepted inputs retain exact message parity.
- **Verify:** `prompt-contracts lint contracts/`; run selected consumer parity cases against the candidate wheel.
- **Dependencies:** T21, T14.
- **Files:** Job-assistant consumer contract: `contract.toml`, system template, user template, input schema, output schema. If the original flow has one message only, omit the unused asset rather than inventing a new instruction.
- **Scope:** M. **Criteria:** AC-02, AC-03, AC-07, AC-09.

### T23 — adopt the library in the job assistant

- [ ] Complete T23.
- **Deliverable:** Delegating prompt facade with verified locks and unchanged application review/claim checks.
- **Acceptance:** (1) Missing inputs cause zero gateway calls; (2) legacy labels and new identities coexist predictably; (3) unit/eval/import-contract tests and rollback pass.
- **Verify:** `make test-unit`; `make contracts`; `make evals` under existing offline configuration; synthetic rollback drill. Do not enable real-provider tests implicitly.
- **Dependencies:** T22, T17.
- **Files:** Job-assistant consumer: `backend/app/prompts/registry.py` or selected flow facade, `backend/pyproject.toml` + dependency lock, contract lock, selected-flow test, migration evidence document.
- **Scope:** M. **Criteria:** AC-03, AC-21, AC-22, AC-29.

### T24 — establish the integration-prerelease artifact pipeline

- [ ] Complete T24.
- **Deliverable:** Tag/version validation, released-contract preservation checks, and a build-once verified candidate artifact; initial OIDC/TestPyPI publication only when release work is authorized and setup is available.
- **Acceptance:** (1) Mismatched tag/version/source cannot publish; (2) changing an old version and updating its lock still fails; (3) consumers are rechecked against the actual candidate artifact rather than an unrecorded checkout.
- **Verify:** `uv run --frozen pytest tests/integration/test_release_policy.py`; execute a nonpublishing `release.yml` validation run; verify both consumer evidence records identify candidate version and checksums. A public TestPyPI/PyPI prerelease also requires the license/provenance and publishing-setup conditions in T34; the prerelease label does not bypass them. External publication is conditional on release authorization, not a substitute for local checks.
- **Dependencies:** T15, T20, T23.
- **Files:** `.github/workflows/release.yml`, `scripts/check_release.py`, `scripts/verify_published_contracts.py`, `tests/integration/test_release_policy.py`, `docs/operations/releases.md`.
- **Scope:** M. **Criteria:** AC-12, AC-29, AC-30, AC-32.

### Checkpoint M3 / v0.1 integration candidate

- [x] SDK adapter works without owning credentials, retries, or clients.
- [ ] Two real consumers run migrated flows with candidate artifact and contract locks.
- [ ] Accepted-input parity is demonstrated; stricter rejected cases are documented intentionally.
- [ ] Domain truth/review checks remain in the applications and their existing suites pass.
- [ ] All v0.1 acceptance IDs have evidence, including final CI/release criteria as the pipeline is completed in M5 before any production release.

## M4 — differentiating public features

### T25 — define directional compatibility reports

- [x] Complete T25.
- **Deliverable:** Public report types, stable rule IDs, and a labeled change corpus.
- **Acceptance:** (1) Input/output directions are distinct; (2) optional-to-required output strengthening is represented correctly; (3) unsupported proofs yield `unknown` and wording changes trigger behavioral review.
- **Verify:** `uv run --frozen pytest tests/compatibility/test_report_contract.py`; manually review corpus against plan section 11.
- **Dependencies:** T12, T05.
- **Files:** `src/prompt_contracts/compatibility/models.py`, `tests/compatibility/test_report_contract.py`, `tests/fixtures/compatibility_cases.json`, `docs/decisions/0005-directional-compatibility.md`.
- **Scope:** M. **Criteria:** AC-24–AC-26.

### T26 — implement conservative compatibility rules

- [x] Complete T26.
- **Deliverable:** Tested subset/widening/narrowing analysis for the supported profile.
- **Acceptance:** (1) Known cases match the labeled corpus; (2) combined/uncertain changes never default to compatible; (3) local refs and complexity remain bounded under the same schema policy.
- **Verify:** `uv run --frozen pytest tests/compatibility/test_rules.py tests/properties/test_compatibility.py`.
- **Dependencies:** T25.
- **Files:** `src/prompt_contracts/compatibility/compare.py`, `src/prompt_contracts/compatibility/rules.py`, `tests/compatibility/test_rules.py`, `tests/properties/test_compatibility.py`.
- **Scope:** M. **Criteria:** AC-24, AC-25.

### T27 — expose compatibility checks in CLI and CI

- [x] Complete T27.
- **Deliverable:** `diff` command, deterministic reports, and explicit compatible-only policy behavior.
- **Acceptance:** (1) Breaking/unknown changes fail with exit 5 under the policy; (2) structural results stay separate from behavioral-review requirements; (3) reports include both identities and stable report-format version.
- **Verify:** `uv run --frozen pytest tests/integration/test_cli_diff.py`; exercise representative old/new fixtures from both consumers.
- **Dependencies:** T26, T14.
- **Files:** `src/prompt_contracts/cli/commands.py`, `src/prompt_contracts/cli/reporting.py`, `tests/integration/test_cli_diff.py`, `docs/compatibility.md`.
- **Scope:** M. **Criteria:** AC-24–AC-26.

### T28 — implement a production-renderer evaluation bridge

- [x] Complete T28.
- **Deliverable:** Python bridge helpers and synthetic Promptfoo example using context variables and an explicit offline provider.
- **Acceptance:** (1) No separate business-template renderer exists; (2) contract ref/lock/model policy are explicit; (3) validation failures become failed cases with safe metadata.
- **Verify:** `uv run --frozen --extra gateway pytest tests/adapters/test_promptfoo_bridge.py`.
- **Dependencies:** T17, T12.
- **Files:** `src/prompt_contracts/adapters/promptfoo.py`, `examples/promptfoo/provider.py`, `examples/promptfoo/promptfooconfig.yaml`, `examples/promptfoo/cases.yaml`, `tests/adapters/test_promptfoo_bridge.py`.
- **Scope:** M. **Criteria:** AC-27, AC-28, AC-33.

### T29 — verify the bridge with the real Promptfoo CLI

- [x] Complete T29.
- **Deliverable:** Exactly pinned Node tooling and an offline real-CLI compatibility test.
- **Acceptance:** (1) Production/eval message and schema mappings match; (2) negative validation cases fail evaluation; (3) no provider key/network call occurs and cache reuse cannot hide contract changes.
- **Verify:** `npm --prefix tools/promptfoo ci`; `make ci-promptfoo`; inspect the saved synthetic report and expected nonzero negative-case exit.
- **Dependencies:** T28.
- **Files:** `tools/promptfoo/package.json` + `package-lock.json`, `tests/adapters/test_promptfoo_cli.py`, `Makefile`, `docs/integrations/promptfoo.md`.
- **Scope:** M. **Criteria:** AC-27, AC-28, AC-33.

### T30 — measure runtime cost and emit safe metadata

- [x] Complete T30.
- **Deliverable:** Reproducible cold/warm benchmark and a host-oriented metadata recipe without raw data logging.
- **Acceptance:** (1) Benchmark includes fixtures/environment/iteration method; (2) contract/policy/adapter identities can accompany a result; (3) no raw input hashes or high-cardinality metric labels are enabled by default.
- **Verify:** `uv run --frozen python benchmarks/runtime.py --iterations 1000`; `uv run --frozen pytest tests/unit/test_execution_metadata.py`.
- **Dependencies:** T12, T17.
- **Files:** `benchmarks/runtime.py`, `benchmarks/README.md`, `src/prompt_contracts/types.py`, `tests/unit/test_execution_metadata.py`, `docs/errors-and-privacy.md`.
- **Scope:** M. **Criteria:** AC-21, AC-35.

### Checkpoint M4 / v0.2 feature complete

- [x] Compatibility never overstates uncertain cases and follows directional rules.
- [x] The actual Promptfoo CLI proves rendering parity and negative-case failure.
- [x] Benchmarks and safe metadata have recorded evidence.
- [x] Public API remains focused; deferred platform features have not entered the release.

## M5 — complete docs, required gates, and release evidence

### T31 — write the runtime and authoring guides

- [x] Complete T31.
- **Deliverable:** Quickstart, authoring, rendering, and identity documentation with executable synthetic examples.
- **Acceptance:** (1) A new user can render/validate offline; (2) version/lock/update rules and limitations are explicit; (3) documented examples execute from a clean environment.
- **Verify:** `uv run --frozen mkdocs build --strict`; `uv run --frozen pytest tests/integration/test_documented_examples.py`.
- **Dependencies:** T14, T27.
- **Files:** `README.md`, `docs/index.md`, `docs/rendering.md`, `docs/identity-and-locks.md`, `tests/integration/test_documented_examples.py`.
- **Scope:** M. **Criteria:** AC-34.

### T32 — finish consumer and operations guidance

- [ ] Complete T32.
- **Deliverable:** Real migration evidence, deployment/rollback runbooks, and contribution boundaries.
- **Acceptance:** (1) Both consumers have exact commands/versions/results; (2) package and contract rollback is described as one unit; (3) new contributors understand privacy, versioning, and release responsibilities.
- **Verify:** Execute both documented synthetic rollback drills and review the evidence against AC-29; run strict docs build.
- **Dependencies:** T20, T23, T24, T29.
- **Files:** `docs/integrations/ace-your-interview.md`, `docs/integrations/job-hunting-assistant.md`, `docs/operations/rollback.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- **Scope:** M. **Criteria:** AC-21, AC-29, AC-34.

### T33 — complete repository gates and maintenance checks

- [ ] Complete T33.
- **Deliverable:** Required security/quality/portability/package/docs/Promptfoo jobs, final gate, and scheduled maintenance.
- **Acceptance:** (1) Failed/cancelled/unexpectedly skipped mandatory jobs block the gate; (2) PRs cannot run credentialed evals or publish; (3) optional extras and dependency-floor/latest adapter checks run explicitly.
- **Verify:** Actionlint plus controlled failure/skip gate drill; `make ci-quality`; `make ci-package`; `make ci-promptfoo`; `make ci-docs`. Record actual emitted check names.
- **Dependencies:** T15, T24, T29, T31, T32.
- **Files:** `.github/workflows/ci.yml`, `.github/workflows/maintenance.yml`, `.github/dependabot.yml`, `.github/CODEOWNERS`, `docs/operations/ci.md`.
- **Scope:** M. **Criteria:** AC-23, AC-30, AC-31, AC-33.

### T34 — verify release setup and candidate provenance

- [ ] Complete T34.
- **Deliverable:** Release metadata/license/support policy and reviewed publishing configuration.
- **Acceptance:** (1) Name/license/provenance and dependency support decisions are resolved; (2) one publishing owner uses protected tag/environment/OIDC; (3) checksum-verified wheel/sdist are built once and publication receives those exact artifacts.
- **Verify:** `uv build`; `uv run --frozen twine check dist/*`; `uv run --frozen python scripts/verify_distribution.py --dist-dir dist`; release policy tests and nonpublishing workflow rehearsal. Operator setup must be confirmed with evidence rather than assumed from YAML.
- **Dependencies:** T24, T33.
- **Files:** `.github/workflows/release.yml`, `scripts/check_release.py`, `pyproject.toml`, `LICENSE`, `docs/operations/releases.md`.
- **Scope:** M. **Criteria:** AC-12, AC-30–AC-33.

### T35 — publish and verify the authorized beta release

- [ ] Complete T35 only when release execution is authorized.
- **Deliverable:** Tagged candidate/beta artifacts and downstream adoption evidence.
- **Acceptance:** (1) Tag/version/commit and checksums match; (2) a fresh install from the published artifact works without checkout; (3) both consumer locks identify the adopted artifact and rollback remains tested.
- **Verify:** Run the protected release workflow; fresh core/extra installation smoke; repeat focused consumer integration/evaluation checks; compare all acceptance IDs with evidence links.
- **Dependencies:** T34, M4 checkpoint, both consumer acceptance records.
- **Files:** `CHANGELOG.md`, release evidence in `docs/operations/releases.md`, package version/lock updates if required; consumer dependency-lock PRs in their own repositories.
- **Scope:** M. **Criteria:** All applicable AC IDs.

### Final acceptance checkpoint

- [ ] Every applicable acceptance ID has an executed check or linked consumer/operator evidence.
- [x] Package and contract versions are independently pinned and immutable.
- [ ] Two applications demonstrate the dependency's practical value.
- [ ] Runtime/evaluation parity and conservative compatibility reporting are demonstrated publicly with synthetic data.
- [ ] Published artifacts, release instructions, limitations, and rollback instructions agree.
- [x] No planned command, performance target, live evaluation, or deployment is reported as verified without evidence.

## Audit follow-up (November 14, 2026)

Reopened checkboxes require external consumer changes or hosted/operator evidence. T24/T33/T34 have repository implementations and local tests, but have not been exercised on GitHub or an index. The real CLI check is selected with `pytest -m promptfoo`; ordinary Python checks exclude it and the dedicated CI job requires it. See the review report for the acceptance mapping and exact verification results.
