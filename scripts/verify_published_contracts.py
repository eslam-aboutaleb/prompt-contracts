"""Verify that published contract versions remain immutable across lock updates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from prompt_contracts.errors import PromptContractError
from prompt_contracts.identity.lock import read_lock_file
from prompt_contracts.registry import PromptRegistry


def verify_published_immutability(
    baseline_lock_path: Path,
    candidate_lock_path: Path,
    *,
    contracts_dir: Path | None = None,
) -> list[str]:
    """Compare ``baseline_lock_path`` against ``candidate_lock_path`` and return violations."""
    violations: list[str] = []
    try:
        baseline = read_lock_file(baseline_lock_path)
    except PromptContractError as exc:
        return [f"Baseline lock error ({exc.code}): {exc.safe_message}"]

    try:
        candidate = read_lock_file(candidate_lock_path)
    except PromptContractError as exc:
        return [f"Candidate lock error ({exc.code}): {exc.safe_message}"]

    if contracts_dir is not None:
        try:
            PromptRegistry.from_directory(contracts_dir, lock_file=candidate_lock_path)
        except PromptContractError as exc:
            violations.append(
                "Candidate lock does not match contracts "
                f"directory ({exc.code}): {exc.safe_message}"
            )

    candidate_by_ref = {entry.ref: entry for entry in candidate.contracts}
    for base_entry in baseline.contracts:
        cand_entry = candidate_by_ref.get(base_entry.ref)
        if cand_entry is None:
            violations.append(
                f"Published contract {base_entry.ref} was deleted from candidate lockfile"
            )
            continue
        if cand_entry.bundle_digest != base_entry.bundle_digest:
            violations.append(
                f"Published contract {base_entry.ref} mutated in place: "
                f"baseline digest {base_entry.bundle_digest} != "
                f"candidate digest {cand_entry.bundle_digest}"
            )

    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify that published contract versions in a baseline lock are unchanged."
    )
    parser.add_argument(
        "--baseline-lock",
        type=Path,
        required=True,
        help="Path to the baseline/published contracts.lock.json.",
    )
    parser.add_argument(
        "--candidate-lock",
        type=Path,
        required=True,
        help="Path to the candidate contracts.lock.json.",
    )
    parser.add_argument(
        "--contracts-dir",
        type=Path,
        default=None,
        help="Optional contracts directory to verify against the candidate lock.",
    )
    args = parser.parse_args(argv)

    violations = verify_published_immutability(
        args.baseline_lock,
        args.candidate_lock,
        contracts_dir=args.contracts_dir,
    )
    if violations:
        for violation in violations:
            sys.stderr.write(f"IMMUTABILITY VIOLATION: {violation}\n")
        return 1

    sys.stdout.write("Published contract immutability verification passed.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
