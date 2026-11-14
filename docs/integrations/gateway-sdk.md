# `llm-gateway-sdk` Adapter

`prompt_contracts.adapters.gateway` bridges a rendered contract to `llm-gateway-sdk` (`GatewayClient` and `AsyncGatewayClient`) without owning client lifecycle, model aliases, credentials, timeouts, or retry policies.

## Installation

```bash
pip install "llm-gateway-sdk @ git+https://github.com/eslam-aboutaleb/llm-gateway-sdk.git@3da8548e528ec6ed404ef2b115f0568db83fa7bd"
pip install ".[gateway]"
```

These commands run from this repository checkout. On November 14, 2026, the SDK version `0.1.0` was not available on PyPI; the tested source is the pinned Git revision above. The floor check uses that revision with `jsonschema==4.23.0` and `referencing==0.35.0`. The latest check resolves SDK `main` and the newest core dependencies within the declared ranges in a separate environment, then verifies dependency consistency and runs the offline suite. Neither check mutates `uv.lock`.

## Explicit Capability Modes

- `GatewayCapabilities.strict_json_schema()`: Emits `response_format={"type": "json_schema", "json_schema": {"name": ..., "strict": True, "schema": ...}}`. Verifies pre-request that every object schema sets `additionalProperties: false` and lists all properties in `required`.
- `GatewayCapabilities.local_validation()`: Explicit opt-in mode that omits `response_format` on the wire and validates the response locally via `validate_gateway_response`. There is no silent downgrade from strict mode to local mode.

## Synchronous & Asynchronous Usage

```python
from llm_gateway_sdk import GatewaySettings, create_async_client, create_client
from prompt_contracts.adapters.gateway import (
    GatewayCapabilities,
    build_execution_metadata,
    to_gateway_request,
    validate_gateway_response,
)

rendered = contract.render(inputs)
gw_request = to_gateway_request(
    rendered,
    contract=contract,
    capabilities=GatewayCapabilities.strict_json_schema(),
)

client = create_client(GatewaySettings(base_url="...", api_key="..."))
response = client.complete(model="structured-output", **gw_request.to_kwargs())
validated = validate_gateway_response(contract, response)
metadata = build_execution_metadata(
    contract,
    rendered,
    response=response,
    model_alias="structured-output",
    output_valid=True,
)
```

## Non-Valid Completion Status Handling

`validate_gateway_response` checks completion status before calling `contract.validate_output`:

- Missing or multiple choices (`len(choices) != 1`) -> `IncompleteCompletionError(code=PC_COMPLETION_CHOICE_COUNT)`
- Truncation (`finish_reason == "length"`) -> `IncompleteCompletionError(code=PC_COMPLETION_TRUNCATED)`
- Content filter or refusal (`finish_reason` in `{"content_filter", "refusal", "safety"}` or `message.refusal`) -> `IncompleteCompletionError(code=PC_COMPLETION_REFUSED_OR_FILTERED)`
- Unexpected tool calls (`finish_reason == "tool_calls"` or `message.tool_calls`) -> `IncompleteCompletionError(code=PC_COMPLETION_UNEXPECTED_TOOL_CALL)`
- Empty or null content -> `IncompleteCompletionError(code=PC_COMPLETION_EMPTY_CONTENT)`
