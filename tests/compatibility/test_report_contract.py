"""Tests for CompatibilityReport structure, status combination, and policy checks (T25, AC-16)."""

from __future__ import annotations

import json
from pathlib import Path

from prompt_contracts import (
    CompatibilityPolicy,
    CompatibilityStatus,
    PromptRegistry,
    compare_contracts,
)


def test_compatibility_report_structure_and_behavioral_flag(
    repo_root: Path,
) -> None:
    ace_dir = repo_root / "tests" / "fixtures" / "consumers" / "ace_your_interview"
    reg = PromptRegistry.from_directory(
        ace_dir / "contracts",
        lock_file=ace_dir / "contracts.lock.json",
    )
    old_c = reg.get("study.topic-language-advisor@1.0.0")
    new_c = reg.get("study.topic-language-advisor@1.1.0")

    report = compare_contracts(old_c, new_c)
    assert report.input_status is CompatibilityStatus.COMPATIBLE
    assert report.output_status is CompatibilityStatus.COMPATIBLE
    assert report.overall_status is CompatibilityStatus.COMPATIBLE
    assert report.behavioral_review_required is True
    assert report.passes_policy(CompatibilityPolicy.COMPATIBLE_ONLY) is True
    assert report.passes_policy(CompatibilityPolicy.REPORT_ONLY) is True

    payload = json.loads(report.to_json())
    assert payload["old_ref"] == "study.topic-language-advisor@1.0.0"
    assert payload["new_ref"] == "study.topic-language-advisor@1.1.0"
    assert payload["behavioral_review_required"] is True
