"""Synthetic consumer-style fixture round trips and rollback drills.
These fixtures do not establish real application migration or AC-29 acceptance.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from llm_gateway_sdk import GatewaySettings, create_client

from prompt_contracts import (
    ContractRef,
    InputValidationError,
    OutputValidationError,
    PromptRegistry,
)
from prompt_contracts.adapters.gateway import (
    GatewayCapabilities,
    build_execution_metadata,
    to_gateway_request,
    validate_gateway_response,
)


@pytest.mark.parametrize(
    "consumer_folder",
    ["ace_your_interview", "job_hunting_assistant"],
)
def test_synthetic_consumer_fixture_validation_and_rollback_drill(
    repo_root: Path, consumer_folder: str
) -> None:
    fixture_dir = repo_root / "tests" / "fixtures" / "consumers" / consumer_folder
    baseline = json.loads((fixture_dir / "baseline.json").read_text(encoding="utf-8"))
    assert baseline["fixture_kind"] == "synthetic_design_example"
    registry = PromptRegistry.from_directory(
        fixture_dir / "contracts",
        lock_file=fixture_dir / "contracts.lock.json",
    )
    registry.freeze()

    name = str(baseline["contract_name"])
    v_active = str(baseline["active_version"])
    v_canary = str(baseline["canary_version"])
    inputs: dict[str, Any] = baseline["inputs"]

    # 1. Active version (1.0.0) message-level parity against the hand-authored synthetic fixture
    contract_v1 = registry.get(ContractRef(name, v_active))
    rendered_v1 = contract_v1.render(inputs)
    assert rendered_v1.to_messages_list() == baseline["expected_messages_v1"]

    # 2. Pre-request input validation failure causes zero gateway transport calls (AC-03)
    transport_calls: list[dict[str, Any]] = []

    def _mock_gateway(request: httpx.Request) -> httpx.Response:
        transport_calls.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            status_code=200,
            headers={"x-request-id": "req-consumer-001"},
            json={
                "id": "chatcmpl-consumer-001",
                "object": "chat.completion",
                "created": 1763120000,
                "model": "gpt-4o-mini-2024-07-18",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": baseline["valid_output"],
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 80,
                    "completion_tokens": 30,
                    "total_tokens": 110,
                },
            },
        )

    with pytest.raises(InputValidationError):
        contract_v1.render({})
    assert len(transport_calls) == 0

    # 3. Full round-trip over llm-gateway-sdk + MockTransport
    gw_req = to_gateway_request(
        rendered_v1,
        contract=contract_v1,
        capabilities=GatewayCapabilities.strict_json_schema(),
    )
    settings = GatewaySettings(
        base_url="https://gateway.example.internal/v1",
        api_key="sk-synthetic-consumer-key",
    )
    with httpx.Client(transport=httpx.MockTransport(_mock_gateway)) as http_client:
        client = create_client(settings, http_client=http_client)
        response = client.complete(model="structured-output", **gw_req.to_kwargs())

    assert len(transport_calls) == 1
    validated = validate_gateway_response(contract_v1, response)
    assert validated == json.loads(baseline["valid_output"])

    meta = build_execution_metadata(
        contract_v1,
        rendered_v1,
        response=response,
        model_alias="structured-output",
        output_valid=True,
    )
    assert meta.contract_ref == f"{name}@{v_active}"
    assert meta.bundle_digest == contract_v1.bundle_digest

    # 4. Output validation failure before downstream persistence
    with pytest.raises(OutputValidationError):
        contract_v1.validate_output('{"invalid_field": "rejected"}')

    # 5. Rollback drill (T23): switch version pin 1.0.0 -> 1.1.0 -> 1.0.0 via config only
    contract_canary = registry.get(ContractRef(name, v_canary))
    assert contract_canary.bundle_digest != contract_v1.bundle_digest
    rendered_canary = contract_canary.render(inputs)
    assert rendered_canary.to_messages_list() != rendered_v1.to_messages_list()

    rolled_back = registry.get(ContractRef(name, v_active))
    assert rolled_back.bundle_digest == contract_v1.bundle_digest
    assert rolled_back.render(inputs).to_messages_list() == baseline["expected_messages_v1"]
