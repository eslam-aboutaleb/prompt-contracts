# Promptfoo Evaluation Bridge

`prompt_contracts.adapters.promptfoo` ensures Promptfoo evaluations execute the exact same production contract loader, lock verifier, input validator, single-pass renderer, and output validator used in production.

## Sentinel Prompt & Custom Python Provider

To prevent Promptfoo from double-rendering Nunjucks/Handlebars syntax inside business prompts, `promptfooconfig.yaml` passes a static sentinel prompt (`__PROMPT_CONTRACTS_SENTINEL__`) and delegates rendering to `examples/promptfoo/provider.py`:

```yaml
prompts:
  - "__PROMPT_CONTRACTS_SENTINEL__"

providers:
  - id: file://provider.py
    label: prompt-contracts-production-renderer
    config:
      contracts_root: "."
      lock_file: "contracts.lock.json"
      contract_ref: "career.application-answer@1.0.0"
      mode: "offline"
      model_alias: "offline-scripted"
      dataset_revision: "synthetic-v1"
      schema_mode: "strict_json_schema"
```

## Offline by Default

- In `mode: "offline"` (default), evaluation runs deterministically with zero external network calls using `offline_responder` or `_mock_response`.
- When input or output validation fails, `EvaluationBridgeResult.to_promptfoo_response()` returns `"error": "[<ErrorCode>] <message>"` so Promptfoo marks the test case as failed.
- Cache keys (`compute_evaluation_cache_key`) bind `bundle_digest`, `dataset_revision`, `model_alias`, `schema_mode`, `policy_id`, and `adapter_version`.

## Metadata and caching

`to_promptfoo_response()` excludes raw rendered messages and gateway request data from metadata by default. Synthetic parity tests may explicitly call `to_promptfoo_response(include_rendered_prompt=True)` to include both. Promptfoo itself receives test inputs and outputs; use synthetic datasets in public reports.

The example disables Promptfoo caching (`evaluateOptions.cache: false`) and CI also passes `--no-cache`. The returned cache identifier is metadata, not a replacement for the runner cache key. Keep caching disabled unless the host binds every relevant model option and contract identity into its cache.
