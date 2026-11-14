"""Unit tests for exception hierarchy, structured error serialization, and chaining
suppression (T04).
"""

from __future__ import annotations

import json

from prompt_contracts.errors import (
    ContractIdentityConflict,
    ErrorCode,
    IncompleteCompletionError,
    InputValidationError,
    LockMismatchError,
    ManifestError,
    OutputValidationError,
    PathPolicyError,
    PromptContractError,
    ProviderCapabilityError,
    ResourceLimitError,
    TemplateSyntaxError,
    UnsupportedFormatError,
    UnsupportedSchemaError,
    ValidationIssue,
)


def test_all_domain_exceptions_inherit_from_prompt_contract_error() -> None:
    subclasses = [
        ManifestError,
        UnsupportedFormatError,
        UnsupportedSchemaError,
        PathPolicyError,
        ContractIdentityConflict,
        LockMismatchError,
        InputValidationError,
        TemplateSyntaxError,
        OutputValidationError,
        IncompleteCompletionError,
        ProviderCapabilityError,
        ResourceLimitError,
    ]
    for cls in subclasses:
        err = cls("Test error message")
        assert isinstance(err, PromptContractError)
        assert err.__suppress_context__ is True
        assert err.__cause__ is None
        payload = err.to_dict()
        assert payload["error_type"] == cls.__name__
        assert payload["code"] == str(err.code)
        assert payload["message"] == "Test error message"
        parsed = json.loads(err.to_json())
        assert parsed == payload


def test_validation_issue_structure_and_forbidden_value_keys() -> None:
    issue = ValidationIssue(
        code="minLength",
        message="String length is less than minimum allowed (1)",
        data_path="$.question",
        schema_path="$.properties.question.minLength",
    )
    data = issue.to_dict()
    assert data == {
        "code": "minLength",
        "data_path": "$.question",
        "message": "String length is less than minimum allowed (1)",
        "schema_path": "$.properties.question.minLength",
    }
    for forbidden_key in ("instance", "value", "raw_input", "raw_output", "content"):
        assert forbidden_key not in data

    err = InputValidationError(
        "Input validation failed",
        code=ErrorCode.INPUT_SCHEMA_VIOLATION,
        contract_ref="demo.test@1.0.0",
        issues=(issue,),
    )
    assert len(err.issues) == 1
    assert err.to_dict()["issues"] == [data]
    assert "demo.test@1.0.0" in repr(err)
