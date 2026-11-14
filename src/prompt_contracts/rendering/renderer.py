"""Single-pass, opaque-value template renderer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from prompt_contracts.errors import ErrorCode, InputValidationError, ResourceLimitError
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    ContractRef,
    MessageTemplate,
    RenderedMessage,
    RenderedPrompt,
    RuntimePolicy,
    TokenKind,
    serialize_compact_json,
)

__all__ = [
    "format_input_value",
    "render_message_template",
    "render_prompt_messages",
]


def format_input_value(
    value: Any,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> str:
    """Format a validated JSON value for single-pass template insertion.

    Strings render verbatim after UTF-8 verification. Non-string JSON values render as
    compact, sorted-key UTF-8 JSON with no whitespace separators.
    """
    if type(value) is str:
        try:
            value.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            raise InputValidationError(
                "Input string contains invalid UTF-8 surrogates",
                code=ErrorCode.INPUT_VALUE_INVALID,
            ) from None
        return value
    return serialize_compact_json(value, max_depth=policy.max_nesting_depth)


def render_message_template(
    template: MessageTemplate,
    validated_inputs: Mapping[str, Any],
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    contract_ref: str | None = None,
) -> RenderedMessage:
    """Render a single :class:`MessageTemplate` in one pass without scanning or re-evaluating
    inserted data.
    """
    parts: list[str] = []
    total_bytes = 0
    for token in template.tokens:
        if token.kind == TokenKind.LITERAL:
            part = token.value
        elif token.kind == TokenKind.VARIABLE:
            if token.value not in validated_inputs:
                raise InputValidationError(
                    f"Missing required template input '{token.value}'",
                    code=ErrorCode.INPUT_SCHEMA_VIOLATION,
                    contract_ref=contract_ref,
                    source_path=template.file,
                    line=token.line,
                    column=token.column,
                )
            part = format_input_value(validated_inputs[token.value], policy=policy)
        else:
            continue
        total_bytes += len(part.encode("utf-8"))
        if total_bytes > policy.max_rendered_bytes:
            raise ResourceLimitError(
                f"Rendered message exceeds limit ({policy.max_rendered_bytes} bytes)",
                code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
                contract_ref=contract_ref,
                source_path=template.file,
                line=token.line,
                column=token.column,
            )
        parts.append(part)
    return RenderedMessage(role=template.role, content="".join(parts))


def render_prompt_messages(
    *,
    contract_ref: ContractRef,
    bundle_digest: str,
    renderer: str,
    templates: Sequence[MessageTemplate],
    validated_inputs: Mapping[str, Any],
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> RenderedPrompt:
    """Render all templates in order and enforce total UTF-8 output byte bounds."""
    rendered_messages: list[RenderedMessage] = []
    total_bytes = 0
    ref_str = str(contract_ref)

    for tmpl in templates:
        msg = render_message_template(
            tmpl,
            validated_inputs,
            policy=policy,
            contract_ref=ref_str,
        )
        msg_bytes = len(msg.content.encode("utf-8"))
        total_bytes += msg_bytes
        if total_bytes > policy.max_rendered_bytes:
            raise ResourceLimitError(
                f"Rendered messages size ({total_bytes} bytes) "
                f"exceeds limit ({policy.max_rendered_bytes} bytes)",
                code=ErrorCode.RESOURCE_SIZE_EXCEEDED,
                contract_ref=ref_str,
            )
        rendered_messages.append(msg)

    return RenderedPrompt(
        contract_ref=contract_ref,
        bundle_digest=bundle_digest,
        renderer=renderer,
        policy_id=policy.policy_id,
        messages=tuple(rendered_messages),
    )
