"""Tests for gateway response validation and sync/async llm-gateway-sdk integration (T17,
AC-03, AC-19).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from llm_gateway_sdk import GatewaySettings, create_async_client, create_client

from prompt_contracts import (
    ErrorCode,
    IncompleteCompletionError,
    InputValidationError,
    PromptRegistry,
)
from prompt_contracts.adapters.gateway import (
    GatewayCapabilities,
    build_execution_metadata,
    to_gateway_request,
    validate_gateway_response,
)


def test_unknown_finish_reason_does_not_leak_provider_content(examples_dir: Path) -> None:
    contract = PromptRegistry.from_directory(examples_dir, lock_file="contracts.lock.json").get(
        "career.application-answer@1.0.0"
    )
    with pytest.raises(IncompleteCompletionError) as caught:
        validate_gateway_response(
            contract,
            {
                "choices": [
                    {"finish_reason": "SYNTHETIC_SECRET_REASON", "message": {"content": "{}"}}
                ]
            },
        )
    assert "SYNTHETIC_SECRET_REASON" not in caught.value.to_json()
    assert "SYNTHETIC_SECRET_REASON" not in repr(caught.value)


def test_sync_and_async_llm_gateway_sdk_roundtrip_and_zero_calls_on_bad_input(
    examples_dir: Path,
) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")
    valid_inputs = json.loads(
        (examples_dir / "inputs" / "application-answer.json").read_text(encoding="utf-8")
    )

    transport_calls: list[dict[str, Any]] = []

    def _mock_handler(request: httpx.Request) -> httpx.Response:
        transport_calls.append(json.loads(request.content.decode("utf-8")))
        return httpx.Response(
            200,
            headers={"x-request-id": "req-sync-async-1"},
            json={
                "id": "chatcmpl-sync-1",
                "object": "chat.completion",
                "created": 1700000000,
                "model": "gpt-4.1-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "answer": "Grounded production experience.",
                                    "evidence_ids": ["fact-1"],
                                    "needs_review": False,
                                }
                            ),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 50,
                    "completion_tokens": 15,
                    "total_tokens": 65,
                },
            },
        )

    # AC-03: Missing input fails pre-request with zero transport calls
    with pytest.raises(InputValidationError):
        contract.render({"question": "Missing verified_facts"})
    assert len(transport_calls) == 0

    # Sync GatewayClient roundtrip
    rendered = contract.render(valid_inputs)
    gateway_req = to_gateway_request(
        rendered,
        contract=contract,
        capabilities=GatewayCapabilities.strict_json_schema(),
    )
    settings = GatewaySettings(
        base_url="https://gateway.internal.example/v1",
        api_key="test-token",
    )
    with httpx.Client(transport=httpx.MockTransport(_mock_handler)) as http_client:
        client = create_client(settings, http_client=http_client)
        response = client.complete(
            model="gpt-4.1-mini",
            **gateway_req.to_kwargs(),
        )

    assert len(transport_calls) == 1
    parsed = validate_gateway_response(contract, response)
    assert parsed == {
        "answer": "Grounded production experience.",
        "evidence_ids": ["fact-1"],
        "needs_review": False,
    }
    meta = build_execution_metadata(
        contract,
        rendered,
        response=response,
        model_alias="gpt-4.1-mini",
        generation_options={"temperature": 0.0},
        output_valid=True,
    )
    assert meta.bundle_digest == contract.bundle_digest

    # AsyncGatewayClient roundtrip
    async def _run_async() -> dict[str, Any]:
        async_transport = httpx.MockTransport(_mock_handler)
        async with httpx.AsyncClient(transport=async_transport) as async_http:
            async_client = create_async_client(settings, http_client=async_http)
            async_resp = await async_client.complete(
                model="gpt-4.1-mini",
                **gateway_req.to_kwargs(),
            )
        res: dict[str, Any] = validate_gateway_response(contract, async_resp)
        return res

    async_parsed = asyncio.run(_run_async())
    assert async_parsed["needs_review"] is False
    assert len(transport_calls) == 2


@pytest.mark.parametrize(
    "response_payload,expected_code",
    [
        ({"choices": []}, ErrorCode.COMPLETION_CHOICE_COUNT),
        (
            {
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "{}"}},
                    {"finish_reason": "stop", "message": {"content": "{}"}},
                ]
            },
            ErrorCode.COMPLETION_CHOICE_COUNT,
        ),
        (
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"answer": "SYNTHETIC_SECRET_TRUNCATED'},
                    }
                ]
            },
            ErrorCode.COMPLETION_TRUNCATED,
        ),
        (
            {
                "choices": [
                    {
                        "finish_reason": "content_filter",
                        "message": {"content": ""},
                    }
                ]
            },
            ErrorCode.COMPLETION_REFUSED_OR_FILTERED,
        ),
        (
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": None,
                            "refusal": "SYNTHETIC_SECRET_REFUSAL_REASON",
                        },
                    }
                ]
            },
            ErrorCode.COMPLETION_REFUSED_OR_FILTERED,
        ),
        (
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [{"id": "call_1"}],
                        },
                    }
                ]
            },
            ErrorCode.COMPLETION_UNEXPECTED_TOOL_CALL,
        ),
        (
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": ""},
                    }
                ]
            },
            ErrorCode.COMPLETION_EMPTY_CONTENT,
        ),
    ],
)
def test_validate_gateway_response_distinguishes_non_valid_completion_states(
    examples_dir: Path,
    response_payload: dict[str, Any],
    expected_code: str,
) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")
    with pytest.raises(IncompleteCompletionError) as exc_info:
        validate_gateway_response(contract, response_payload)
    assert exc_info.value.code == expected_code
    assert "SYNTHETIC_SECRET" not in str(exc_info.value)
