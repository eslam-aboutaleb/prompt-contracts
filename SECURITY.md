# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| `0.2.x` | Yes |
| `< 0.2.0` | No |

## Security Guarantees Enforced by `prompt-contracts`

1. **Single-Pass Template Rendering (`placeholders-v1`)**: Inserted input values are never re-tokenized or re-evaluated, preventing second-pass template injection.
2. **Root-Confined Asset Loading**: Bundle loaders reject symlinks, `..` path traversal, absolute paths, Windows reserved filenames, case-folding collisions, and unreferenced files inside bundle directories.
3. **Bounded Resource Limits (`RuntimePolicy`)**: Enforces strict ceilings on manifest size, schema size, template size, expanded schema nodes, JSON nesting depth, input bytes, rendered bytes, and response bytes.
4. **Zero-Leakage Diagnostics**: Domain exceptions suppress raw exception chaining (`__suppress_context__ = True`) and omit rejected values and unknown property names from all diagnostic surfaces.

## Reporting a Vulnerability

Please report suspected security vulnerabilities privately via GitHub Security Advisories on `https://github.com/eslam-aboutaleb/prompt-contracts/security/advisories` rather than opening a public issue.
