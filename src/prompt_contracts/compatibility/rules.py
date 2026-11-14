"""Conservative directional schema compatibility rules for Draft 2020-12 profile.

Caller-input direction requires ``I_old <= I_new`` (widening is compatible, narrowing is breaking).
Consumer-output direction requires ``O_new <= O_old`` (narrowing is compatible, widening is
breaking).
Any combination the rule set cannot prove returns ``CompatibilityStatus.UNKNOWN``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from prompt_contracts.compatibility.models import (
    CompatibilityDirection,
    CompatibilityFinding,
    CompatibilityRuleId,
    CompatibilityStatus,
    combine_statuses,
)

__all__ = ["compare_expanded_schemas"]

_CONSTRAINT_KEYWORDS = frozenset(
    {
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
    }
)

_TYPE_SPECIFIC_KEYWORDS = frozenset(
    {
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minItems",
        "maxItems",
        "items",
        "properties",
        "required",
        "additionalProperties",
    }
)


def _normalize_types(node: Mapping[str, Any]) -> set[str] | None:
    if "type" not in node:
        return None
    raw = node["type"]
    if isinstance(raw, str):
        return {raw}
    if isinstance(raw, (list, tuple)):
        return {str(x) for x in raw}
    return None


def _is_type_subset(sub: set[str], sup: set[str]) -> bool:
    """Return True if JSON Schema primitive type set ``sub`` is a subset of ``sup``."""
    for t in sub:
        if t in sup:
            continue
        if t == "integer" and "number" in sup:
            continue
        return False
    return True


def _strip_meta(node: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in node.items() if k in _CONSTRAINT_KEYWORDS}


def _json_equal(left: Any, right: Any) -> bool:
    """Compare JSON values without Python's ``True == 1`` ambiguity."""
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return left.keys() == right.keys() and all(
            _json_equal(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, (list, tuple)) and isinstance(right, (list, tuple)):
        return len(left) == len(right) and all(
            _json_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    return bool(left == right)


def _status_for_widening(direction: CompatibilityDirection) -> CompatibilityStatus:
    return (
        CompatibilityStatus.COMPATIBLE
        if direction == CompatibilityDirection.INPUT
        else CompatibilityStatus.BREAKING
    )


def _status_for_narrowing(direction: CompatibilityDirection) -> CompatibilityStatus:
    return (
        CompatibilityStatus.BREAKING
        if direction == CompatibilityDirection.INPUT
        else CompatibilityStatus.COMPATIBLE
    )


def _compare_numeric_lower_bounds(
    old_node: Mapping[str, Any],
    new_node: Mapping[str, Any],
    *,
    direction: CompatibilityDirection,
    path: str,
    findings: list[CompatibilityFinding],
) -> None:
    old_min = old_node.get("minimum")
    old_ex_min = old_node.get("exclusiveMinimum")
    new_min = new_node.get("minimum")
    new_ex_min = new_node.get("exclusiveMinimum")

    if (old_min, old_ex_min) == (new_min, new_ex_min):
        return

    # Both minimum and exclusiveMinimum present on same node is ambiguous -> unknown
    if (old_min is not None and old_ex_min is not None) or (
        new_min is not None and new_ex_min is not None
    ):
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                path=path,
                message="Simultaneous minimum and exclusiveMinimum cannot be proved compatible",
            )
        )
        return

    old_val = old_min if old_min is not None else old_ex_min
    old_exclusive = old_ex_min is not None
    new_val = new_min if new_min is not None else new_ex_min
    new_exclusive = new_ex_min is not None

    if old_val is None and new_val is not None:
        # Added lower bound -> narrowing
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=_status_for_narrowing(direction),
                rule_id=CompatibilityRuleId.NUMBER_MIN_RAISED,
                path=path,
                message="Added numeric lower bound",
            )
        )
        return

    if old_val is not None and new_val is None:
        # Removed lower bound -> widening
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=_status_for_widening(direction),
                rule_id=CompatibilityRuleId.NUMBER_MIN_LOWERED,
                path=path,
                message="Removed numeric lower bound",
            )
        )
        return

    assert old_val is not None and new_val is not None
    if old_exclusive == new_exclusive:
        if new_val > old_val:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.NUMBER_MIN_RAISED,
                    path=path,
                    message=f"Numeric lower bound raised from {old_val} to {new_val}",
                )
            )
        elif new_val < old_val:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.NUMBER_MIN_LOWERED,
                    path=path,
                    message=f"Numeric lower bound lowered from {old_val} to {new_val}",
                )
            )
        return

    # Switching inclusivity at the exact same value is provable; different values with switched
    # inclusivity is unknown for integers
    if new_val == old_val:
        if not old_exclusive and new_exclusive:
            # minimum: X -> exclusiveMinimum: X (strictly narrower)
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.NUMBER_MIN_RAISED,
                    path=path,
                    message=(
                        "Numeric lower bound tightened from "
                        f"inclusive {old_val} to exclusive {new_val}"
                    ),
                )
            )
        else:
            # exclusiveMinimum: X -> minimum: X (strictly wider)
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.NUMBER_MIN_LOWERED,
                    path=path,
                    message=(
                        "Numeric lower bound widened from "
                        f"exclusive {old_val} to inclusive {new_val}"
                    ),
                )
            )
    else:
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                path=path,
                message=(
                    "Mixed inclusive/exclusive numeric lower "
                    "bound change with different values is unknown"
                ),
            )
        )


def _compare_numeric_upper_bounds(
    old_node: Mapping[str, Any],
    new_node: Mapping[str, Any],
    *,
    direction: CompatibilityDirection,
    path: str,
    findings: list[CompatibilityFinding],
) -> None:
    old_max = old_node.get("maximum")
    old_ex_max = old_node.get("exclusiveMaximum")
    new_max = new_node.get("maximum")
    new_ex_max = new_node.get("exclusiveMaximum")

    if (old_max, old_ex_max) == (new_max, new_ex_max):
        return

    if (old_max is not None and old_ex_max is not None) or (
        new_max is not None and new_ex_max is not None
    ):
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                path=path,
                message="Simultaneous maximum and exclusiveMaximum cannot be proved compatible",
            )
        )
        return

    old_val = old_max if old_max is not None else old_ex_max
    old_exclusive = old_ex_max is not None
    new_val = new_max if new_max is not None else new_ex_max
    new_exclusive = new_ex_max is not None

    if old_val is None and new_val is not None:
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=_status_for_narrowing(direction),
                rule_id=CompatibilityRuleId.NUMBER_MAX_LOWERED,
                path=path,
                message="Added numeric upper bound",
            )
        )
        return

    if old_val is not None and new_val is None:
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=_status_for_widening(direction),
                rule_id=CompatibilityRuleId.NUMBER_MAX_RAISED,
                path=path,
                message="Removed numeric upper bound",
            )
        )
        return

    assert old_val is not None and new_val is not None
    if old_exclusive == new_exclusive:
        if new_val < old_val:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.NUMBER_MAX_LOWERED,
                    path=path,
                    message=f"Numeric upper bound lowered from {old_val} to {new_val}",
                )
            )
        elif new_val > old_val:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.NUMBER_MAX_RAISED,
                    path=path,
                    message=f"Numeric upper bound raised from {old_val} to {new_val}",
                )
            )
        return

    if new_val == old_val:
        if not old_exclusive and new_exclusive:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.NUMBER_MAX_LOWERED,
                    path=path,
                    message=(
                        "Numeric upper bound tightened from "
                        f"inclusive {old_val} to exclusive {new_val}"
                    ),
                )
            )
        else:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.NUMBER_MAX_RAISED,
                    path=path,
                    message=(
                        "Numeric upper bound widened from "
                        f"exclusive {old_val} to inclusive {new_val}"
                    ),
                )
            )
    else:
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                path=path,
                message=(
                    "Mixed inclusive/exclusive numeric upper "
                    "bound change with different values is unknown"
                ),
            )
        )


def _compare_nodes(
    old_node: Mapping[str, Any],
    new_node: Mapping[str, Any],
    *,
    direction: CompatibilityDirection,
    path: str,
    findings: list[CompatibilityFinding],
) -> None:
    old_clean = _strip_meta(old_node)
    new_clean = _strip_meta(new_node)
    if _json_equal(old_clean, new_clean):
        return

    if any(
        set(node.get("required", ())) - set(node.get("properties", {}))
        for node in (old_clean, new_clean)
    ):
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                path=path,
                message="Required names outside declared properties need explicit review",
            )
        )
        return

    # Check const / enum transitions mixed with other constraint changes
    if ("const" in old_clean) != ("const" in new_clean) or (
        ("enum" in old_clean) != ("enum" in new_clean)
    ):
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                path=path,
                message=(
                    "Transition between enum/const and general schema constraints is not provable"
                ),
            )
        )
        return

    if "const" in old_clean and "const" in new_clean:
        if not _json_equal(old_clean["const"], new_clean["const"]):
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.BREAKING,
                    rule_id=CompatibilityRuleId.CONST_CHANGED,
                    path=path,
                    message="Schema const value changed",
                )
            )
        else:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.UNKNOWN,
                    rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                    path=path,
                    message="Sibling constraints changed on a constant-valued schema",
                )
            )
        return

    if "enum" in old_clean and "enum" in new_clean:
        # If enum is combined with changing bounds/types, report unknown
        old_other = {k: v for k, v in old_clean.items() if k != "enum"}
        new_other = {k: v for k, v in new_clean.items() if k != "enum"}
        if not _json_equal(old_other, new_other):
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.UNKNOWN,
                    rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                    path=path,
                    message=(
                        "Simultaneous enum and sibling constraint modification cannot be proved"
                    ),
                )
            )
            return

        old_items = list(old_clean["enum"])
        new_items = list(new_clean["enum"])
        added = [x for x in new_items if not any(_json_equal(x, y) for y in old_items)]
        removed = [x for x in old_items if not any(_json_equal(x, y) for y in new_items)]
        if added and removed:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.BREAKING,
                    rule_id=CompatibilityRuleId.ENUM_CHANGED_INCOMPATIBLE,
                    path=path,
                    message="Enum both added and removed permitted values",
                )
            )
        elif added:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.ENUM_WIDENED,
                    path=path,
                    message=f"Enum widened with {len(added)} new value(s)",
                )
            )
        elif removed:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.ENUM_NARROWED,
                    path=path,
                    message=f"Enum narrowed by removing {len(removed)} value(s)",
                )
            )
        return

    # Type analysis
    old_types = _normalize_types(old_clean)
    new_types = _normalize_types(new_clean)
    if old_types != new_types:
        if old_types is None or new_types is None:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.UNKNOWN,
                    rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                    path=path,
                    message="Adding or removing unrestricted 'type' keyword is not provable",
                )
            )
            return

        # Check if type-specific constraints also changed while type changed
        old_ts = {k: v for k, v in old_clean.items() if k in _TYPE_SPECIFIC_KEYWORDS}
        new_ts = {k: v for k, v in new_clean.items() if k in _TYPE_SPECIFIC_KEYWORDS}
        if old_ts != new_ts:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.UNKNOWN,
                    rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                    path=path,
                    message=(
                        "Simultaneous type change and type-specific "
                        "constraint change is not provable"
                    ),
                )
            )
            return

        old_in_new = _is_type_subset(old_types, new_types)
        new_in_old = _is_type_subset(new_types, old_types)
        if old_in_new and not new_in_old:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.TYPE_WIDENED,
                    path=path,
                    message=f"Schema type widened from {sorted(old_types)} to {sorted(new_types)}",
                )
            )
        elif new_in_old and not old_in_new:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.TYPE_NARROWED,
                    path=path,
                    message=f"Schema type narrowed from {sorted(old_types)} to {sorted(new_types)}",
                )
            )
        elif not old_in_new and not new_in_old:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.BREAKING,
                    rule_id=CompatibilityRuleId.TYPE_CHANGED_INCOMPATIBLE,
                    path=path,
                    message=(
                        "Schema type changed incompatibly from "
                        f"{sorted(old_types)} to {sorted(new_types)}"
                    ),
                )
            )
        return

    # Multi-type union with changing type-specific constraints is ambiguous
    if old_types is not None and len(old_types) > 1:
        old_ts = {k: v for k, v in old_clean.items() if k in _TYPE_SPECIFIC_KEYWORDS}
        new_ts = {k: v for k, v in new_clean.items() if k in _TYPE_SPECIFIC_KEYWORDS}
        if old_ts != new_ts:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.UNKNOWN,
                    rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                    path=path,
                    message=(
                        "Constraint modification on multi-type union cannot be proved compatible"
                    ),
                )
            )
            return

    # String length bounds (minLength defaults to 0, maxLength defaults to +inf)
    old_min_len = int(old_clean.get("minLength", 0))
    new_min_len = int(new_clean.get("minLength", 0))
    if new_min_len > old_min_len:
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=_status_for_narrowing(direction),
                rule_id=CompatibilityRuleId.STRING_MIN_LENGTH_RAISED,
                path=path,
                message=f"String minLength raised from {old_min_len} to {new_min_len}",
            )
        )
    elif new_min_len < old_min_len:
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=_status_for_widening(direction),
                rule_id=CompatibilityRuleId.STRING_MIN_LENGTH_LOWERED,
                path=path,
                message=f"String minLength lowered from {old_min_len} to {new_min_len}",
            )
        )

    old_max_len = old_clean.get("maxLength")
    new_max_len = new_clean.get("maxLength")
    if old_max_len != new_max_len:
        if old_max_len is None and new_max_len is not None:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.STRING_MAX_LENGTH_LOWERED,
                    path=path,
                    message=f"String maxLength added ({new_max_len})",
                )
            )
        elif old_max_len is not None and new_max_len is None:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.STRING_MAX_LENGTH_RAISED,
                    path=path,
                    message=f"String maxLength ({old_max_len}) removed",
                )
            )
        elif old_max_len is not None and new_max_len is not None:
            if new_max_len < old_max_len:
                findings.append(
                    CompatibilityFinding(
                        direction=direction,
                        status=_status_for_narrowing(direction),
                        rule_id=CompatibilityRuleId.STRING_MAX_LENGTH_LOWERED,
                        path=path,
                        message=f"String maxLength lowered from {old_max_len} to {new_max_len}",
                    )
                )
            elif new_max_len > old_max_len:
                findings.append(
                    CompatibilityFinding(
                        direction=direction,
                        status=_status_for_widening(direction),
                        rule_id=CompatibilityRuleId.STRING_MAX_LENGTH_RAISED,
                        path=path,
                        message=f"String maxLength raised from {old_max_len} to {new_max_len}",
                    )
                )

    # Array length bounds (minItems defaults to 0, maxItems defaults to +inf)
    old_min_items = int(old_clean.get("minItems", 0))
    new_min_items = int(new_clean.get("minItems", 0))
    if new_min_items > old_min_items:
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=_status_for_narrowing(direction),
                rule_id=CompatibilityRuleId.ARRAY_MIN_ITEMS_RAISED,
                path=path,
                message=f"Array minItems raised from {old_min_items} to {new_min_items}",
            )
        )
    elif new_min_items < old_min_items:
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=_status_for_widening(direction),
                rule_id=CompatibilityRuleId.ARRAY_MIN_ITEMS_LOWERED,
                path=path,
                message=f"Array minItems lowered from {old_min_items} to {new_min_items}",
            )
        )

    old_max_items = old_clean.get("maxItems")
    new_max_items = new_clean.get("maxItems")
    if old_max_items != new_max_items:
        if old_max_items is None and new_max_items is not None:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.ARRAY_MAX_ITEMS_LOWERED,
                    path=path,
                    message=f"Array maxItems added ({new_max_items})",
                )
            )
        elif old_max_items is not None and new_max_items is None:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.ARRAY_MAX_ITEMS_RAISED,
                    path=path,
                    message=f"Array maxItems ({old_max_items}) removed",
                )
            )
        elif old_max_items is not None and new_max_items is not None:
            if new_max_items < old_max_items:
                findings.append(
                    CompatibilityFinding(
                        direction=direction,
                        status=_status_for_narrowing(direction),
                        rule_id=CompatibilityRuleId.ARRAY_MAX_ITEMS_LOWERED,
                        path=path,
                        message=f"Array maxItems lowered from {old_max_items} to {new_max_items}",
                    )
                )
            elif new_max_items > old_max_items:
                findings.append(
                    CompatibilityFinding(
                        direction=direction,
                        status=_status_for_widening(direction),
                        rule_id=CompatibilityRuleId.ARRAY_MAX_ITEMS_RAISED,
                        path=path,
                        message=f"Array maxItems raised from {old_max_items} to {new_max_items}",
                    )
                )

    # Numeric bounds
    _compare_numeric_lower_bounds(
        old_clean, new_clean, direction=direction, path=path, findings=findings
    )
    _compare_numeric_upper_bounds(
        old_clean, new_clean, direction=direction, path=path, findings=findings
    )

    # Array items
    if "items" in old_clean or "items" in new_clean:
        if "items" in old_clean and "items" in new_clean:
            _compare_nodes(
                old_clean["items"],
                new_clean["items"],
                direction=direction,
                path=f"{path}.items",
                findings=findings,
            )
        else:
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=CompatibilityStatus.UNKNOWN,
                    rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                    path=f"{path}.items",
                    message="Adding or removing array 'items' schema cannot be proved compatible",
                )
            )

    # Object properties, required, additionalProperties
    old_add_props = bool(old_clean.get("additionalProperties", True))
    new_add_props = bool(new_clean.get("additionalProperties", True))
    if old_add_props != new_add_props:
        if not old_add_props and new_add_props:
            # Closed -> Open (widening)
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.ADDITIONAL_PROPERTIES_CHANGED,
                    path=f"{path}.additionalProperties",
                    message="additionalProperties changed from false to true",
                )
            )
        else:
            # Open -> Closed (narrowing)
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.ADDITIONAL_PROPERTIES_CHANGED,
                    path=f"{path}.additionalProperties",
                    message="additionalProperties changed from true to false",
                )
            )

    old_props: Mapping[str, Any] = old_clean.get("properties", {})
    new_props: Mapping[str, Any] = new_clean.get("properties", {})
    old_req = set(old_clean.get("required", ()))
    new_req = set(new_clean.get("required", ()))

    all_prop_names = sorted(set(old_props.keys()) | set(new_props.keys()))
    if (old_req ^ new_req) - set(all_prop_names):
        findings.append(
            CompatibilityFinding(
                direction=direction,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.UNKNOWN_COMBINATION,
                path=f"{path}.required",
                message="Required names outside declared properties changed",
            )
        )
    for prop_name in all_prop_names:
        prop_path = f"{path}.properties.{prop_name}"
        in_old = prop_name in old_props
        in_new = prop_name in new_props
        was_req = prop_name in old_req
        is_req = prop_name in new_req

        if not in_old and in_new:
            if is_req:
                # Newly added required property:
                # Input: breaking (old valid inputs omit it).
                # Output: if old object was closed, breaking (new outputs include a key
                #         rejected by old closed object); if open, compatible narrowing.
                status = (
                    CompatibilityStatus.BREAKING
                    if direction == CompatibilityDirection.INPUT
                    else (
                        CompatibilityStatus.BREAKING
                        if not old_add_props
                        else CompatibilityStatus.COMPATIBLE
                    )
                )
                findings.append(
                    CompatibilityFinding(
                        direction=direction,
                        status=status,
                        rule_id=CompatibilityRuleId.REQUIRED_PROPERTY_ADDED,
                        path=prop_path,
                        message=f"Added required property {prop_name!r}",
                    )
                )
            else:
                # Newly added optional property:
                # Input: compatible (if old inputs omit it, still valid).
                # Output: breaking if old object was closed (additionalProperties: false),
                # compatible if open.
                if direction == CompatibilityDirection.INPUT:
                    # An open old object already accepts arbitrary values for this name.
                    # Declaring a schema can reject those old values.
                    status = (
                        CompatibilityStatus.UNKNOWN
                        if old_add_props
                        else CompatibilityStatus.COMPATIBLE
                    )
                else:
                    status = (
                        CompatibilityStatus.BREAKING
                        if not old_add_props
                        else CompatibilityStatus.COMPATIBLE
                    )
                findings.append(
                    CompatibilityFinding(
                        direction=direction,
                        status=status,
                        rule_id=CompatibilityRuleId.OPTIONAL_PROPERTY_ADDED,
                        path=prop_path,
                        message=f"Added optional property {prop_name!r}",
                    )
                )
            continue

        if in_old and not in_new:
            if was_req:
                # Removed a previously required property from properties:
                # Input: if new object is closed (additionalProperties: false), old callers
                # sending it are rejected -> breaking!
                # Output: new outputs may omit a property old consumers required -> breaking!
                if direction == CompatibilityDirection.INPUT:
                    status = (
                        CompatibilityStatus.BREAKING
                        if not new_add_props
                        else CompatibilityStatus.COMPATIBLE
                    )
                else:
                    status = CompatibilityStatus.BREAKING
                findings.append(
                    CompatibilityFinding(
                        direction=direction,
                        status=status,
                        rule_id=CompatibilityRuleId.REQUIRED_PROPERTY_REMOVED,
                        path=prop_path,
                        message=f"Removed previously required property {prop_name!r}",
                    )
                )
            else:
                # Removed a previously optional property:
                # Input: breaking if new object is closed (old callers sending it are rejected).
                # Output: compatible narrowing (new outputs cannot emit it when closed).
                if direction == CompatibilityDirection.INPUT:
                    status = (
                        CompatibilityStatus.BREAKING
                        if not new_add_props
                        else CompatibilityStatus.COMPATIBLE
                    )
                else:
                    status = (
                        CompatibilityStatus.COMPATIBLE
                        if not new_add_props
                        else CompatibilityStatus.BREAKING
                    )
                findings.append(
                    CompatibilityFinding(
                        direction=direction,
                        status=status,
                        rule_id=CompatibilityRuleId.OPTIONAL_PROPERTY_REMOVED,
                        path=prop_path,
                        message=f"Removed optional property {prop_name!r}",
                    )
                )
            continue

        # Property exists in both old and new schemas
        if not was_req and is_req:
            # Optional promoted to required!
            # Input: breaking (old callers omitting it fail).
            # Output: compatible strengthening (plan 11.2: "can be strengthening if property
            # already existed as optional").
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_narrowing(direction),
                    rule_id=CompatibilityRuleId.OPTIONAL_PROMOTED_TO_REQUIRED,
                    path=prop_path,
                    message=f"Existing optional property {prop_name!r} promoted to required",
                )
            )
        elif was_req and not is_req:
            # Required demoted to optional!
            # Input: compatible widening.
            # Output: breaking (new outputs may omit it).
            findings.append(
                CompatibilityFinding(
                    direction=direction,
                    status=_status_for_widening(direction),
                    rule_id=CompatibilityRuleId.REQUIRED_DEMOTED_TO_OPTIONAL,
                    path=prop_path,
                    message=f"Required property {prop_name!r} made optional",
                )
            )

        _compare_nodes(
            old_props[prop_name],
            new_props[prop_name],
            direction=direction,
            path=prop_path,
            findings=findings,
        )


def compare_expanded_schemas(
    old_expanded: Mapping[str, Any],
    new_expanded: Mapping[str, Any],
    *,
    direction: CompatibilityDirection,
) -> tuple[CompatibilityStatus, tuple[CompatibilityFinding, ...]]:
    """Compare two expanded schemas in ``direction`` and return ``(status, findings)``."""
    findings: list[CompatibilityFinding] = []
    _compare_nodes(
        old_expanded,
        new_expanded,
        direction=direction,
        path="$",
        findings=findings,
    )
    status = combine_statuses([f.status for f in findings])
    return status, tuple(findings)
