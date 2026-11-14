# Job-Hunting Assistant: proposed migration

Status checked November 14, 2026 at source commit `4164e0db29850c30a78de5f78159497af2c32335` (`job_hunting_assitant`). The application still uses `backend/app/prompts/registry.py` and `backend/app/application/answers/generate.py`; its dependency manifest and lock do not include `prompt-contracts`.

The fixtures under `tests/fixtures/consumers/job_hunting_assistant/` are hand-authored synthetic examples. They exercise library validation and version rollback, but are not captured legacy messages or evidence of an application migration.

## Inventory differences that must be resolved

The actual `answer_generation/v1.md` starts “You answer one question from a job application form, for a candidate.” It contains evidence-only and protected-attribute rules and no template placeholders. The application caller assembles the interaction. Its output schema permits an empty `answer` when evidence is insufficient.

The synthetic contract uses a different career-coach prompt with `question`, `job_description`, and `user_profile` placeholders, and requires a nonempty `answer`. It cannot be treated as a message-preserving or behavior-preserving replacement for the current flow.

## Work required before acceptance

1. Capture ordered messages from the actual answer-generation caller using synthetic evidence, including its empty-answer/review path. Preserve the legacy version label and record capture commands and source revision.
2. Author application-owned contract assets preserving the existing instructions, output schema, and accepted inputs. Document any deliberate stricter rejection separately.
3. Install and pin a checksum-identified candidate package and contract lock. Delegate production rendering and structural validation while retaining application claim, evidence, review and persistence checks.
4. Run the consumer's unit, import-contract and offline evaluation targets (`make test-unit`, `make contracts`, `make evals`) under its documented offline configuration; record actual results.
5. Demonstrate rollback of the package and contract pair without editing a locked version.

AC-29 and backlog T21–T23 remain incomplete until these consumer-owned changes and evidence exist.
