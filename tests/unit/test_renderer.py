"""Unit tests for placeholders-v1 template parser and single-pass renderer (T07)."""

from __future__ import annotations

import pytest

from prompt_contracts.errors import (
    ErrorCode,
    ManifestError,
    TemplateSyntaxError,
)
from prompt_contracts.rendering.parser import (
    parse_template,
    validate_template_variables_against_schema,
)
from prompt_contracts.rendering.renderer import render_message_template
from prompt_contracts.types import MessageRole, MessageTemplate


def _compile_msg(raw: str) -> MessageTemplate:
    tokens = parse_template(raw, source_path="user.md")
    return MessageTemplate(
        role=MessageRole.USER,
        file="user.md",
        raw_text=raw,
        tokens=tokens,
    )


def test_parse_and_render_escapes_and_lone_braces() -> None:
    raw = 'JSON example: {"a": 1}\nLiteral braces: {{{{escaped}}}}\nValue: {{user_input}}'
    tmpl = _compile_msg(raw)
    assert tmpl.referenced_variables == ("user_input",)
    msg = render_message_template(tmpl, {"user_input": "hello {{injected_var}} {{{{raw}}}}"})
    assert msg.content == (
        'JSON example: {"a": 1}\n'
        "Literal braces: {{escaped}}\n"
        "Value: hello {{injected_var}} {{{{raw}}}}"
    )


def test_renderer_serializes_non_string_values_as_compact_sorted_json() -> None:
    tmpl = _compile_msg("Payload: {{meta}} Flag: {{active}}")
    msg = render_message_template(tmpl, {"meta": {"z": 1, "a": [True, None]}, "active": False})
    assert msg.content == 'Payload: {"a":[true,null],"z":1} Flag: false'


@pytest.mark.parametrize(
    "bad_template",
    [
        "Unclosed {{variable",
        "Unmatched closing }} brace",
        "Empty {{   }} placeholder",
        "Expression {{user.name}} not allowed",
        "Filter {{user | upper}} not allowed",
        "Index {{items[0]}} not allowed",
        "Nested {{a {{b}}}} braces",
    ],
)
def test_parser_rejects_invalid_placeholder_syntax_with_location(
    bad_template: str,
) -> None:
    with pytest.raises(TemplateSyntaxError) as exc_info:
        parse_template(bad_template, source_path="user.md")
    assert exc_info.value.line is not None
    assert exc_info.value.column is not None


def test_verify_placeholders_requires_declared_and_required_top_level_properties() -> None:
    tmpl = _compile_msg("Question: {{question}} Context: {{context}}")
    schema_missing = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["question"],
        "properties": {
            "question": {"type": "string"},
            "context": {"type": "string"},
        },
    }
    with pytest.raises(ManifestError) as exc_info:
        validate_template_variables_against_schema((tmpl,), schema_missing)
    assert exc_info.value.code == ErrorCode.TEMPLATE_OPTIONAL_VARIABLE

    schema_undeclared = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["question"],
        "properties": {"question": {"type": "string"}},
    }
    with pytest.raises(ManifestError) as exc_info2:
        validate_template_variables_against_schema((tmpl,), schema_undeclared)
    assert exc_info2.value.code == ErrorCode.TEMPLATE_UNDECLARED_VARIABLE


def test_renderer_stops_before_expanding_remaining_tokens_past_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from prompt_contracts.errors import ResourceLimitError
    from prompt_contracts.types import RuntimePolicy

    calls = 0

    def counted_format(value: object, *, policy: RuntimePolicy) -> str:
        nonlocal calls
        calls += 1
        return "é" * 4

    monkeypatch.setattr("prompt_contracts.rendering.renderer.format_input_value", counted_format)
    with pytest.raises(ResourceLimitError) as exc_info:
        render_message_template(
            _compile_msg("{{value}}" * 1000),
            {"value": "test"},
            policy=RuntimePolicy(max_rendered_bytes=10),
        )
    assert calls == 2
    assert exc_info.value.code == ErrorCode.RESOURCE_SIZE_EXCEEDED
