# Single-Pass Rendering (`placeholders-v1`)

`prompt-contracts` uses a minimal, deterministic template engine (`placeholders-v1`) rather than a general-purpose code-execution template engine.

## Lexer Rules (Left-to-Right)

1. `{{{{` renders as literal `{{`.
2. `}}}}` renders as literal `}}`.
3. `{{ variable_name }}` substitutes the validated top-level input property `variable_name` (`^[a-zA-Z_][a-zA-Z0-9_]*$`).
4. Unmatched `{{` or `}}`, nested braces, attribute access (`{{user.name}}`), indexing (`{{items[0]}}`), or filters (`{{text | upper}}`) raise `TemplateSyntaxError` with 1-based `(line, column)` coordinates.
5. Lone `{` and `}` characters (such as JSON examples in prompts) are emitted verbatim without escaping.

## Schema-Bound Placeholders

Every placeholder variable referenced across `messages` must be:

1. Declared in `input.schema.json` under top-level `properties`.
2. Listed in top-level `required`.

## Opaque Single-Pass Insertion

- String values are inserted verbatim in a single pass after UTF-8 validation.
- Non-string JSON values (`int`, `float`, `bool`, `None`, `list`, `dict`) are serialized as compact, sorted-key UTF-8 JSON (`json.dumps(..., sort_keys=True, separators=(",", ":"))`).
- Inserted data is never re-tokenized or re-rendered. If an untrusted input string contains `{{other_variable}}` or `{{{{`, those characters remain literal data in the rendered message.
