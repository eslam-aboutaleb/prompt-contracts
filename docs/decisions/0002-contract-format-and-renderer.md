# ADR-0002: Contract Format v1 and `placeholders-v1` Renderer

## Status
Accepted

## Context
General-purpose template engines (such as Jinja2, Handlebars, or Nunjucks) allow arbitrary expressions, loops, filters, and nested evaluation, creating injection and double-rendering risks when untrusted user content or literal JSON braces appear in prompts.

## Decision
Define `format_version = 1` in `contract.toml` paired with the single-pass `placeholders-v1` lexer/renderer:
- `{{{{` and `}}}}` escape literal double braces.
- `{{ variable_name }}` substitutes required top-level properties from `input.schema.json` in a single non-re-entrant pass.
- Lone `{` and `}` characters pass through verbatim.

## Consequences
Templates remain simple, auditable, and immune to second-pass template injection.
