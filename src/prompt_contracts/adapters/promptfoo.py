"""Production-renderer evaluation bridge for Promptfoo custom Python providers.

Ensures evaluations exercise the exact same contract loader, lock verification, input
validator, single-pass renderer, gateway request mapper, and output validator used in
production, without allowing Promptfoo to double-render business templates.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from prompt_contracts.adapters.gateway import (
    GatewayCapabilities,
    GatewayRequest,
    build_execution_metadata,
    to_gateway_request,
)
from prompt_contracts.errors import ErrorCode, PromptContractError
from prompt_contracts.registry import PromptRegistry
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    ContractRef,
    JSONPrimitive,
    RenderedPrompt,
    RuntimePolicy,
    serialize_compact_json,
)

__all__ = [
    "BRIDGE_ADAPTER_VERSION",
    "EvaluationBridgeConfig",
    "EvaluationBridgeResult",
    "compute_evaluation_cache_key",
    "execute_promptfoo_case",
    "parse_promptfoo_provider_config",
]

BRIDGE_ADAPTER_VERSION = "pc-promptfoo-bridge-v1"


@dataclass(frozen=True, slots=True)
class EvaluationBridgeConfig:
    """Validated configuration for a Promptfoo custom Python provider invocation."""

    contracts_root: Path
    lock_file: Path
    contract_ref: ContractRef
    mode: str = "offline"
    model_alias: str = "offline-scripted"
    dataset_revision: str = "synthetic-v1"
    schema_mode: str = "strict_json_schema"
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY

    def __post_init__(self) -> None:
        if self.mode not in ("offline", "live"):
            raise PromptContractError(
                f"Unsupported evaluation bridge mode {self.mode!r}; expected 'offline' or 'live'",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=str(self.contract_ref),
            )
        if self.schema_mode not in ("strict_json_schema", "local_validation"):
            raise PromptContractError(
                f"Unsupported evaluation schema_mode {self.schema_mode!r}",
                code=ErrorCode.MANIFEST_SCHEMA_INVALID,
                contract_ref=str(self.contract_ref),
            )


@dataclass(frozen=True, slots=True)
class EvaluationBridgeResult:
    """Result of executing a single evaluation case through the production renderer bridge."""

    passed_validation: bool
    output: Any
    rendered_prompt: RenderedPrompt | None
    gateway_request: GatewayRequest | None
    safe_metadata: dict[str, Any]
    cache_key: str
    error_code: str | None = None
    error_message: str | None = None

    def to_promptfoo_response(self, *, include_rendered_prompt: bool = False) -> dict[str, Any]:
        """Format result for Promptfoo's ``call_api(prompt, options, context)`` return contract.

        When input or output validation fails, ``error`` is populated so Promptfoo marks
        the test case as failed rather than treating an empty answer as a pass.
        Raw rendered inputs are excluded from metadata unless explicitly requested for
        synthetic parity checks via ``include_rendered_prompt``.
        """
        meta = {
            **self.safe_metadata,
            "cache_key": self.cache_key,
            "passed_validation": self.passed_validation,
        }
        if include_rendered_prompt and self.rendered_prompt is not None:
            meta["rendered_messages"] = self.rendered_prompt.to_messages_list()
        if include_rendered_prompt and self.gateway_request is not None:
            meta["gateway_kwargs"] = self.gateway_request.to_kwargs()

        if not self.passed_validation:
            err_str = f"[{self.error_code}] {self.error_message}"
            return {
                "output": "",
                "error": err_str,
                "metadata": meta,
            }

        out_val = (
            self.output if isinstance(self.output, str) else serialize_compact_json(self.output)
        )
        return {
            "output": out_val,
            "metadata": meta,
        }


def compute_evaluation_cache_key(
    *,
    bundle_digest: str,
    dataset_revision: str,
    model_alias: str,
    schema_mode: str,
    policy_id: str,
    adapter_version: str = BRIDGE_ADAPTER_VERSION,
) -> str:
    """Compute a cache key binding bundle digest, dataset revision, adapter, model, and policy."""
    payload = json.dumps(
        {
            "adapter_version": adapter_version,
            "bundle_digest": bundle_digest,
            "dataset_revision": dataset_revision,
            "model_alias": model_alias,
            "policy_id": policy_id,
            "schema_mode": schema_mode,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(b"prompt-contracts.eval-cache.v1\n" + payload).hexdigest()
    return f"pc-eval-cache-v1:sha256:{digest}"


def parse_promptfoo_provider_config(
    options: Mapping[str, Any] | None,
    *,
    allowed_base_dir: Path,
) -> EvaluationBridgeConfig:
    """Extract and validate :class:`EvaluationBridgeConfig` from Promptfoo ``options['config']``."""
    raw_cfg = options.get("config", {}) if isinstance(options, Mapping) else {}
    if not isinstance(raw_cfg, Mapping):
        raise PromptContractError(
            "Promptfoo provider options['config'] must be a mapping",
            code=ErrorCode.MANIFEST_SCHEMA_INVALID,
        )

    raw_ref = raw_cfg.get("contract_ref")
    if type(raw_ref) is not str or not raw_ref:
        raise PromptContractError(
            "Promptfoo provider config requires explicit 'contract_ref' ('<name>@<version>')",
            code=ErrorCode.INVALID_CONTRACT_REF,
        )
    contract_ref = ContractRef.parse(raw_ref)

    raw_root = str(raw_cfg.get("contracts_root") or ".")
    raw_lock = str(raw_cfg.get("lock_file") or "contracts.lock.json")

    base_resolved = Path(allowed_base_dir).resolve()
    root_candidate = (base_resolved / raw_root).resolve()
    lock_candidate = (base_resolved / raw_lock).resolve()

    if not root_candidate.is_relative_to(base_resolved):
        raise PromptContractError(
            "Promptfoo provider 'contracts_root' escapes allowed base directory",
            code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            contract_ref=str(contract_ref),
        )
    if not lock_candidate.is_relative_to(base_resolved):
        raise PromptContractError(
            "Promptfoo provider 'lock_file' escapes allowed base directory",
            code=ErrorCode.PATH_TRAVERSAL_OR_UNSAFE,
            contract_ref=str(contract_ref),
        )

    mode = str(raw_cfg.get("mode") or "offline")
    model_alias = str(raw_cfg.get("model_alias") or "offline-scripted")
    dataset_revision = str(raw_cfg.get("dataset_revision") or "synthetic-v1")
    schema_mode = str(raw_cfg.get("schema_mode") or "strict_json_schema")

    return EvaluationBridgeConfig(
        contracts_root=root_candidate,
        lock_file=lock_candidate,
        contract_ref=contract_ref,
        mode=mode,
        model_alias=model_alias,
        dataset_revision=dataset_revision,
        schema_mode=schema_mode,
    )


def execute_promptfoo_case(
    *,
    config: EvaluationBridgeConfig,
    context_vars: Mapping[str, Any],
    offline_responder: Callable[[RenderedPrompt, GatewayRequest, Mapping[str, Any]], str]
    | None = None,
    live_responder: Callable[[RenderedPrompt, GatewayRequest], str] | None = None,
    generation_options: Mapping[str, JSONPrimitive] | None = None,
) -> EvaluationBridgeResult:
    """Run a single evaluation case through the locked production contract pipeline.

    - Blocks accidental ``mode='live'`` execution unless ``PROMPT_CONTRACTS_ALLOW_LIVE_EVAL=true``
      is explicitly set in the environment and not running in pull-request CI (``AC-33``).
    - Converts any input or output validation failure into a structured failed case with
      sanitized metadata and zero raw value leakage (``AC-28``).
    """
    if config.mode == "live":
        in_pr_ci = os.environ.get("GITHUB_EVENT_NAME") in ("pull_request", "pull_request_target")
        live_allowed = os.environ.get("PROMPT_CONTRACTS_ALLOW_LIVE_EVAL", "").lower() == "true"
        if in_pr_ci or not live_allowed:
            raise PromptContractError(
                "Live evaluation mode is blocked unless "
                "PROMPT_CONTRACTS_ALLOW_LIVE_EVAL=true outside PR workflows",
                code=ErrorCode.CAPABILITY_UNSUPPORTED,
                contract_ref=str(config.contract_ref),
            )

    registry = PromptRegistry.from_directory(
        root=config.contracts_root,
        lock_file=config.lock_file,
        policy=config.policy,
    )
    registry.freeze()
    contract = registry.get(config.contract_ref)

    cache_key = compute_evaluation_cache_key(
        bundle_digest=contract.bundle_digest,
        dataset_revision=config.dataset_revision,
        model_alias=config.model_alias,
        schema_mode=config.schema_mode,
        policy_id=contract.policy.policy_id,
    )

    caps = (
        GatewayCapabilities.strict_json_schema()
        if config.schema_mode == "strict_json_schema"
        else GatewayCapabilities.local_validation()
    )

    # The scripted response is harness data. Other keys, including declared names
    # starting with '_', must pass through the production input validator unchanged.
    declared_inputs = contract.input_schema.get("properties", {})
    render_inputs = {
        k: v for k, v in context_vars.items() if k != "_mock_response" or k in declared_inputs
    }

    t0 = time.perf_counter()
    try:
        rendered = contract.render(render_inputs)
        render_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        gateway_req = to_gateway_request(
            rendered,
            contract=contract,
            capabilities=caps,
        )
    except PromptContractError as exc:
        from prompt_contracts import __version__

        safe_meta = {
            "bundle_digest": contract.bundle_digest,
            "contract_name": contract.name,
            "contract_ref": str(contract.ref),
            "contract_version": contract.version,
            "dataset_revision": config.dataset_revision,
            "digest_algorithm": contract.digest_algorithm,
            "error": exc.to_dict(),
            "input_valid": False,
            "library_version": __version__,
            "model_alias": config.model_alias,
            "output_valid": None,
            "policy_id": contract.policy.policy_id,
            "renderer": contract.renderer,
        }
        return EvaluationBridgeResult(
            passed_validation=False,
            output=None,
            rendered_prompt=None,
            gateway_request=None,
            safe_metadata=safe_meta,
            cache_key=cache_key,
            error_code=exc.code,
            error_message=exc.safe_message,
        )

    if config.mode == "offline":
        if offline_responder is not None:
            raw_response_text = offline_responder(rendered, gateway_req, context_vars)
        elif "_mock_response" in context_vars and isinstance(context_vars["_mock_response"], str):
            raw_response_text = context_vars["_mock_response"]
        else:
            raise PromptContractError(
                "Offline evaluation requires an offline_responder "
                "callable or '_mock_response' context variable",
                code=ErrorCode.COMPLETION_EMPTY_CONTENT,
                contract_ref=str(contract.ref),
            )
    else:
        if live_responder is None:
            raise PromptContractError(
                "Live evaluation requires an explicit host live_responder callable",
                code=ErrorCode.CAPABILITY_UNSUPPORTED,
                contract_ref=str(contract.ref),
            )
        raw_response_text = live_responder(rendered, gateway_req)

    t1 = time.perf_counter()
    try:
        validated_output = contract.validate_output(raw_response_text)
        val_ms = round((time.perf_counter() - t1) * 1000.0, 3)
    except PromptContractError as exc:
        val_ms = round((time.perf_counter() - t1) * 1000.0, 3)
        exec_meta = build_execution_metadata(
            contract,
            rendered,
            model_alias=config.model_alias,
            dataset_revision=config.dataset_revision,
            input_valid=True,
            output_valid=False,
            render_duration_ms=render_ms,
            validation_duration_ms=val_ms,
            generation_options=generation_options,
        )
        meta_dict = exec_meta.to_dict()
        meta_dict["error"] = exc.to_dict()
        return EvaluationBridgeResult(
            passed_validation=False,
            output=None,
            rendered_prompt=rendered,
            gateway_request=gateway_req,
            safe_metadata=meta_dict,
            cache_key=cache_key,
            error_code=exc.code,
            error_message=exc.safe_message,
        )

    exec_meta = build_execution_metadata(
        contract,
        rendered,
        model_alias=config.model_alias,
        dataset_revision=config.dataset_revision,
        input_valid=True,
        output_valid=True,
        render_duration_ms=render_ms,
        validation_duration_ms=val_ms,
        generation_options=generation_options,
    )
    return EvaluationBridgeResult(
        passed_validation=True,
        output=validated_output,
        rendered_prompt=rendered,
        gateway_request=gateway_req,
        safe_metadata=exec_meta.to_dict(),
        cache_key=cache_key,
    )
