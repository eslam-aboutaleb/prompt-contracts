"""Tests for gateway request construction and explicit capability modes (T16, AC-19, AC-20)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from prompt_contracts import (
    Contract,
    ErrorCode,
    PromptRegistry,
    ProviderCapabilityError,
)
from prompt_contracts.adapters.gateway import (
    GatewayCapabilities,
    to_gateway_request,
)


def test_to_gateway_request_strict_and_local_validation_modes(
    examples_dir: Path,
) -> None:
    registry = PromptRegistry.from_directory(
        examples_dir,
        lock_file=examples_dir / "contracts.lock.json",
    )
    contract = registry.get("career.application-answer@1.0.0")
    inputs = json.loads(
        (examples_dir / "inputs" / "application-answer.json").read_text(encoding="utf-8")
    )
    rendered = contract.render(inputs)

    strict_req = to_gateway_request(
        rendered,
        contract=contract,
        capabilities=GatewayCapabilities.strict_json_schema(),
    )
    assert strict_req.response_format is not None
    assert strict_req.response_format["type"] == "json_schema"
    assert strict_req.response_format["json_schema"]["strict"] is True
    kwargs = strict_req.to_kwargs()
    assert "messages" in kwargs
    assert "response_format" in kwargs
    assert "model" not in kwargs

    # Detached copy verification
    kwargs["messages"][0]["content"] = "mutated"
    assert strict_req.messages[0]["content"] != "mutated"

    local_req = to_gateway_request(
        rendered,
        contract=contract,
        capabilities=GatewayCapabilities.local_validation(),
    )
    assert local_req.response_format is None
    assert "response_format" not in local_req.to_kwargs()


def test_to_gateway_request_rejects_unsupported_strict_schema_without_silent_downgrade(
    examples_dir: Path, tmp_path: Path
) -> None:
    bundle_dir = tmp_path / "career.application-answer" / "1.0.0"
    shutil.copytree(
        examples_dir / "contracts" / "career.application-answer" / "1.0.0",
        bundle_dir,
    )
    # Add an optional property to output.schema.json (not in required)
    out_schema = json.loads((bundle_dir / "output.schema.json").read_text(encoding="utf-8"))
    out_schema["properties"]["optional_citation"] = {"type": "string"}
    (bundle_dir / "output.schema.json").write_text(
        json.dumps(out_schema, indent=2) + "\n", encoding="utf-8"
    )
    contract = Contract.from_directory(bundle_dir)
    inputs = json.loads(
        (examples_dir / "inputs" / "application-answer.json").read_text(encoding="utf-8")
    )
    rendered = contract.render(inputs)

    # Strict mode rejects optional object property pre-request
    with pytest.raises(ProviderCapabilityError) as exc_info:
        to_gateway_request(
            rendered,
            contract=contract,
            capabilities=GatewayCapabilities.strict_json_schema(),
        )
    assert exc_info.value.code == ErrorCode.CAPABILITY_UNSUPPORTED

    # Explicit local validation mode succeeds
    local_req = to_gateway_request(
        rendered,
        contract=contract,
        capabilities=GatewayCapabilities.local_validation(),
    )
    assert local_req.response_format is None
