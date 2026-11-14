"""Unit tests for ExecutionMetadata construction, redaction, and serialization (T30)."""

from __future__ import annotations

import pytest

from prompt_contracts.errors import InputValidationError, PromptContractError
from prompt_contracts.types import ExecutionMetadata


def test_execution_metadata_serialization_and_privacy() -> None:
    meta = ExecutionMetadata(
        contract_name="career.application-answer",
        contract_version="1.0.0",
        bundle_digest="sha256:" + ("b" * 64),
        policy_id="pc-policy-v1:1234567890abcdef",
        library_version="0.2.0",
        model_alias="structured-output",
        served_model="gpt-4.1-mini",
        generation_options={"temperature": 0.2, "max_tokens": 512},
        output_valid=True,
    )
    payload = meta.to_dict()
    assert payload["contract_name"] == "career.application-answer"
    assert payload["contract_version"] == "1.0.0"
    assert payload["bundle_digest"] == "sha256:" + ("b" * 64)
    assert payload["generation_options"] == {"max_tokens": 512, "temperature": 0.2}
    for forbidden in ("messages", "inputs", "raw_output", "parsed_output", "api_key"):
        assert forbidden not in payload


@pytest.mark.parametrize(
    "bad_key",
    [
        "api_key",
        "authorization",
        "messages",
        "inputs",
        "raw_output",
        "parsed_output",
        "secret_token",
        "password",
    ],
)
def test_execution_metadata_rejects_sensitive_or_raw_content_keys(bad_key: str) -> None:
    with pytest.raises((InputValidationError, PromptContractError)):
        ExecutionMetadata(
            contract_name="career.application-answer",
            contract_version="1.0.0",
            bundle_digest="sha256:" + ("b" * 64),
            policy_id="pc-policy-v1:1234567890abcdef",
            library_version="0.2.0",
            generation_options={bad_key: "SYNTHETIC_SECRET_MARKER_001"},
        )
