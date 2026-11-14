# prompt-contracts

Version your prompts with the input and response formats your application expects. Load them from your repository, render messages for your existing model client, and validate results before using them.

Start with [Set up your first contract](getting-started.md). It covers installation, every file you need, calling from an application, handling errors, and updating prompts.

## Integrations

- [llm-gateway-sdk](integrations/gateway-sdk.md): build requests and validate completion states.
- [Other clients and frameworks](integrations/framework-adapters.md): connect the renderer to your existing transport.
- [Promptfoo](integrations/promptfoo.md): evaluate prompts using the production renderer.

## Reference

- [Contract format](contract-format.md): manifest and schema fields.
- [Template rendering](rendering.md): placeholders and escaping.
- [Lockfiles](identity-and-locks.md): track prompt file changes.
- [Schema compatibility](compatibility.md): compare contract versions.
- [Errors and privacy](errors-and-privacy.md): handle failures without exposing rejected values.
