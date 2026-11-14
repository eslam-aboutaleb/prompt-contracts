"""Bounded JSON Schema Draft 2020-12 profile validator and sanitizer.

Enforces the supported keyword profile, blocks remote reference retrieval, detects
cyclic ``$ref`` graphs, enforces expanded node ceilings, and translates validation
failures into sanitized :class:`ValidationIssue` objects without rejected values.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from heapq import nsmallest
from typing import Any

import jsonschema
import referencing

from prompt_contracts.errors import (
    ErrorCode,
    PromptContractError,
    ResourceLimitError,
    UnsupportedSchemaError,
    ValidationIssue,
)
from prompt_contracts.types import (
    DEFAULT_RUNTIME_POLICY,
    RuntimePolicy,
    freeze_json_value,
    thaw_json_value,
)

__all__ = [
    "ALLOWED_PRIMITIVE_TYPES",
    "DRAFT_2020_12_URI",
    "SUPPORTED_SCHEMA_KEYWORDS",
    "CompiledSchema",
    "compile_schema_profile",
    "expand_schema_node",
    "validate_instance_sanitized",
]

DRAFT_2020_12_URI = "https://json-schema.org/draft/2020-12/schema"

SUPPORTED_SCHEMA_KEYWORDS: frozenset[str] = frozenset(
    {
        "$schema",
        "title",
        "description",
        "type",
        "enum",
        "const",
        "properties",
        "required",
        "additionalProperties",
        "items",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "$defs",
        "$ref",
    }
)

ALLOWED_PRIMITIVE_TYPES: frozenset[str] = frozenset(
    {
        "object",
        "array",
        "string",
        "number",
        "integer",
        "boolean",
        "null",
    }
)

LOCAL_DEF_PREFIX = "#/$defs/"


def _no_remote_retrieval(_uri: str) -> referencing.Resource[Any]:
    raise UnsupportedSchemaError(
        "External schema reference retrieval is disabled by security policy",
        code=ErrorCode.SCHEMA_REF_EXTERNAL_OR_INVALID,
    )


_EMPTY_LOCAL_REGISTRY: referencing.Registry[Any] = referencing.Registry(
    retrieve=_no_remote_retrieval  # type: ignore[call-arg]
)


@dataclass(frozen=True, slots=True)
class CompiledSchema:
    """Verified immutable schema representation and local-only validator."""

    raw_schema: Mapping[str, Any]
    expanded_node_count: int
    is_input_schema: bool
    _validator: jsonschema.Draft202012Validator

    def to_dict(self) -> dict[str, Any]:
        """Return a defensive mutable copy of the raw schema."""
        res = thaw_json_value(self.raw_schema)
        assert isinstance(res, dict)
        return res


def _format_pointer(parts: list[str | int]) -> str:
    if not parts:
        return "$"
    out = ["$"]
    for part in parts:
        if isinstance(part, int):
            out.append(f"[{part}]")
        else:
            out.append(f".{part}")
    return "".join(out)


def _validate_keyword_types(
    node: Mapping[str, Any],
    *,
    path: list[str | int],
    is_root: bool,
    defs_map: Mapping[str, Any],
    contract_ref: str | None,
    source_path: str | None,
) -> None:
    if not isinstance(node, Mapping):
        raise UnsupportedSchemaError(
            f"Schema node at {_format_pointer(path)} must be a JSON object",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    for key in node:
        if key not in SUPPORTED_SCHEMA_KEYWORDS:
            raise UnsupportedSchemaError(
                f"Unsupported JSON Schema keyword {key!r} at {_format_pointer(path)}",
                code=ErrorCode.SCHEMA_KEYWORD_UNSUPPORTED,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        if key in ("$schema", "$defs") and not is_root:
            raise UnsupportedSchemaError(
                f"Keyword {key!r} is only permitted at the schema root ({_format_pointer(path)})",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    if "$schema" in node:
        schema_uri = node["$schema"]
        if schema_uri != DRAFT_2020_12_URI:
            raise UnsupportedSchemaError(
                "Only JSON Schema Draft 2020-12 ('$schema': "
                "'https://json-schema.org/draft/2020-12/schema') is supported",
                code=ErrorCode.SCHEMA_KEYWORD_UNSUPPORTED,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    for meta_key in ("title", "description"):
        if meta_key in node and type(node[meta_key]) is not str:
            raise UnsupportedSchemaError(
                f"Schema {meta_key!r} at {_format_pointer(path)} must be a string",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    if "$ref" in node:
        ref_val = node["$ref"]
        if type(ref_val) is not str or not ref_val.startswith(LOCAL_DEF_PREFIX):
            raise UnsupportedSchemaError(
                f"Schema '$ref' at {_format_pointer(path)} "
                "must be a local '#/$defs/<name>' reference",
                code=ErrorCode.SCHEMA_REF_EXTERNAL_OR_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        def_name = ref_val[len(LOCAL_DEF_PREFIX) :]
        if not def_name or "/" in def_name or def_name not in defs_map:
            raise UnsupportedSchemaError(
                f"Schema '$ref' at {_format_pointer(path)} points to undefined local definition",
                code=ErrorCode.SCHEMA_REF_EXTERNAL_OR_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        extra_keys = set(node.keys()) - {"$ref", "title", "description"}
        if extra_keys:
            raise UnsupportedSchemaError(
                f"Schema '$ref' node at {_format_pointer(path)} cannot "
                "combine '$ref' with sibling validation keywords",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    if "type" in node:
        t_val = node["type"]
        if type(t_val) is str:
            if t_val not in ALLOWED_PRIMITIVE_TYPES:
                raise UnsupportedSchemaError(
                    f"Unsupported schema type {t_val!r} at {_format_pointer(path)}",
                    code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                )
        elif isinstance(t_val, (list, tuple)):
            if (
                not t_val
                or not all(type(item) is str and item in ALLOWED_PRIMITIVE_TYPES for item in t_val)
                or len(set(t_val)) != len(t_val)
            ):
                raise UnsupportedSchemaError(
                    f"Schema 'type' list at {_format_pointer(path)} "
                    "must contain unique valid primitive type names",
                    code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                )
        else:
            raise UnsupportedSchemaError(
                f"Schema 'type' at {_format_pointer(path)} must be a string or list of strings",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    if "enum" in node:
        enum_val = node["enum"]
        if not isinstance(enum_val, (list, tuple)) or len(enum_val) == 0:
            raise UnsupportedSchemaError(
                f"Schema 'enum' at {_format_pointer(path)} must be a non-empty array",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    if "additionalProperties" in node and type(node["additionalProperties"]) is not bool:
        raise UnsupportedSchemaError(
            f"Schema 'additionalProperties' at {_format_pointer(path)} must be a boolean",
            code=ErrorCode.SCHEMA_KEYWORD_UNSUPPORTED,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    if "required" in node:
        req = node["required"]
        if (
            not isinstance(req, (list, tuple))
            or not all(type(k) is str and k for k in req)
            or len(set(req)) != len(req)
        ):
            raise UnsupportedSchemaError(
                f"Schema 'required' at {_format_pointer(path)} "
                "must be a list of unique non-empty strings",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    if "properties" in node:
        props = node["properties"]
        if not isinstance(props, Mapping):
            raise UnsupportedSchemaError(
                f"Schema 'properties' at {_format_pointer(path)} must be an object",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        for prop_name, prop_schema in props.items():
            if not isinstance(prop_schema, Mapping):
                raise UnsupportedSchemaError(
                    f"Property schema for {prop_name!r} at "
                    f"{_format_pointer(path)} must be an object",
                    code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                )

    if "items" in node and not isinstance(node["items"], Mapping):
        raise UnsupportedSchemaError(
            f"Schema 'items' at {_format_pointer(path)} must be a single schema object",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    for int_kw in ("minItems", "maxItems", "minLength", "maxLength"):
        if int_kw in node:
            val = node[int_kw]
            if type(val) is not int or val < 0:
                raise UnsupportedSchemaError(
                    f"Schema {int_kw!r} at {_format_pointer(path)} must be a non-negative integer",
                    code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                )

    if "minItems" in node and "maxItems" in node and node["minItems"] > node["maxItems"]:
        raise UnsupportedSchemaError(
            f"Schema 'minItems' cannot exceed 'maxItems' at {_format_pointer(path)}",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    if "minLength" in node and "maxLength" in node and node["minLength"] > node["maxLength"]:
        raise UnsupportedSchemaError(
            f"Schema 'minLength' cannot exceed 'maxLength' at {_format_pointer(path)}",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    for num_kw in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"):
        if num_kw in node:
            val = node[num_kw]
            if type(val) not in (int, float):
                raise UnsupportedSchemaError(
                    f"Schema {num_kw!r} at {_format_pointer(path)} must be a finite number",
                    code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                    contract_ref=contract_ref,
                    source_path=source_path,
                )

    if "minimum" in node and "maximum" in node and node["minimum"] > node["maximum"]:
        raise UnsupportedSchemaError(
            f"Schema 'minimum' cannot exceed 'maximum' at {_format_pointer(path)}",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )


def expand_schema_node(
    root_schema: Mapping[str, Any],
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    contract_ref: str | None = None,
    source_path: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Validate every node and expand local ``#/$defs/...`` references with cycle and node
    bounds.
    """
    if not isinstance(root_schema, Mapping):
        raise UnsupportedSchemaError(
            "Schema root must be a JSON object",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    raw_defs = root_schema.get("$defs", {})
    if not isinstance(raw_defs, Mapping):
        raise UnsupportedSchemaError(
            "Schema '$defs' must be an object mapping definition names to schema objects",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )
    for def_name, def_schema in raw_defs.items():
        if type(def_name) is not str or not def_name or "/" in def_name:
            raise UnsupportedSchemaError(
                "Invalid definition name in '$defs'",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        if not isinstance(def_schema, Mapping):
            raise UnsupportedSchemaError(
                f"Definition {def_name!r} in '$defs' must be a schema object",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    expanded_counter = 0

    def _walk(
        node: Mapping[str, Any],
        path: list[str | int],
        active_refs: tuple[str, ...],
        depth: int,
        is_root: bool,
    ) -> dict[str, Any]:
        nonlocal expanded_counter
        expanded_counter += 1
        if expanded_counter > policy.max_expanded_schema_nodes:
            raise ResourceLimitError(
                f"Expanded schema exceeds maximum of {policy.max_expanded_schema_nodes} nodes",
                code=ErrorCode.SCHEMA_EXPANSION_EXCEEDED,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        if depth > policy.max_nesting_depth:
            raise ResourceLimitError(
                f"Schema exceeds maximum nesting depth of {policy.max_nesting_depth}",
                code=ErrorCode.NESTING_DEPTH_EXCEEDED,
                contract_ref=contract_ref,
                source_path=source_path,
            )

        _validate_keyword_types(
            node,
            path=path,
            is_root=is_root,
            defs_map=raw_defs,
            contract_ref=contract_ref,
            source_path=source_path,
        )

        if "$ref" in node:
            ref_target = str(node["$ref"])
            def_name = ref_target[len(LOCAL_DEF_PREFIX) :]
            if def_name in active_refs:
                raise UnsupportedSchemaError(
                    f"Cyclic '$ref' detected involving '#/$defs/{def_name}'",
                    code=ErrorCode.SCHEMA_REF_CYCLE,
                    contract_ref=contract_ref,
                    source_path=source_path,
                )
            target_node = raw_defs[def_name]
            return _walk(
                target_node,
                [*path, "$ref", def_name],
                (*active_refs, def_name),
                depth + 1,
                False,
            )

        out: dict[str, Any] = {}
        for k, v in node.items():
            if k == "$defs":
                continue
            if k == "properties":
                props_out: dict[str, Any] = {}
                for prop_name, prop_node in v.items():
                    props_out[prop_name] = _walk(
                        prop_node,
                        [*path, "properties", prop_name],
                        active_refs,
                        depth + 1,
                        False,
                    )
                out["properties"] = props_out
            elif k == "items":
                out["items"] = _walk(
                    v,
                    [*path, "items"],
                    active_refs,
                    depth + 1,
                    False,
                )
            else:
                out[k] = thaw_json_value(freeze_json_value(v, max_depth=policy.max_nesting_depth))
        return out

    # Also validate all definitions in $defs even if unreferenced so unsupported keywords never hide
    for def_name, def_node in raw_defs.items():
        _walk(def_node, ["$defs", def_name], (def_name,), 1, False)

    expanded_root = _walk(root_schema, [], (), 0, True)
    return expanded_root, expanded_counter


def compile_schema_profile(
    schema: Mapping[str, Any],
    *,
    is_input_schema: bool = False,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    contract_ref: str | None = None,
    source_path: str | None = None,
) -> CompiledSchema:
    """Validate ``schema`` against the supported profile and return an immutable
    :class:`CompiledSchema`.
    """
    frozen_schema = freeze_json_value(schema, max_depth=policy.max_nesting_depth)
    if not isinstance(frozen_schema, Mapping):
        raise UnsupportedSchemaError(
            "Schema root must be a JSON object",
            code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
            contract_ref=contract_ref,
            source_path=source_path,
        )

    expanded_schema, expanded_count = expand_schema_node(
        frozen_schema,
        policy=policy,
        contract_ref=contract_ref,
        source_path=source_path,
    )

    if is_input_schema:
        if frozen_schema.get("type") != "object":
            raise UnsupportedSchemaError(
                "Input schema root must declare 'type': 'object'",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        if frozen_schema.get("additionalProperties") is not False:
            raise UnsupportedSchemaError(
                "Input schema root must declare 'additionalProperties': false",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )
        if "properties" not in frozen_schema or not isinstance(
            frozen_schema["properties"], Mapping
        ):
            raise UnsupportedSchemaError(
                "Input schema root must declare explicit 'properties'",
                code=ErrorCode.SCHEMA_STRUCTURE_INVALID,
                contract_ref=contract_ref,
                source_path=source_path,
            )

    validator = jsonschema.Draft202012Validator(expanded_schema, registry=_EMPTY_LOCAL_REGISTRY)

    return CompiledSchema(
        raw_schema=frozen_schema,
        expanded_node_count=expanded_count,
        is_input_schema=is_input_schema,
        _validator=validator,
    )


def _sanitize_validation_error(err: jsonschema.ValidationError) -> ValidationIssue:
    """Convert a ``jsonschema.ValidationError`` into a safe :class:`ValidationIssue` without
    values.
    """
    validator_name = str(err.validator)
    data_parts = [p if isinstance(p, int) else str(p) for p in err.absolute_path]
    schema_parts = [p if isinstance(p, int) else str(p) for p in err.absolute_schema_path]
    data_ptr = _format_pointer(data_parts)
    schema_ptr = _format_pointer(schema_parts)

    if validator_name == "required":
        missing_prop: str | None = None
        if isinstance(err.validator_value, (list, tuple)) and isinstance(err.instance, Mapping):
            for req_key in err.validator_value:
                if req_key not in err.instance:
                    missing_prop = str(req_key)
                    break
        msg = (
            f"Missing required property {missing_prop!r}"
            if missing_prop
            else "Missing required property"
        )
        return ValidationIssue(
            code="required",
            message=msg,
            data_path=data_ptr,
            schema_path=schema_ptr,
        )

    if validator_name == "additionalProperties":
        # Never echo unknown data-key names into paths or messages (plan section 14)
        return ValidationIssue(
            code="additionalProperties",
            message="Unexpected property is not permitted on closed object",
            data_path=data_ptr,
            schema_path=schema_ptr,
        )

    safe_messages: dict[str, str] = {
        "type": f"Value does not match required type {err.validator_value!r}",
        "enum": "Value is not one of the permitted enum members",
        "const": "Value does not match required constant",
        "minLength": f"String length is less than minimum {err.validator_value}",
        "maxLength": f"String length exceeds maximum {err.validator_value}",
        "minItems": f"Array item count is less than minimum {err.validator_value}",
        "maxItems": f"Array item count exceeds maximum {err.validator_value}",
        "minimum": f"Number is less than minimum {err.validator_value}",
        "maximum": f"Number exceeds maximum {err.validator_value}",
        "exclusiveMinimum": f"Number is not greater than exclusiveMinimum {err.validator_value}",
        "exclusiveMaximum": f"Number is not less than exclusiveMaximum {err.validator_value}",
    }
    msg = safe_messages.get(validator_name, f"Schema constraint '{validator_name}' failed")
    return ValidationIssue(
        code=validator_name,
        message=msg,
        data_path=data_ptr,
        schema_path=schema_ptr,
    )


def validate_instance_sanitized(
    compiled: CompiledSchema,
    instance: Any,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    error_cls: type[PromptContractError],
    error_code: str,
    summary_message: str,
    contract_ref: str | None = None,
) -> None:
    """Validate ``instance`` against ``compiled`` and raise ``error_cls`` with sanitized issues."""
    error_count = 0

    def counted_errors() -> Iterator[jsonschema.ValidationError]:
        nonlocal error_count
        for error in compiled._validator.iter_errors(instance):
            error_count += 1
            yield error

    raw_errors = nsmallest(
        policy.max_reported_issues,
        counted_errors(),
        key=lambda e: (
            [str(p) for p in e.absolute_path],
            [str(p) for p in e.absolute_schema_path],
            str(e.validator),
        ),
    )
    if not raw_errors:
        return

    reported = [_sanitize_validation_error(err) for err in raw_errors]
    truncated = max(0, error_count - len(reported))
    raise error_cls(
        summary_message,
        code=error_code,
        contract_ref=contract_ref,
        issues=reported,
        truncated_issue_count=truncated,
    )
