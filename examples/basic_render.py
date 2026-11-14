"""Offline contract loading, lock verification, rendering, and output validation example."""

from __future__ import annotations

import json
from pathlib import Path

from prompt_contracts import ContractRef, PromptRegistry


def run_basic_example() -> dict[str, object]:
    """Load the example contract with lock verification, render messages, and validate a JSON
    output.
    """
    examples_dir = Path(__file__).resolve().parent
    registry = PromptRegistry.from_directory(
        root=examples_dir,
        lock_file="contracts.lock.json",
    )
    registry.freeze()

    contract = registry.get(ContractRef("career.application-answer", "1.0.0"))
    rendered = contract.render(
        {
            "question": "Describe your database experience.",
            "verified_facts": "fact-1: Maintained PostgreSQL migrations.",
        }
    )

    sample_response = json.dumps(
        {
            "answer": "I maintained PostgreSQL schema migrations in production.",
            "evidence_ids": ["fact-1"],
            "needs_review": False,
        }
    )
    validated = contract.validate_output(sample_response)
    return {
        "contract_ref": str(rendered.contract_ref),
        "bundle_digest": rendered.bundle_digest,
        "messages": rendered.to_messages_list(),
        "validated_output": validated,
    }


if __name__ == "__main__":
    result = run_basic_example()
    print(json.dumps(result, indent=2))
