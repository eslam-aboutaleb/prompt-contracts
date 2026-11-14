# prompt-contracts

Keep your application's prompts, inputs, and expected responses versioned together. Validate data before sending it to a model and reject responses that do not match the format your application needs.

Use it when a changed prompt or malformed model response could break your application. It works with your existing model client; you keep control of API calls, credentials, retries, and costs.

## Install

Requires Python 3.11 or newer. Install from GitHub:

```bash
pip install "prompt-contracts @ git+https://github.com/eslam-aboutaleb/prompt-contracts.git@main"
```

For reproducible deployments, replace `main` with a full commit SHA and commit your dependency lockfile. There is no PyPI release yet.

## Add it to your application

A contract is a folder containing a prompt template, an input schema, an output schema, and a small manifest. Keep these files in your application repository.

For example, an answer-writing feature can require a question and verified facts as input, and return an answer with evidence IDs. Start with the [complete setup guide](docs/getting-started.md), or copy the working example:

```bash
git clone https://github.com/eslam-aboutaleb/prompt-contracts.git
mkdir -p prompts
cp -R prompt-contracts/examples/contracts prompts/
cp prompt-contracts/examples/contracts.lock.json prompts/
```

Load the contract once at application startup:

```python
from pathlib import Path
from prompt_contracts import PromptRegistry

registry = PromptRegistry.from_directory(
    Path("prompts"), lock_file="contracts.lock.json"
).freeze()
contract = registry.get("career.application-answer@1.0.0")
```

Wrap your existing model call with rendering and validation:

```python
from collections.abc import Callable
from typing import Any


def draft_answer(
    question: str,
    verified_facts: str,
    complete: Callable[[list[dict[str, str]]], str],
) -> Any:
    rendered = contract.render({
        "question": question,
        "verified_facts": verified_facts,
    })
    raw_json = complete(rendered.to_messages_list())
    return contract.validate_output(raw_json)
```

`complete` is your application function that sends the messages to your model and returns its response text. The messages use the usual `role` and `content` fields. Use the [gateway adapter](docs/integrations/gateway-sdk.md) if you use `llm-gateway-sdk`, or see [framework integration](docs/integrations/framework-adapters.md) for other clients.

You can check the validation step without making an API call:

```python
result = contract.validate_output(
    '{"answer":"I maintained PostgreSQL migrations.",'
    '"evidence_ids":["fact-1"],"needs_review":false}'
)
print(result["answer"])
```

Missing inputs raise `InputValidationError` before the model call. Malformed JSON or a response that fails the schema raises `OutputValidationError`. Handle these errors in your application before using a result. With the core API, your client must also handle refusals, truncation, and tool calls before passing response text to validation; the gateway adapter checks those completion states for you.

Validation checks structure and constraints you define. It does not verify factual accuracy, prevent all prompt injection, or guarantee model quality. You can use [Promptfoo](docs/integrations/promptfoo.md) alongside it to evaluate behavior with the same renderer your application uses.

## Change a prompt safely

1. Create a new version folder when changing a published prompt or schema.
2. Generate the lockfile and review its changes with the prompt changes.
3. Update the contract reference in your application, run your evaluations, and deploy the prompt files with your code.

```bash
prompt-contracts lint prompts/contracts
prompt-contracts lock prompts/contracts --output prompts/contracts.lock.json --update
prompt-contracts verify prompts/contracts --lock prompts/contracts.lock.json
```

Run `lint` and `verify` in CI as well. Lock verification detects files that no longer match the committed lockfile. To compare two versions' input and output schemas, use `prompt-contracts diff OLD_BUNDLE NEW_BUNDLE`; behavioral changes still need evaluation.

## More help

- [Set up your first contract](docs/getting-started.md)
- [Write templates and schemas](docs/contract-format.md)
- [Handle validation errors](docs/errors-and-privacy.md)
- [Load packaged prompt files](examples/packaged_consumer)
- [Evaluate with Promptfoo](docs/integrations/promptfoo.md)
- [Contribute](CONTRIBUTING.md)

[MIT license](LICENSE).
