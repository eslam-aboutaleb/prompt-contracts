"""Unit tests for core value types, immutability, and runtime policy validation (T04)."""

from __future__ import annotations

import pytest

from prompt_contracts.errors import (
    InputValidationError,
    ManifestError,
    PathPolicyError,
    PromptContractError,
    ResourceLimitError,
)
from prompt_contracts.types import (
    SPEC_MAX_INPUT_BYTES,
    ContractRef,
    MessageRole,
    MessageTemplate,
    OutputMode,
    OutputSpec,
    RenderedMessage,
    RenderedPrompt,
    RuntimePolicy,
    TemplateToken,
    TokenKind,
    freeze_json_value,
    serialize_compact_json,
    thaw_json_value,
    validate_logical_relative_path,
)


def test_contract_ref_parsing_and_formatting() -> None:
    ref = ContractRef.parse("career.application-answer@1.0.0")
    assert ref.name == "career.application-answer"
    assert ref.version == "1.0.0"
    assert str(ref) == "career.application-answer@1.0.0"


@pytest.mark.parametrize(
    "bad_ref",
    [
        "",
        "career.application-answer",
        "Career.Answer@1.0.0",
        "career..answer@1.0.0",
        "career.answer@v1.0.0",
        "career.answer@1.0",
        "career.answer@01.0.0",
        "career.answer@1.0.0-alpha",
    ],
)
def test_contract_ref_rejects_invalid_identifiers(bad_ref: str) -> None:
    with pytest.raises(ManifestError):
        ContractRef.parse(bad_ref)


def test_runtime_policy_defaults_and_ceiling_enforcement() -> None:
    policy = RuntimePolicy()
    assert policy.max_input_bytes == 1_048_576
    assert policy.max_rendered_bytes == 2_097_152
    assert policy.max_response_bytes == 1_048_576
    assert policy.max_nesting_depth == 32
    assert policy.max_expanded_schema_nodes == 5_000

    tighter = RuntimePolicy(max_input_bytes=4096, max_nesting_depth=8)
    assert tighter.max_input_bytes == 4096
    assert tighter.max_nesting_depth == 8

    with pytest.raises(ResourceLimitError):
        RuntimePolicy(max_input_bytes=0)

    with pytest.raises(ResourceLimitError):
        RuntimePolicy(max_input_bytes=SPEC_MAX_INPUT_BYTES + 1)


def test_freeze_and_thaw_json_value_and_compact_serialization() -> None:
    payload = {"b": [1, 2, {"nested": True}], "a": "hello", "c": None}
    frozen = freeze_json_value(payload, max_depth=8)
    with pytest.raises(TypeError):
        frozen["a"] = "mutated"

    thawed = thaw_json_value(frozen)
    assert thawed == payload
    thawed["a"] = "changed"
    assert frozen["a"] == "hello"

    compact = serialize_compact_json(payload)
    assert compact == '{"a":"hello","b":[1,2,{"nested":true}],"c":null}'


def test_freeze_json_value_rejects_non_finite_numbers_and_deep_nesting() -> None:
    with pytest.raises(InputValidationError):
        freeze_json_value({"x": float("nan")})

    with pytest.raises(InputValidationError):
        freeze_json_value({"x": float("inf")})

    with pytest.raises(ResourceLimitError):
        freeze_json_value({"a": {"b": {"c": 1}}}, max_depth=2)


def test_rendered_prompt_and_message_immutability() -> None:
    msg = RenderedMessage(role=MessageRole.USER, content="Hello world")
    prompt = RenderedPrompt(
        contract_ref=ContractRef("demo.test", "1.0.0"),
        bundle_digest="sha256:" + ("a" * 64),
        renderer="placeholders-v1",
        policy_id="pc-policy-v1:0000000000000000",
        messages=(msg,),
    )
    sdk_msgs = prompt.to_messages_list()
    assert sdk_msgs == [{"role": "user", "content": "Hello world"}]
    sdk_msgs[0]["content"] = "mutated"
    assert prompt.messages[0].content == "Hello world"


def test_template_and_output_spec_validation() -> None:
    tok = TemplateToken(kind=TokenKind.VARIABLE, value="user_name", line=1, column=1)
    tmpl = MessageTemplate(
        role=MessageRole.USER,
        file="user.md",
        raw_text="{{user_name}}",
        tokens=(tok,),
    )
    assert tmpl.role is MessageRole.USER
    assert tmpl.referenced_variables == ("user_name",)

    text_spec = OutputSpec(mode=OutputMode.TEXT, min_length=1, max_length=100)
    assert text_spec.mode is OutputMode.TEXT

    with pytest.raises(ManifestError):
        OutputSpec(mode=OutputMode.TEXT, schema_file="output.schema.json")

    with pytest.raises(ManifestError):
        OutputSpec(mode=OutputMode.JSON, schema_file=None)

    with pytest.raises(ManifestError):
        OutputSpec(mode=OutputMode.TEXT, min_length=50, max_length=10)


@pytest.mark.parametrize(
    "bad_path",
    [
        "",
        "/abs/path.md",
        "../escape.md",
        "sub/../../escape.md",
        "back\\slash.md",
        "./dot.md",
        "CON.md",
        "nul.json",
    ],
)
def test_validate_logical_relative_path_rejects_unsafe_paths(bad_path: str) -> None:
    with pytest.raises((PathPolicyError, PromptContractError)):
        validate_logical_relative_path(bad_path)


@pytest.mark.parametrize("payload", ["\ud800", {"\udfff": "value"}, {"value": "\ud800"}])
def test_json_values_reject_surrogates_in_keys_and_values(payload: object) -> None:
    with pytest.raises(InputValidationError):
        freeze_json_value(payload)


def test_json_values_reject_primitive_subclasses() -> None:
    class CustomString(str):
        pass

    class CustomInteger(int):
        pass

    class CustomFloat(float):
        pass

    for value in (CustomString("text"), CustomInteger(1), CustomFloat(1.0)):
        with pytest.raises(InputValidationError):
            freeze_json_value(value)


def test_json_byte_limit_stops_before_copying_remaining_values() -> None:
    with pytest.raises(ResourceLimitError):
        freeze_json_value(["x" * 100, object()], max_bytes=32)


@pytest.mark.parametrize("value", [None, True, False, 12, 1.25, "雪\n", [1, "a"], {"x": [1]}])
def test_json_byte_budget_matches_compact_utf8_representation(value: object) -> None:
    exact_size = len(serialize_compact_json(value).encode("utf-8"))
    assert thaw_json_value(freeze_json_value(value, max_bytes=exact_size)) == value
    with pytest.raises(ResourceLimitError):
        freeze_json_value(value, max_bytes=exact_size - 1)


def test_json_serialization_translates_integer_conversion_limit() -> None:
    import sys

    limit = sys.get_int_max_str_digits()
    if limit == 0:
        pytest.skip("Interpreter integer conversion limit is disabled")
    with pytest.raises(InputValidationError):
        serialize_compact_json({"value": 10 ** (limit + 1)})
