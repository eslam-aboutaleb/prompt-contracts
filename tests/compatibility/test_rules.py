"""Tests for directional compatibility rules across fixtures and edge cases (T26, AC-17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from prompt_contracts.compatibility.models import (
    CompatibilityDirection,
    CompatibilityRuleId,
    CompatibilityStatus,
)
from prompt_contracts.compatibility.rules import compare_expanded_schemas
from prompt_contracts.validation.profile import expand_schema_node


def test_fixture_compatibility_cases(repo_root: Path) -> None:
    cases_path = repo_root / "tests" / "fixtures" / "compatibility_cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    for case in cases:
        direction = CompatibilityDirection(case["direction"])
        old_exp, _ = expand_schema_node(case["old_schema"])
        new_exp, _ = expand_schema_node(case["new_schema"])
        status, findings = compare_expanded_schemas(old_exp, new_exp, direction=direction)
        assert str(status) == case["expected_status"], f"Failed case {case['id']}"
        assert any(f.rule_id == case["expected_rule_id"] for f in findings), (
            f"Missing rule {case['expected_rule_id']} in {case['id']}"
        )


@pytest.mark.parametrize(
    "direction,old_bounds,new_bounds,expected_status",
    [
        # Input: lowering minLength or raising maxLength is compatible
        (
            CompatibilityDirection.INPUT,
            {"type": "string", "minLength": 5, "maxLength": 20},
            {"type": "string", "minLength": 2, "maxLength": 40},
            CompatibilityStatus.COMPATIBLE,
        ),
        # Input: raising minLength or lowering maxLength is breaking
        (
            CompatibilityDirection.INPUT,
            {"type": "string", "minLength": 2, "maxLength": 40},
            {"type": "string", "minLength": 5, "maxLength": 20},
            CompatibilityStatus.BREAKING,
        ),
        # Output: raising minLength or lowering maxLength (narrowing) is compatible
        (
            CompatibilityDirection.OUTPUT,
            {"type": "string", "minLength": 2, "maxLength": 40},
            {"type": "string", "minLength": 5, "maxLength": 20},
            CompatibilityStatus.COMPATIBLE,
        ),
        # Output: lowering minLength or raising maxLength (widening) is breaking
        (
            CompatibilityDirection.OUTPUT,
            {"type": "string", "minLength": 5, "maxLength": 20},
            {"type": "string", "minLength": 2, "maxLength": 40},
            CompatibilityStatus.BREAKING,
        ),
    ],
)
def test_string_bounds_directional_symmetry(
    direction: CompatibilityDirection,
    old_bounds: dict[str, object],
    new_bounds: dict[str, object],
    expected_status: CompatibilityStatus,
) -> None:
    old_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["val"],
        "properties": {"val": old_bounds},
    }
    new_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["val"],
        "properties": {"val": new_bounds},
    }
    old_exp, _ = expand_schema_node(old_schema)
    new_exp, _ = expand_schema_node(new_schema)
    status, _ = compare_expanded_schemas(old_exp, new_exp, direction=direction)
    assert status is expected_status


def test_unprovable_integer_bound_inclusivity_switch_returns_unknown_status() -> None:
    old_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["val"],
        "properties": {"val": {"type": "integer", "minimum": 5}},
    }
    new_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["val"],
        "properties": {"val": {"type": "integer", "exclusiveMinimum": 3}},
    }
    old_exp, _ = expand_schema_node(old_schema)
    new_exp, _ = expand_schema_node(new_schema)
    status, findings = compare_expanded_schemas(
        old_exp, new_exp, direction=CompatibilityDirection.INPUT
    )
    assert status is CompatibilityStatus.UNKNOWN
    assert any(f.rule_id == CompatibilityRuleId.UNKNOWN_COMBINATION for f in findings)


@pytest.mark.parametrize(
    "direction,old_prop,new_prop,expected_status,expected_rule",
    [
        # Numeric lower bounds
        (
            CompatibilityDirection.INPUT,
            {"type": "number"},
            {"type": "number", "minimum": 0},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.NUMBER_MIN_RAISED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "minimum": 0},
            {"type": "number"},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.NUMBER_MIN_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "minimum": 5},
            {"type": "number", "minimum": 10},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.NUMBER_MIN_RAISED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "minimum": 10},
            {"type": "number", "minimum": 5},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.NUMBER_MIN_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "minimum": 5},
            {"type": "number", "exclusiveMinimum": 5},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.NUMBER_MIN_RAISED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "exclusiveMinimum": 5},
            {"type": "number", "minimum": 5},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.NUMBER_MIN_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "minimum": 5, "exclusiveMinimum": 5},
            {"type": "number", "minimum": 5},
            CompatibilityStatus.UNKNOWN,
            CompatibilityRuleId.UNKNOWN_COMBINATION,
        ),
        # Numeric upper bounds
        (
            CompatibilityDirection.INPUT,
            {"type": "number"},
            {"type": "number", "maximum": 100},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.NUMBER_MAX_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "maximum": 100},
            {"type": "number"},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.NUMBER_MAX_RAISED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "maximum": 100},
            {"type": "number", "maximum": 50},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.NUMBER_MAX_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "maximum": 50},
            {"type": "number", "maximum": 100},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.NUMBER_MAX_RAISED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "maximum": 100},
            {"type": "number", "exclusiveMaximum": 100},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.NUMBER_MAX_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "exclusiveMaximum": 100},
            {"type": "number", "maximum": 100},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.NUMBER_MAX_RAISED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "maximum": 100},
            {"type": "number", "exclusiveMaximum": 90},
            CompatibilityStatus.UNKNOWN,
            CompatibilityRuleId.UNKNOWN_COMBINATION,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number", "maximum": 100, "exclusiveMaximum": 100},
            {"type": "number", "maximum": 100},
            CompatibilityStatus.UNKNOWN,
            CompatibilityRuleId.UNKNOWN_COMBINATION,
        ),
        # Const and Enum rules
        (
            CompatibilityDirection.INPUT,
            {"const": "a"},
            {"const": "b"},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.CONST_CHANGED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"const": "a"},
            {"type": "string"},
            CompatibilityStatus.UNKNOWN,
            CompatibilityRuleId.UNKNOWN_COMBINATION,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "string", "enum": ["a", "b"], "maxLength": 5},
            {"type": "string", "enum": ["a", "b", "c"], "maxLength": 10},
            CompatibilityStatus.UNKNOWN,
            CompatibilityRuleId.UNKNOWN_COMBINATION,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "string", "enum": ["a", "b"]},
            {"type": "string", "enum": ["b", "c"]},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.ENUM_CHANGED_INCOMPATIBLE,
        ),
        # Type changes
        (
            CompatibilityDirection.INPUT,
            {"type": "integer"},
            {"type": "number"},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.TYPE_WIDENED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "number"},
            {"type": "integer"},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.TYPE_NARROWED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "string"},
            {"type": "integer"},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.TYPE_CHANGED_INCOMPATIBLE,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "string"},
            {"type": ["string", "null"], "minLength": 1},
            CompatibilityStatus.UNKNOWN,
            CompatibilityRuleId.UNKNOWN_COMBINATION,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": ["string", "null"], "minLength": 1},
            {"type": ["string", "null"], "minLength": 2},
            CompatibilityStatus.UNKNOWN,
            CompatibilityRuleId.UNKNOWN_COMBINATION,
        ),
        # String maxLength added/removed
        (
            CompatibilityDirection.INPUT,
            {"type": "string"},
            {"type": "string", "maxLength": 10},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.STRING_MAX_LENGTH_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "string", "maxLength": 10},
            {"type": "string"},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.STRING_MAX_LENGTH_RAISED,
        ),
        # Array bounds and items
        (
            CompatibilityDirection.INPUT,
            {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
            {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.ARRAY_MIN_ITEMS_RAISED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 3},
            {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 5},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.ARRAY_MIN_ITEMS_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "array", "items": {"type": "string"}},
            {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            CompatibilityStatus.BREAKING,
            CompatibilityRuleId.ARRAY_MAX_ITEMS_LOWERED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "array", "items": {"type": "string"}, "maxItems": 5},
            {"type": "array", "items": {"type": "string"}},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.ARRAY_MAX_ITEMS_RAISED,
        ),
        (
            CompatibilityDirection.INPUT,
            {"type": "array", "items": {"type": "integer"}},
            {"type": "array", "items": {"type": "number"}},
            CompatibilityStatus.COMPATIBLE,
            CompatibilityRuleId.TYPE_WIDENED,
        ),
    ],
)
def test_schema_rule_matrix(
    direction: CompatibilityDirection,
    old_prop: dict[str, object],
    new_prop: dict[str, object],
    expected_status: CompatibilityStatus,
    expected_rule: CompatibilityRuleId,
) -> None:
    old_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["val"],
        "properties": {"val": old_prop},
    }
    new_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["val"],
        "properties": {"val": new_prop},
    }
    old_exp, _ = expand_schema_node(old_schema)
    new_exp, _ = expand_schema_node(new_schema)
    status, findings = compare_expanded_schemas(old_exp, new_exp, direction=direction)
    assert status is expected_status
    assert any(f.rule_id == str(expected_rule) for f in findings)


def test_object_property_and_additional_properties_transitions() -> None:
    base_old = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["req_keep", "req_remove", "req_demote"],
        "properties": {
            "req_keep": {"type": "string"},
            "req_remove": {"type": "string"},
            "req_demote": {"type": "string"},
            "opt_remove": {"type": "string"},
            "opt_promote": {"type": "string"},
        },
    }
    base_new = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": True,
        "required": ["req_keep", "opt_promote", "req_added"],
        "properties": {
            "req_keep": {"type": "string"},
            "req_demote": {"type": "string"},
            "opt_promote": {"type": "string"},
            "req_added": {"type": "string"},
            "opt_added": {"type": "string"},
        },
    }
    old_exp, _ = expand_schema_node(base_old)
    new_exp, _ = expand_schema_node(base_new)

    in_status, in_findings = compare_expanded_schemas(
        old_exp, new_exp, direction=CompatibilityDirection.INPUT
    )
    assert in_status is CompatibilityStatus.BREAKING
    in_rules = {f.rule_id for f in in_findings}
    assert CompatibilityRuleId.ADDITIONAL_PROPERTIES_CHANGED in in_rules
    assert CompatibilityRuleId.REQUIRED_PROPERTY_ADDED in in_rules
    assert CompatibilityRuleId.OPTIONAL_PROPERTY_ADDED in in_rules
    assert CompatibilityRuleId.REQUIRED_PROPERTY_REMOVED in in_rules
    assert CompatibilityRuleId.OPTIONAL_PROPERTY_REMOVED in in_rules
    assert CompatibilityRuleId.OPTIONAL_PROMOTED_TO_REQUIRED in in_rules
    assert CompatibilityRuleId.REQUIRED_DEMOTED_TO_OPTIONAL in in_rules

    out_status, out_findings = compare_expanded_schemas(
        old_exp, new_exp, direction=CompatibilityDirection.OUTPUT
    )
    assert out_status is CompatibilityStatus.BREAKING
    out_rules = {f.rule_id for f in out_findings}
    assert CompatibilityRuleId.ADDITIONAL_PROPERTIES_CHANGED in out_rules
    assert CompatibilityRuleId.REQUIRED_PROPERTY_ADDED in out_rules
    assert CompatibilityRuleId.OPTIONAL_PROPERTY_ADDED in out_rules
    assert CompatibilityRuleId.REQUIRED_PROPERTY_REMOVED in out_rules
    assert CompatibilityRuleId.OPTIONAL_PROPERTY_REMOVED in out_rules
    assert CompatibilityRuleId.OPTIONAL_PROMOTED_TO_REQUIRED in out_rules
    assert CompatibilityRuleId.REQUIRED_DEMOTED_TO_OPTIONAL in out_rules

    # Also test open -> closed
    rev_status, rev_findings = compare_expanded_schemas(
        new_exp, old_exp, direction=CompatibilityDirection.INPUT
    )
    assert rev_status is CompatibilityStatus.BREAKING
    assert any(f.rule_id == CompatibilityRuleId.ADDITIONAL_PROPERTIES_CHANGED for f in rev_findings)


def test_compare_contracts_text_mode_and_template_changes(
    examples_dir: Path, tmp_path: Path
) -> None:
    import dataclasses
    import shutil

    from prompt_contracts import Contract, compare_contracts
    from prompt_contracts.types import MessageRole

    b1 = tmp_path / "b1"
    b2 = tmp_path / "b2"
    shutil.copytree(examples_dir / "contracts" / "career.application-answer" / "1.0.0", b1)
    shutil.copytree(examples_dir / "contracts" / "career.application-answer" / "1.0.0", b2)

    # Convert both to text mode
    t1 = (b1 / "contract.toml").read_text(encoding="utf-8")
    t1_text = t1.replace(
        'mode = "json"\nschema = "output.schema.json"',
        'mode = "text"\nmin_length = 5\nmax_length = 100',
    )
    (b1 / "contract.toml").write_text(t1_text, encoding="utf-8")
    (b1 / "output.schema.json").unlink()

    t2_text = t1.replace(
        'mode = "json"\nschema = "output.schema.json"',
        'mode = "text"\nmin_length = 10\nmax_length = 80',
    )
    (b2 / "contract.toml").write_text(t2_text, encoding="utf-8")
    (b2 / "output.schema.json").unlink()
    # Change placeholder set in b2/user.md
    (b2 / "user.md").write_text("Question only: {{question}}\n", encoding="utf-8")

    c_json = Contract.from_directory(
        examples_dir / "contracts" / "career.application-answer" / "1.0.0"
    )
    c_text1 = Contract.from_directory(b1)
    c_text2 = Contract.from_directory(b2)

    # Mode change: json_schema -> text
    rep_mode = compare_contracts(c_json, c_text1)
    assert rep_mode.output_status is CompatibilityStatus.BREAKING
    assert rep_mode.behavioral_review_required is True
    assert any(f.rule_id == CompatibilityRuleId.OUTPUT_MODE_CHANGED for f in rep_mode.findings)

    # Text narrowed (compatible) + placeholder set changed
    rep_narrow = compare_contracts(c_text1, c_text2)
    assert rep_narrow.output_status is CompatibilityStatus.COMPATIBLE
    assert rep_narrow.behavioral_review_required is True
    assert any(f.rule_id == CompatibilityRuleId.TEXT_LENGTH_NARROWED for f in rep_narrow.findings)
    assert any(
        f.rule_id == CompatibilityRuleId.PLACEHOLDER_SET_CHANGED for f in rep_narrow.findings
    )

    # Text widened (breaking)
    rep_wide = compare_contracts(c_text2, c_text1)
    assert rep_wide.output_status is CompatibilityStatus.BREAKING
    assert any(f.rule_id == CompatibilityRuleId.TEXT_LENGTH_WIDENED for f in rep_wide.findings)

    # Text equal bounds
    rep_eq = compare_contracts(c_text1, c_text1)
    assert rep_eq.output_status is CompatibilityStatus.COMPATIBLE

    # Format/renderer change
    c_diff_fmt = dataclasses.replace(c_text1, format_version=2)
    rep_fmt = compare_contracts(c_text1, c_diff_fmt)
    assert rep_fmt.input_status is CompatibilityStatus.UNKNOWN
    assert rep_fmt.output_status is CompatibilityStatus.UNKNOWN
    assert any(
        f.rule_id == CompatibilityRuleId.FORMAT_OR_RENDERER_CHANGED for f in rep_fmt.findings
    )

    # Message role/order change
    reversed_msgs = (
        dataclasses.replace(c_text1.messages[0], role=MessageRole.USER),
        c_text1.messages[1],
    )
    c_diff_roles = dataclasses.replace(c_text1, messages=reversed_msgs)
    rep_roles = compare_contracts(c_text1, c_diff_roles)
    assert rep_roles.behavioral_review_required is True
    assert any(
        f.rule_id == CompatibilityRuleId.MESSAGE_ROLE_OR_ORDER_CHANGED for f in rep_roles.findings
    )
