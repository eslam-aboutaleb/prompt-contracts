"""Single-pass lexer/parser for the ``placeholders-v1`` template grammar.

Grammar and precedence rules (left-to-right):
1. ``{{{{`` -> literal ``{{`` (4 characters consumed).
2. ``}}}}`` -> literal ``}}`` (4 characters consumed).
3. ``{{``   -> variable placeholder ``{{ <identifier> }}`` where ``<identifier>``
   matches ``^[a-zA-Z_][a-zA-Z0-9_]*$`` optionally surrounded by ASCII spaces or tabs.
   Any expression, attribute access, indexing, filter, newline, nested brace, or unclosed
   ``{{`` raises :class:`TemplateSyntaxError` with 1-based ``(line, column)``.
4. ``}}``   -> unmatched closing double-brace; raises :class:`TemplateSyntaxError` with
   1-based ``(line, column)``.
5. Lone ``{`` or ``}`` (not adjacent to a second identical brace) -> literal character.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from prompt_contracts.errors import ErrorCode, ManifestError, TemplateSyntaxError
from prompt_contracts.types import IDENTIFIER_RE, MessageTemplate, TemplateToken, TokenKind

__all__ = [
    "SUPPORTED_RENDERER_ID",
    "parse_template",
    "validate_template_variables_against_schema",
]

SUPPORTED_RENDERER_ID = "placeholders-v1"


def parse_template(
    source: str,
    *,
    source_path: str | None = None,
    contract_ref: str | None = None,
) -> tuple[TemplateToken, ...]:
    """Compile ``source`` into an immutable sequence of :class:`TemplateToken` objects."""
    if type(source) is not str:
        raise TemplateSyntaxError(
            "Template source must be a string",
            code=ErrorCode.TEMPLATE_SYNTAX_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    tokens: list[TemplateToken] = []
    literal_buf: list[str] = []
    lit_start_line = 1
    lit_start_col = 1

    line = 1
    col = 1
    n = len(source)
    i = 0

    def _flush_literal() -> None:
        if literal_buf:
            tokens.append(
                TemplateToken(
                    kind=TokenKind.LITERAL,
                    value="".join(literal_buf),
                    line=lit_start_line,
                    column=lit_start_col,
                )
            )
            literal_buf.clear()

    def _append_literal(text: str, start_line: int, start_col: int) -> None:
        nonlocal lit_start_line, lit_start_col
        if not literal_buf:
            lit_start_line = start_line
            lit_start_col = start_col
        literal_buf.append(text)

    def _advance(count: int) -> None:
        nonlocal i, line, col
        chunk = source[i : i + count]
        i += count
        nl_count = chunk.count("\n")
        if nl_count > 0:
            line += nl_count
            col = count - chunk.rfind("\n")
        else:
            col += count

    while i < n:
        if source.startswith("{{{{", i):
            _append_literal("{{", line, col)
            _advance(4)
            continue

        if source.startswith("}}}}", i):
            _append_literal("}}", line, col)
            _advance(4)
            continue

        if source.startswith("{{", i):
            tok_line = line
            tok_col = col
            close_idx = source.find("}}", i + 2)
            if close_idx == -1:
                raise TemplateSyntaxError(
                    "Unclosed '{{' placeholder delimiter in template",
                    code=ErrorCode.TEMPLATE_SYNTAX_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                    line=tok_line,
                    column=tok_col,
                )
            inner = source[i + 2 : close_idx]
            if "\n" in inner or "\r" in inner:
                raise TemplateSyntaxError(
                    "Multi-line placeholder expression is not permitted",
                    code=ErrorCode.TEMPLATE_SYNTAX_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                    line=tok_line,
                    column=tok_col,
                )
            if "{" in inner or "}" in inner:
                raise TemplateSyntaxError(
                    "Nested or malformed brace inside '{{...}}'; "
                    "use '{{{{' or '}}}}' for literal double braces",
                    code=ErrorCode.TEMPLATE_SYNTAX_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                    line=tok_line,
                    column=tok_col,
                )
            stripped_inner = inner.strip(" \t")
            if not stripped_inner:
                raise TemplateSyntaxError(
                    "Empty placeholder '{{}}' is not permitted",
                    code=ErrorCode.TEMPLATE_SYNTAX_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                    line=tok_line,
                    column=tok_col,
                )
            if not IDENTIFIER_RE.fullmatch(stripped_inner):
                raise TemplateSyntaxError(
                    "Placeholder must be a simple ASCII variable identifier "
                    "(expressions, filters, attributes, and indexing are unsupported)",
                    code=ErrorCode.TEMPLATE_SYNTAX_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                    line=tok_line,
                    column=tok_col,
                )
            _flush_literal()
            tokens.append(
                TemplateToken(
                    kind=TokenKind.VARIABLE,
                    value=stripped_inner,
                    line=tok_line,
                    column=tok_col,
                )
            )
            _advance((close_idx + 2) - i)
            continue

        if source.startswith("}}", i):
            raise TemplateSyntaxError(
                "Unmatched closing '}}' delimiter in template; use '}}}}' for literal '}}'",
                code=ErrorCode.TEMPLATE_SYNTAX_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
                line=line,
                column=col,
            )

        next_open = source.find("{{", i)
        next_close = source.find("}}", i)
        candidates = [idx for idx in (next_open, next_close) if idx != -1]
        next_delim = min(candidates) if candidates else n
        step = max(1, next_delim - i)
        _append_literal(source[i : i + step], line, col)
        _advance(step)

    _flush_literal()
    return tuple(tokens)


def validate_template_variables_against_schema(
    templates: Sequence[MessageTemplate],
    input_schema: Mapping[str, Any],
    *,
    contract_ref: str | None = None,
) -> None:
    """Ensure every placeholder variable in ``templates`` is a declared, required top-level input
    property.
    """
    properties = input_schema.get("properties")
    if not isinstance(properties, Mapping):
        raise ManifestError(
            "Input schema must declare a top-level 'properties' object",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
        )
    raw_required = input_schema.get("required", ())
    required_set = set(raw_required) if isinstance(raw_required, (list, tuple)) else set()

    for tmpl in templates:
        for tok in tmpl.tokens:
            if tok.kind != TokenKind.VARIABLE:
                continue
            var_name = tok.value
            if var_name not in properties:
                raise ManifestError(
                    f"Template placeholder '{var_name}' is not declared in input_schema properties",
                    code=ErrorCode.TEMPLATE_UNDECLARED_VARIABLE,
                    contract_ref=contract_ref,
                    source_path=tmpl.file,
                    line=tok.line,
                    column=tok.column,
                )
            if var_name not in required_set:
                raise ManifestError(
                    f"Template placeholder '{var_name}' must be listed in input_schema 'required'",
                    code=ErrorCode.TEMPLATE_OPTIONAL_VARIABLE,
                    contract_ref=contract_ref,
                    source_path=tmpl.file,
                    line=tok.line,
                    column=tok.column,
                )
