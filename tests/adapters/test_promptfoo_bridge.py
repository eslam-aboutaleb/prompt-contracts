"""Tests for Promptfoo production-renderer evaluation bridge and cache key parity (T28, AC-21)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_contracts import ContractRef, PromptRegistry
from prompt_contracts.adapters.promptfoo import (
    EvaluationBridgeConfig,
    compute_evaluation_cache_key,
    execute_promptfoo_case,
)


def test_promptfoo_bridge_renders_identical_messages_and_cache_key(
    examples_dir: Path,
) -> None:
    registry = PromptRegistry.from_directory(
        root=examples_dir,
        lock_file="contracts.lock.json",
    )
    contract = registry.get(ContractRef("career.application-answer", "1.0.0"))
    vars_payload = {
        "question": "How did you handle {{injected_var}}?",
        "verified_facts": "fact-1: Built single-pass renderer.",
    }
    direct_rendered = contract.render(vars_payload)

    cfg = EvaluationBridgeConfig(
        contracts_root=examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
        contract_ref=ContractRef("career.application-answer", "1.0.0"),
        mode="offline",
    )
    result = execute_promptfoo_case(
        config=cfg,
        context_vars={
            **vars_payload,
            "_mock_response": json.dumps(
                {
                    "answer": "Single-pass rendering prevented evaluation.",
                    "evidence_ids": ["fact-1"],
                    "needs_review": False,
                }
            ),
        },
    )
    assert result.passed_validation is True
    assert result.rendered_prompt is not None
    assert result.rendered_prompt.to_messages_list() == direct_rendered.to_messages_list()

    resp = result.to_promptfoo_response()
    assert "error" not in resp
    assert resp["metadata"]["bundle_digest"] == contract.bundle_digest
    assert "rendered_messages" not in resp["metadata"]
    assert "gateway_kwargs" not in resp["metadata"]
    assert "{{injected_var}}" not in json.dumps(resp["metadata"])
    assert (
        result.to_promptfoo_response(include_rendered_prompt=True)["metadata"]["rendered_messages"]
        == direct_rendered.to_messages_list()
    )

    # Changing bundle digest changes cache key
    k1 = compute_evaluation_cache_key(
        bundle_digest=contract.bundle_digest,
        dataset_revision="v1",
        model_alias="offline",
        schema_mode="strict_json_schema",
        policy_id=contract.policy.policy_id,
    )
    k2 = compute_evaluation_cache_key(
        bundle_digest="sha256:" + ("0" * 64),
        dataset_revision="v1",
        model_alias="offline",
        schema_mode="strict_json_schema",
        policy_id=contract.policy.policy_id,
    )
    assert k1 != k2


def test_promptfoo_bridge_returns_error_on_invalid_input_or_output(
    examples_dir: Path,
) -> None:
    cfg = EvaluationBridgeConfig(
        contracts_root=examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
        contract_ref=ContractRef("career.application-answer", "1.0.0"),
        mode="offline",
    )
    bad_in_res = execute_promptfoo_case(
        config=cfg,
        context_vars={"question": "Missing verified_facts"},
    )
    assert bad_in_res.passed_validation is False
    assert "error" in bad_in_res.to_promptfoo_response()

    bad_out_res = execute_promptfoo_case(
        config=cfg,
        context_vars={
            "question": "Valid question?",
            "verified_facts": "fact-1: Valid fact.",
            "_mock_response": '{"invalid_schema": true}',
        },
    )
    assert bad_out_res.passed_validation is False
    assert "error" in bad_out_res.to_promptfoo_response()


@pytest.mark.parametrize("event", ["pull_request", "pull_request_target"])
def test_live_evaluation_cannot_invoke_responder_on_pull_requests(
    examples_dir: Path, monkeypatch: pytest.MonkeyPatch, event: str
) -> None:
    from prompt_contracts import PromptContractError

    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("PROMPT_CONTRACTS_ALLOW_LIVE_EVAL", "true")
    config = EvaluationBridgeConfig(
        contracts_root=examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
        contract_ref=ContractRef("career.application-answer", "1.0.0"),
        mode="live",
    )
    calls = []

    def responder(*args: object) -> str:
        calls.append(args)
        return "{}"

    with pytest.raises(PromptContractError):
        execute_promptfoo_case(config=config, context_vars={}, live_responder=responder)
    assert calls == []


def test_underscore_prefixed_unknown_input_is_validated(examples_dir: Path) -> None:
    config = EvaluationBridgeConfig(
        contracts_root=examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
        contract_ref=ContractRef("career.application-answer", "1.0.0"),
    )
    result = execute_promptfoo_case(
        config=config,
        context_vars={
            "question": "Q?",
            "verified_facts": "Fact",
            "_unknown": "sensitive",
            "_mock_response": "{}",
        },
    )
    assert not result.passed_validation
    assert result.error_code == "PC_INPUT_SCHEMA_VIOLATION"
    assert "sensitive" not in json.dumps(result.safe_metadata)
