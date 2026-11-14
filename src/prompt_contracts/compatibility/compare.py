"""Contract-to-contract directional compatibility analyzer."""

from __future__ import annotations

from prompt_contracts.compatibility.models import (
    CompatibilityDirection,
    CompatibilityFinding,
    CompatibilityReport,
    CompatibilityRuleId,
    CompatibilityStatus,
    combine_statuses,
)
from prompt_contracts.compatibility.rules import compare_expanded_schemas
from prompt_contracts.contract import Contract
from prompt_contracts.types import DEFAULT_RUNTIME_POLICY, OutputMode, RuntimePolicy
from prompt_contracts.validation.profile import expand_schema_node

__all__ = ["compare_contracts"]


def compare_contracts(
    old_contract: Contract,
    new_contract: Contract,
    *,
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
) -> CompatibilityReport:
    """Analyze directional input/output compatibility and behavioral review requirements between
    two contracts.
    """
    findings: list[CompatibilityFinding] = []
    behavioral_review_required = False

    # 1. Check format version & renderer
    if (
        old_contract.format_version != new_contract.format_version
        or old_contract.renderer != new_contract.renderer
    ):
        behavioral_review_required = True
        findings.append(
            CompatibilityFinding(
                direction=CompatibilityDirection.INPUT,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.FORMAT_OR_RENDERER_CHANGED,
                path="$.manifest",
                message="Contract format_version or renderer changed; requires explicit migration",
            )
        )
        findings.append(
            CompatibilityFinding(
                direction=CompatibilityDirection.OUTPUT,
                status=CompatibilityStatus.UNKNOWN,
                rule_id=CompatibilityRuleId.FORMAT_OR_RENDERER_CHANGED,
                path="$.manifest",
                message="Contract format_version or renderer changed; requires explicit migration",
            )
        )
        return CompatibilityReport(
            old_ref=old_contract.ref,
            new_ref=new_contract.ref,
            old_bundle_digest=old_contract.bundle_digest,
            new_bundle_digest=new_contract.bundle_digest,
            input_status=CompatibilityStatus.UNKNOWN,
            output_status=CompatibilityStatus.UNKNOWN,
            behavioral_review_required=True,
            findings=tuple(findings),
        )

    # 2. Input schema directional analysis (I_old <= I_new)
    old_in_expanded, _ = expand_schema_node(
        old_contract._compiled_input_schema.raw_schema,
        policy=policy,
        contract_ref=str(old_contract.ref),
    )
    new_in_expanded, _ = expand_schema_node(
        new_contract._compiled_input_schema.raw_schema,
        policy=policy,
        contract_ref=str(new_contract.ref),
    )
    input_status, input_findings = compare_expanded_schemas(
        old_in_expanded,
        new_in_expanded,
        direction=CompatibilityDirection.INPUT,
    )
    findings.extend(input_findings)

    # 3. Output mode & schema directional analysis (O_new <= O_old)
    old_out = old_contract.output_spec
    new_out = new_contract.output_spec
    output_statuses: list[CompatibilityStatus] = []

    if old_out.mode != new_out.mode:
        behavioral_review_required = True
        output_statuses.append(CompatibilityStatus.BREAKING)
        findings.append(
            CompatibilityFinding(
                direction=CompatibilityDirection.OUTPUT,
                status=CompatibilityStatus.BREAKING,
                rule_id=CompatibilityRuleId.OUTPUT_MODE_CHANGED,
                path="$.output.mode",
                message=f"Output mode changed from {old_out.mode!r} to {new_out.mode!r}",
            )
        )
    elif old_out.mode == OutputMode.TEXT:
        assert old_out.min_length is not None and old_out.max_length is not None
        assert new_out.min_length is not None and new_out.max_length is not None
        if new_out.min_length < old_out.min_length or new_out.max_length > old_out.max_length:
            output_statuses.append(CompatibilityStatus.BREAKING)
            findings.append(
                CompatibilityFinding(
                    direction=CompatibilityDirection.OUTPUT,
                    status=CompatibilityStatus.BREAKING,
                    rule_id=CompatibilityRuleId.TEXT_LENGTH_WIDENED,
                    path="$.output",
                    message=(
                        f"Text output length bounds widened from "
                        f"[{old_out.min_length}, {old_out.max_length}] to "
                        f"[{new_out.min_length}, {new_out.max_length}]"
                    ),
                )
            )
        elif new_out.min_length > old_out.min_length or new_out.max_length < old_out.max_length:
            output_statuses.append(CompatibilityStatus.COMPATIBLE)
            findings.append(
                CompatibilityFinding(
                    direction=CompatibilityDirection.OUTPUT,
                    status=CompatibilityStatus.COMPATIBLE,
                    rule_id=CompatibilityRuleId.TEXT_LENGTH_NARROWED,
                    path="$.output",
                    message=(
                        f"Text output length bounds narrowed from "
                        f"[{old_out.min_length}, {old_out.max_length}] to "
                        f"[{new_out.min_length}, {new_out.max_length}]"
                    ),
                )
            )
        else:
            output_statuses.append(CompatibilityStatus.COMPATIBLE)
    else:
        assert old_contract._compiled_output_schema is not None
        assert new_contract._compiled_output_schema is not None
        old_out_expanded, _ = expand_schema_node(
            old_contract._compiled_output_schema.raw_schema,
            policy=policy,
            contract_ref=str(old_contract.ref),
        )
        new_out_expanded, _ = expand_schema_node(
            new_contract._compiled_output_schema.raw_schema,
            policy=policy,
            contract_ref=str(new_contract.ref),
        )
        out_schema_status, out_schema_findings = compare_expanded_schemas(
            old_out_expanded,
            new_out_expanded,
            direction=CompatibilityDirection.OUTPUT,
        )
        output_statuses.append(out_schema_status)
        findings.extend(out_schema_findings)

    # 4. Template roles, ordering, placeholders, and wording changes
    old_roles = tuple(m.role for m in old_contract.messages)
    new_roles = tuple(m.role for m in new_contract.messages)
    if old_roles != new_roles:
        behavioral_review_required = True
        findings.append(
            CompatibilityFinding(
                direction=CompatibilityDirection.BEHAVIORAL,
                status=CompatibilityStatus.COMPATIBLE,
                rule_id=CompatibilityRuleId.MESSAGE_ROLE_OR_ORDER_CHANGED,
                path="$.messages",
                message=(
                    "Message roles/order changed from "
                    f"{[str(r) for r in old_roles]} to {[str(r) for r in new_roles]}"
                ),
            )
        )
    else:
        for idx, (old_msg, new_msg) in enumerate(
            zip(old_contract.messages, new_contract.messages, strict=True)
        ):
            if old_msg.raw_text != new_msg.raw_text:
                behavioral_review_required = True
                findings.append(
                    CompatibilityFinding(
                        direction=CompatibilityDirection.BEHAVIORAL,
                        status=CompatibilityStatus.COMPATIBLE,
                        rule_id=CompatibilityRuleId.MESSAGE_CONTENT_CHANGED,
                        path=f"$.messages[{idx}]",
                        message=f"Template content changed in message {idx} ({old_msg.role})",
                    )
                )

    old_vars = {v for m in old_contract.messages for v in m.referenced_variables}
    new_vars = {v for m in new_contract.messages for v in m.referenced_variables}
    if old_vars != new_vars:
        behavioral_review_required = True
        findings.append(
            CompatibilityFinding(
                direction=CompatibilityDirection.BEHAVIORAL,
                status=CompatibilityStatus.COMPATIBLE,
                rule_id=CompatibilityRuleId.PLACEHOLDER_SET_CHANGED,
                path="$.messages",
                message=(
                    "Template placeholder set changed from "
                    f"{sorted(old_vars)} to {sorted(new_vars)}"
                ),
            )
        )

    output_status = combine_statuses(output_statuses)
    return CompatibilityReport(
        old_ref=old_contract.ref,
        new_ref=new_contract.ref,
        old_bundle_digest=old_contract.bundle_digest,
        new_bundle_digest=new_contract.bundle_digest,
        input_status=input_status,
        output_status=output_status,
        behavioral_review_required=behavioral_review_required,
        findings=tuple(findings),
    )
