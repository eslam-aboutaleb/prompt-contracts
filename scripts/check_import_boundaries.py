"""Verify internal module dependency direction and zero eager adapter imports."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ALLOWED_INTERNAL_DEPS: dict[str, frozenset[str]] = {
    "errors": frozenset(),
    "types": frozenset({"errors"}),
    "validation": frozenset({"types", "errors", "validation"}),
    "rendering": frozenset({"types", "errors", "validation", "rendering"}),
    "identity": frozenset({"types", "errors", "validation", "identity"}),
    "loading": frozenset(
        {"types", "errors", "validation", "rendering", "identity", "loading", "contract"}
    ),
    "contract": frozenset({"types", "errors", "validation", "rendering", "loading", "contract"}),
    "registry": frozenset(
        {"contract", "loading", "identity", "types", "errors", "registry", "validation"}
    ),
    "compatibility": frozenset(
        {
            "contract",
            "validation",
            "rendering",
            "identity",
            "types",
            "errors",
            "compatibility",
        }
    ),
    "adapters": frozenset(
        {
            "contract",
            "registry",
            "types",
            "errors",
            "validation",
            "adapters",
        }
    ),
    "cli": frozenset(
        {
            "contract",
            "registry",
            "loading",
            "identity",
            "compatibility",
            "types",
            "errors",
            "validation",
            "rendering",
            "cli",
        }
    ),
    "__init__": frozenset(
        {
            "contract",
            "registry",
            "loading",
            "identity",
            "compatibility",
            "types",
            "errors",
            "validation",
            "rendering",
        }
    ),
    "__main__": frozenset({"cli"}),
}

FORBIDDEN_IN_CORE: frozenset[str] = frozenset(
    {
        "llm_gateway_sdk",
        "promptfoo",
        "httpx",
        "urllib.request",
        "socket",
    }
)


def _layer_for_file(pkg_root: Path, file_path: Path) -> str:
    rel = file_path.relative_to(pkg_root)
    if len(rel.parts) == 1:
        return rel.stem
    return rel.parts[0]


def _extract_imports(tree: ast.AST, current_layer: str) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                module_suffix = node.module or ""
                if node.level == 1 and current_layer not in {
                    "__init__",
                    "__main__",
                    "errors",
                    "types",
                    "contract",
                    "registry",
                }:
                    target = (
                        f"prompt_contracts.{current_layer}.{module_suffix}"
                        if module_suffix
                        else f"prompt_contracts.{current_layer}"
                    )
                else:
                    target = (
                        f"prompt_contracts.{module_suffix}" if module_suffix else "prompt_contracts"
                    )
                imports.append((target, node.lineno))
            elif node.module:
                imports.append((node.module, node.lineno))
    return imports


def check_boundaries(src_root: Path) -> list[str]:
    """Return a list of boundary violation descriptions (empty if clean)."""
    pkg_root = src_root / "prompt_contracts"
    if not pkg_root.is_dir():
        return [f"Package directory not found: {pkg_root}"]

    violations: list[str] = []

    for py_file in sorted(pkg_root.rglob("*.py")):
        layer = _layer_for_file(pkg_root, py_file)
        allowed = ALLOWED_INTERNAL_DEPS.get(layer)
        if allowed is None:
            violations.append(f"{py_file}: unknown top-level layer {layer!r}")
            continue

        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))

        if py_file == pkg_root / "adapters" / "__init__.py":
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                        continue
                    violations.append(
                        f"{py_file}:{node.lineno}: adapters/__init__.py "
                        "must not eagerly import modules"
                    )

        for mod_name, lineno in _extract_imports(tree, layer):
            if layer not in {"adapters", "cli", "__main__"}:
                for forbidden in FORBIDDEN_IN_CORE:
                    if mod_name == forbidden or mod_name.startswith(f"{forbidden}."):
                        violations.append(
                            f"{py_file}:{lineno}: core layer {layer!r} "
                            f"imports forbidden module {mod_name!r}"
                        )

            if mod_name.startswith("prompt_contracts."):
                parts = mod_name.split(".")
                if len(parts) >= 2:
                    target_layer = parts[1]
                    if target_layer not in allowed:
                        violations.append(
                            f"{py_file}:{lineno}: layer {layer!r} cannot "
                            f"import from {target_layer!r} ({mod_name})"
                        )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify prompt_contracts internal import boundaries."
    )
    parser.add_argument(
        "--src",
        type=Path,
        default=Path("src"),
        help="Path to src directory (default: src).",
    )
    args = parser.parse_args(argv)

    violations = check_boundaries(args.src.resolve())
    if violations:
        for violation in violations:
            sys.stderr.write(f"BOUNDARY VIOLATION: {violation}\n")
        return 1

    sys.stdout.write("Import boundary verification passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
