"""Data models and rule identifiers for directional contract compatibility reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from prompt_contracts.types import ContractRef

__all__ = [
    "COMPATIBILITY_REPORT_FORMAT",
    "CompatibilityDirection",
    "CompatibilityFinding",
    "CompatibilityPolicy",
    "CompatibilityReport",
    "CompatibilityRuleId",
    "CompatibilityStatus",
]

COMPATIBILITY_REPORT_FORMAT = 1


class CompatibilityStatus(StrEnum):
    """Conservative directional compatibility status."""

    COMPATIBLE = "compatible"
    BREAKING = "breaking"
    UNKNOWN = "unknown"


class CompatibilityDirection(StrEnum):
    """Direction of a compatibility finding."""

    INPUT = "input"
    OUTPUT = "output"
    BEHAVIORAL = "behavioral"


class CompatibilityPolicy(StrEnum):
    """CLI and CI promotion policy for compatibility checks."""

    COMPATIBLE_ONLY = "compatible-only"
    REPORT_ONLY = "report-only"


class CompatibilityRuleId:
    """Stable rule identifiers emitted in compatibility findings."""

    # Properties & Required
    REQUIRED_PROPERTY_ADDED = "PC_COMPAT_REQUIRED_PROPERTY_ADDED"
    REQUIRED_PROPERTY_REMOVED = "PC_COMPAT_REQUIRED_PROPERTY_REMOVED"
    OPTIONAL_PROPERTY_ADDED = "PC_COMPAT_OPTIONAL_PROPERTY_ADDED"
    OPTIONAL_PROPERTY_REMOVED = "PC_COMPAT_OPTIONAL_PROPERTY_REMOVED"
    OPTIONAL_PROMOTED_TO_REQUIRED = "PC_COMPAT_OPTIONAL_PROMOTED_TO_REQUIRED"
    REQUIRED_DEMOTED_TO_OPTIONAL = "PC_COMPAT_REQUIRED_DEMOTED_TO_OPTIONAL"
    ADDITIONAL_PROPERTIES_CHANGED = "PC_COMPAT_ADDITIONAL_PROPERTIES_CHANGED"

    # Types, Enums, Consts
    TYPE_WIDENED = "PC_COMPAT_TYPE_WIDENED"
    TYPE_NARROWED = "PC_COMPAT_TYPE_NARROWED"
    TYPE_CHANGED_INCOMPATIBLE = "PC_COMPAT_TYPE_CHANGED_INCOMPATIBLE"
    ENUM_WIDENED = "PC_COMPAT_ENUM_WIDENED"
    ENUM_NARROWED = "PC_COMPAT_ENUM_NARROWED"
    ENUM_CHANGED_INCOMPATIBLE = "PC_COMPAT_ENUM_CHANGED_INCOMPATIBLE"
    CONST_CHANGED = "PC_COMPAT_CONST_CHANGED"

    # Bounds
    STRING_MIN_LENGTH_RAISED = "PC_COMPAT_STRING_MIN_LENGTH_RAISED"
    STRING_MIN_LENGTH_LOWERED = "PC_COMPAT_STRING_MIN_LENGTH_LOWERED"
    STRING_MAX_LENGTH_LOWERED = "PC_COMPAT_STRING_MAX_LENGTH_LOWERED"
    STRING_MAX_LENGTH_RAISED = "PC_COMPAT_STRING_MAX_LENGTH_RAISED"
    ARRAY_MIN_ITEMS_RAISED = "PC_COMPAT_ARRAY_MIN_ITEMS_RAISED"
    ARRAY_MIN_ITEMS_LOWERED = "PC_COMPAT_ARRAY_MIN_ITEMS_LOWERED"
    ARRAY_MAX_ITEMS_LOWERED = "PC_COMPAT_ARRAY_MAX_ITEMS_LOWERED"
    ARRAY_MAX_ITEMS_RAISED = "PC_COMPAT_ARRAY_MAX_ITEMS_RAISED"
    NUMBER_MIN_RAISED = "PC_COMPAT_NUMBER_MIN_RAISED"
    NUMBER_MIN_LOWERED = "PC_COMPAT_NUMBER_MIN_LOWERED"
    NUMBER_MAX_LOWERED = "PC_COMPAT_NUMBER_MAX_LOWERED"
    NUMBER_MAX_RAISED = "PC_COMPAT_NUMBER_MAX_RAISED"

    # Output Mode & Text Bounds
    OUTPUT_MODE_CHANGED = "PC_COMPAT_OUTPUT_MODE_CHANGED"
    TEXT_LENGTH_NARROWED = "PC_COMPAT_TEXT_LENGTH_NARROWED"
    TEXT_LENGTH_WIDENED = "PC_COMPAT_TEXT_LENGTH_WIDENED"

    # Behavioral & Format
    MESSAGE_CONTENT_CHANGED = "PC_COMPAT_MESSAGE_CONTENT_CHANGED"
    MESSAGE_ROLE_OR_ORDER_CHANGED = "PC_COMPAT_MESSAGE_ROLE_OR_ORDER_CHANGED"
    PLACEHOLDER_SET_CHANGED = "PC_COMPAT_PLACEHOLDER_SET_CHANGED"
    FORMAT_OR_RENDERER_CHANGED = "PC_COMPAT_FORMAT_OR_RENDERER_CHANGED"

    # Unprovable combinations
    UNKNOWN_COMBINATION = "PC_COMPAT_UNKNOWN_COMBINATION"


def combine_statuses(statuses: list[CompatibilityStatus]) -> CompatibilityStatus:
    """Combine multiple status values conservatively (``breaking`` > ``unknown`` >
    ``compatible``).
    """
    if CompatibilityStatus.BREAKING in statuses:
        return CompatibilityStatus.BREAKING
    if CompatibilityStatus.UNKNOWN in statuses:
        return CompatibilityStatus.UNKNOWN
    return CompatibilityStatus.COMPATIBLE


@dataclass(frozen=True, slots=True)
class CompatibilityFinding:
    """Single directional compatibility finding at a schema or manifest path."""

    direction: CompatibilityDirection
    status: CompatibilityStatus
    rule_id: str
    path: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "direction": str(self.direction),
            "message": self.message,
            "path": self.path,
            "rule_id": self.rule_id,
            "status": str(self.status),
        }


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    """Directional compatibility report between an old and new contract snapshot."""

    old_ref: ContractRef
    new_ref: ContractRef
    old_bundle_digest: str
    new_bundle_digest: str
    input_status: CompatibilityStatus
    output_status: CompatibilityStatus
    behavioral_review_required: bool
    findings: tuple[CompatibilityFinding, ...]
    report_format: int = COMPATIBILITY_REPORT_FORMAT

    @property
    def overall_status(self) -> CompatibilityStatus:
        """Combined structural status across input and output directions."""
        return combine_statuses([self.input_status, self.output_status])

    def passes_policy(
        self, policy: CompatibilityPolicy = CompatibilityPolicy.COMPATIBLE_ONLY
    ) -> bool:
        """Return ``True`` if the report satisfies ``policy``."""
        if policy == CompatibilityPolicy.REPORT_ONLY:
            return True
        return (
            self.input_status == CompatibilityStatus.COMPATIBLE
            and self.output_status == CompatibilityStatus.COMPATIBLE
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_format": self.report_format,
            "old_ref": str(self.old_ref),
            "new_ref": str(self.new_ref),
            "old_bundle_digest": self.old_bundle_digest,
            "new_bundle_digest": self.new_bundle_digest,
            "input_status": str(self.input_status),
            "output_status": str(self.output_status),
            "overall_status": str(self.overall_status),
            "behavioral_review_required": self.behavioral_review_required,
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)
