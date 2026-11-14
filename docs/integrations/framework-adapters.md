# Agent & Framework Adapter Boundary

`prompt-contracts` keeps agent frameworks (such as LangGraph, LlamaIndex, or custom orchestrators) outside the core runtime boundary.

## Recommended Integration Pattern

1. **Startup**: Load and freeze a `PromptRegistry` (`PromptRegistry.from_directory(...)` or `PromptRegistry.from_package_resources(...)`).
2. **Node / Step Entry**: Resolve the pinned contract version (`contract = registry.get("domain.task@1.0.0")`) and call `rendered = contract.render(step_inputs)`.
3. **Transport**: Pass `rendered.to_messages_list()` (or `to_gateway_request(rendered, contract=contract).to_kwargs()`) to your transport client.
4. **Node / Step Exit**: Validate the raw completion via `contract.validate_output(raw_text)` (or `validate_gateway_response(contract, response)`) before updating state or persisting results.
