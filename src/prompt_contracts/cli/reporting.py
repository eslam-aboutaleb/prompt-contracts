"""Deterministic text and JSON reporting helpers for the CLI."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from prompt_contracts.compatibility.models import CompatibilityReport
from prompt_contracts.contract import Contract
from prompt_contracts.errors import PromptContractError
from prompt_contracts.identity.lock import ContractLock
from prompt_contracts.types import RenderedPrompt

__all__ = [
    "CLI_REPORT_FORMAT",
    "format_diff_report",
    "format_error_report",
    "format_lint_report",
    "format_lock_report",
    "format_render_output",
    "format_verify_report",
]

CLI_REPORT_FORMAT = 1


def format_lint_report(
    contracts: Sequence[Contract],
    *,
    output_format: str = "text",
) -> str:
    """Format a successful ``lint`` report."""
    if output_format == "json":
        payload = {
            "report_format": CLI_REPORT_FORMAT,
            "command": "lint",
            "status": "ok",
            "contract_count": len(contracts),
            "contracts": [
                {
                    "name": c.name,
                    "version": c.version,
                    "ref": str(c.ref),
                    "bundle_digest": c.bundle_digest,
                    "output_mode": str(c.output_spec.mode),
                    "message_count": len(c.messages),
                }
                for c in contracts
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=False)

    lines = [f"Lint passed for {len(contracts)} contract(s):"]
    for c in contracts:
        lines.append(f"  - {c.ref} ({c.bundle_digest})")
    return "\n".join(lines)


def format_lock_report(
    lock: ContractLock,
    output_path: str,
    *,
    output_format: str = "text",
) -> str:
    """Format a successful ``lock`` generation report."""
    if output_format == "json":
        payload = {
            "report_format": CLI_REPORT_FORMAT,
            "command": "lock",
            "status": "ok",
            "lock_file": output_path,
            "contract_count": len(lock.contracts),
            "contracts": [e.to_dict() for e in lock.contracts],
        }
        return json.dumps(payload, indent=2, sort_keys=False)

    return f"Wrote lockfile {output_path} with {len(lock.contracts)} contract(s)."


def format_verify_report(
    contracts: Sequence[Contract],
    lock_path: str,
    *,
    output_format: str = "text",
) -> str:
    """Format a successful ``verify`` report."""
    if output_format == "json":
        payload = {
            "report_format": CLI_REPORT_FORMAT,
            "command": "verify",
            "status": "ok",
            "lock_file": lock_path,
            "contract_count": len(contracts),
            "contracts": [
                {
                    "ref": str(c.ref),
                    "bundle_digest": c.bundle_digest,
                }
                for c in contracts
            ],
        }
        return json.dumps(payload, indent=2, sort_keys=False)

    return f"Verified {len(contracts)} contract(s) against {lock_path}."


def format_render_output(
    rendered: RenderedPrompt,
    *,
    output_format: str = "json",
) -> str:
    """Format rendered prompt output for ``render``."""
    if output_format == "json":
        payload = {
            "report_format": CLI_REPORT_FORMAT,
            "command": "render",
            "contract_ref": str(rendered.contract_ref),
            "bundle_digest": rendered.bundle_digest,
            "renderer": rendered.renderer,
            "policy_id": rendered.policy_id,
            "messages": rendered.to_messages_list(),
        }
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False)

    parts: list[str] = []
    for msg in rendered.messages:
        parts.append(f"[{msg.role}]\n{msg.content}")
    return "\n\n".join(parts)


def format_diff_report(
    report: CompatibilityReport,
    *,
    policy_name: str,
    passed: bool,
    output_format: str = "text",
) -> str:
    """Format a ``diff`` compatibility report."""
    if output_format == "json":
        payload = {
            **report.to_dict(),
            "command": "diff",
            "policy": policy_name,
            "passed_policy": passed,
        }
        return json.dumps(payload, indent=2, sort_keys=False)

    lines = [
        f"Compatibility diff: {report.old_ref} -> {report.new_ref}",
        f"  old digest: {report.old_bundle_digest}",
        f"  new digest: {report.new_bundle_digest}",
        f"  input status: {report.input_status}",
        f"  output status: {report.output_status}",
        f"  overall status: {report.overall_status}",
        f"  behavioral review required: {report.behavioral_review_required}",
        f"  policy ({policy_name}): {'PASS' if passed else 'FAIL'}",
    ]
    if report.findings:
        lines.append("  findings:")
        for finding in report.findings:
            lines.append(
                f"    - [{finding.direction}:{finding.status}] "
                f"{finding.rule_id} at {finding.path}: {finding.message}"
            )
    return "\n".join(lines)


def format_error_report(
    error: PromptContractError,
    *,
    command: str | None = None,
    output_format: str = "text",
) -> str:
    """Format a sanitized CLI error report without rejected values."""
    if output_format == "json":
        payload: dict[str, Any] = {
            "report_format": CLI_REPORT_FORMAT,
            "status": "error",
            **error.to_dict(),
        }
        if command is not None:
            payload["command"] = command
        return json.dumps(payload, indent=2, sort_keys=False)

    lines = [str(error)]
    for issue in error.issues:
        lines.append(f"  - [{issue.code}] {issue.data_path} ({issue.schema_path}): {issue.message}")
    if error.truncated_issue_count > 0:
        lines.append(f"  ... ({error.truncated_issue_count} additional issue(s) truncated)")
    return "\n".join(lines)
