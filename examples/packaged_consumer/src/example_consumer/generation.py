"""Consumer generation entry point shared between production and Promptfoo evaluation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from prompt_contracts import ContractRef, PromptRegistry
from prompt_contracts.adapters.gateway import (
    GatewayCapabilities,
    build_execution_metadata,
    to_gateway_request,
)


@dataclass(frozen=True, slots=True)
class EvaluationGenerationResult:
    """Structured result returned by ``generate_for_evaluation``."""

    output: dict[str, Any]
    safe_metadata: dict[str, Any]


def load_consumer_registry() -> PromptRegistry:
    """Load and freeze the consumer's packaged contracts via ``importlib.resources``."""
    registry = PromptRegistry.from_package_resources(
        "example_consumer",
        lock_resource="contracts.lock.json",
    )
    registry.freeze()
    return registry


def generate_for_evaluation(
    *,
    inputs: Mapping[str, Any],
    contract_ref: str = "career.application-answer@1.0.0",
    mode: str = "offline",
) -> EvaluationGenerationResult:
    """Render and validate using the packaged contract snapshot."""
    if mode != "offline":
        raise RuntimeError("example_consumer only supports offline mode by default")

    registry = load_consumer_registry()
    contract = registry.get(ContractRef.parse(contract_ref))
    rendered = contract.render(inputs)
    _ = to_gateway_request(
        rendered,
        contract=contract,
        capabilities=GatewayCapabilities.strict_json_schema(),
    )

    scripted_json = json.dumps(
        {
            "answer": f"Grounded response for: {inputs['question']}",
            "evidence_ids": ["fact-1"],
            "needs_review": False,
        }
    )
    validated = contract.validate_output(scripted_json)
    meta = build_execution_metadata(
        contract,
        rendered,
        model_alias="offline-scripted",
        output_valid=True,
    )
    return EvaluationGenerationResult(
        output=validated,
        safe_metadata=meta.to_dict(),
    )
