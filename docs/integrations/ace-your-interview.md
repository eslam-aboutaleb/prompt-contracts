# Ace Your Interview: proposed migration

Status checked November 14, 2026 at source commit `583ff0be33de5befb99a3d66e036b4260b878bf0` (`study-app`). The application still uses `backend/app/services/prompt_registry.py` and `backend/app/services/topic_language_advisor.py`; its dependency manifest and lock do not include `prompt-contracts`.

The fixtures under `tests/fixtures/consumers/ace_your_interview/` are hand-authored synthetic examples. They demonstrate the library API and version rollback; they were not captured from the current application's renderer and do not establish message parity or adoption.

## Inventory differences that must be resolved

The real advisor system message begins “You are a technical curriculum advisor.” Its user-message builder uses `render_contract`, topic metadata, section content and optional MCP context. It expects `requires_programming` and `language_options`.

The synthetic contract instead expects `recommended_languages`, `primary_language`, `reasoning`, and `topic_type`, and takes prebuilt `topic_block` and `notes_block`. Replacing the application flow with this fixture would change both its messages and output interface.

## Work required before acceptance

1. Capture the actual `_build_prompt` and registry system message for normal, Unicode, braces, missing-context, and boundary-size synthetic inputs. Record the exact capture command and source revision.
2. Author an application-owned contract matching those messages and its existing response schema. Keep preprocessing and domain checks in the application.
3. Install a checksum-identified candidate distribution; pin the application dependency and contract lock, then delegate the selected generation path to the library.
4. Run the selected flow tests and existing backend regression suite in the consumer repository. Record commands and results without claiming unexecuted checks.
5. Demonstrate a library-and-contract rollback against that same candidate artifact.

AC-29 and backlog T18–T20 remain incomplete until these consumer-owned changes and evidence exist.
