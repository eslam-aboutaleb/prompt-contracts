"""Automated tests executing all runnable examples in examples/ (T31, AC-27)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from examples.basic_render import run_basic_example
from examples.gateway_roundtrip import (
    run_async_gateway_roundtrip,
    run_sync_gateway_roundtrip,
)
from examples.promptfoo.provider import call_api


def test_basic_render_example_executes() -> None:
    res = run_basic_example()
    assert res["contract_ref"] == "career.application-answer@1.0.0"
    assert isinstance(res["messages"], list)
    assert len(res["messages"]) == 2


def test_gateway_roundtrip_examples_execute() -> None:
    sync_res = run_sync_gateway_roundtrip()
    async_res = asyncio.run(run_async_gateway_roundtrip())
    assert sync_res["answer"] == async_res["answer"]
    assert sync_res["metadata"]["output_valid"] is True


def test_promptfoo_provider_example_executes(examples_dir: Path) -> None:
    resp = call_api(
        "__PROMPT_CONTRACTS_SENTINEL__",
        options={
            "config": {
                "contracts_root": str(examples_dir),
                "lock_file": "contracts.lock.json",
                "contract_ref": "career.application-answer@1.0.0",
                "mode": "offline",
            }
        },
        context={
            "vars": {
                "question": "Describe your database experience.",
                "verified_facts": "fact-1: Maintained PostgreSQL migrations.",
            }
        },
    )
    assert "error" not in resp
    assert "output" in resp
    assert resp["metadata"]["passed_validation"] is True
