# Contract Format (`format_version = 1`)

Each contract version lives in its own immutable bundle directory:

```text
contracts/
  career.application-answer/
    1.0.0/
      contract.toml
      system.md
      user.md
      input.schema.json
      output.schema.json
```

## `contract.toml` Manifest

```toml
format_version = 1
name = "career.application-answer"
version = "1.0.0"
description = "Draft an answer using candidate-provided evidence."
renderer = "placeholders-v1"
input_schema = "input.schema.json"

[output]
mode = "json"
schema = "output.schema.json"

[[messages]]
role = "system"
file = "system.md"

[[messages]]
role = "user"
file = "user.md"
```

### Naming & Versioning Grammar

- **`name`**: Lowercase ASCII letters and digits separated by single dots or hyphens, matching `^[a-z0-9]+(?:[.-][a-z0-9]+)*$`, at most 128 characters. Underscores, empty segments, and leading/trailing punctuation are rejected.
- **`version`**: Strict `MAJOR.MINOR.PATCH` (`^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$`).
- **`ContractRef`**: Canonical `<name>@<version>` reference (for example, `career.application-answer@1.0.0`).

### Asset Closure & Path Confinement

- Every file inside a contract bundle directory must be explicitly referenced by `contract.toml` (`contract.toml`, `input_schema`, `output.schema` when `mode = "json"`, and each `messages[].file`).
- Any unreferenced file, symlink, parent traversal (`..`), absolute path, Windows reserved name, or case-folding collision raises `PathPolicyError`.

## Supported JSON Schema Profile

Both `input.schema.json` and `output.schema.json` use Draft 2020-12 semantics. If present, `$schema` must be `https://json-schema.org/draft/2020-12/schema`. Only this deterministic keyword profile is supported:

- `$schema`, `title`, `description`, `$defs`, `$ref` (local `#/$defs/<Name>` only)
- `type`, `enum`, `const`
- `properties`, `required`, `additionalProperties` (boolean only; the input root requires `false`)
- `items`, `minItems`, `maxItems`
- `minLength`, `maxLength`
- `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`

The input root must be an object with explicit `properties` and `additionalProperties: false`. Every template variable must name a required top-level property. `$defs` is root-only; references must name one root definition and may carry only `title`/`description` siblings. Boolean schemas, remote references, cycles, and unsupported keywords fail at load time.

For text output, replace the output table with:

```toml
[output]
mode = "text"
min_length = 1
max_length = 6000
```

Lengths count Unicode code points. Response byte ceilings apply independently. JSON mode requires `schema` and forbids text length fields; text mode requires both length bounds and forbids `schema`. The reference editor schemas validate the document shape; the runtime additionally enforces portable paths, asset closure, ordered length bounds, uniqueness, and resource policy.
