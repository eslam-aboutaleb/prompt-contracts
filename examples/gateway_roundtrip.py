"""Offline gateway round-trip example using ``llm-gateway-sdk`` and ``httpx.MockTransport``."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from llm_gateway_sdk import GatewayClient, GatewaySettings, create_async_client

from prompt_contracts import ContractRef, PromptRegistry
from prompt_contracts.adapters.gateway import (
    GatewayCapabilities,
    build_execution_metadata,
    to_gateway_request,
    validate_gateway_response,
)


def _mock_gateway_handler(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content.decode("utf-8"))
    assert payload["model"] == "structured-output"
    assert len(payload["messages"]) == 2
    assert payload["response_format"]["type"] == "json_schema"

    response_body = {
        "id": "chatcmpl-example-001",
        "object": "chat.completion",
        "created": 1763120000,
        "model": "gpt-4o-mini-2024-07-18",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "answer": "I maintained PostgreSQL migrations.",
                            "evidence_ids": ["fact-1"],
                            "needs_review": False,
                        }
                    ),
                },
            }
        ],
        "usage": {
            "prompt_tokens": 64,
            "completion_tokens": 22,
            "total_tokens": 86,
        },
    }
    return httpx.Response(
        status_code=200,
        headers={"x-request-id": "req-offline-001", "content-type": "application/json"},
        json=response_body,
    )


async def run_async_gateway_roundtrip() -> dict[str, Any]:
    """Execute an end-to-end async SDK round-trip over an offline mock transport."""
    examples_dir = Path(__file__).resolve().parent
    registry = PromptRegistry.from_directory(
        root=examples_dir,
        lock_file="contracts.lock.json",
    )
    registry.freeze()

    contract = registry.get(ContractRef("career.application-answer", "1.0.0"))
    rendered = contract.render(
        {
            "question": "Describe your database experience.",
            "verified_facts": "fact-1: Maintained PostgreSQL migrations.",
        }
    )

    gw_request = to_gateway_request(
        rendered,
        contract=contract,
        capabilities=GatewayCapabilities.strict_json_schema(),
    )

    settings = GatewaySettings(
        base_url="https://gateway.example.internal/v1",
        api_key="sk-synthetic-offline-key",
    )
    transport = httpx.MockTransport(_mock_gateway_handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = create_async_client(settings, http_client=http_client)
        response = await client.complete(
            model="structured-output",
            **gw_request.to_kwargs(),
        )

    validated_answer = validate_gateway_response(contract, response)
    metadata = build_execution_metadata(
        contract,
        rendered,
        response=response,
        model_alias="structured-output",
        output_valid=True,
    )
    return {
        "answer": validated_answer,
        "metadata": metadata.to_dict(),
    }


def run_sync_gateway_roundtrip() -> dict[str, Any]:
    """Execute an end-to-end synchronous SDK round-trip over an offline mock transport."""
    examples_dir = Path(__file__).resolve().parent
    registry = PromptRegistry.from_directory(
        root=examples_dir,
        lock_file="contracts.lock.json",
    )
    registry.freeze()

    contract = registry.get(ContractRef("career.application-answer", "1.0.0"))
    rendered = contract.render(
        {
            "question": "Describe your database experience.",
            "verified_facts": "fact-1: Maintained PostgreSQL migrations.",
        }
    )
    gw_request = to_gateway_request(
        rendered,
        contract=contract,
        capabilities=GatewayCapabilities.strict_json_schema(),
    )

    settings = GatewaySettings(
        base_url="https://gateway.example.internal/v1",
        api_key="sk-synthetic-offline-key",
    )
    transport = httpx.MockTransport(_mock_gateway_handler)
    with httpx.Client(transport=transport) as http_client:
        from llm_gateway_sdk import create_client

        client: GatewayClient = create_client(settings, http_client=http_client)
        response = client.complete(
            model="structured-output",
            **gw_request.to_kwargs(),
        )

    validated_answer = validate_gateway_response(contract, response)
    metadata = build_execution_metadata(
        contract,
        rendered,
        response=response,
        model_alias="structured-output",
        output_valid=True,
    )
    return {
        "answer": validated_answer,
        "metadata": metadata.to_dict(),
    }


if __name__ == "__main__":
    sync_out = run_sync_gateway_roundtrip()
    async_out = asyncio.run(run_async_gateway_roundtrip())
    assert sync_out["answer"] == async_out["answer"]
    print(json.dumps(async_out, indent=2))
