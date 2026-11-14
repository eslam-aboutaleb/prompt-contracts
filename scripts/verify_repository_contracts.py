"""Preserve every contract locked in a trusted Git baseline, even after lock regeneration."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from prompt_contracts import PromptContractError
from prompt_contracts.identity.lock import parse_lock_bytes, read_lock_file


def verify_repository_contracts(repo: Path, baseline_ref: str) -> list[str]:
    """Compare tracked baseline catalogs with current files; missing catalogs fail closed."""
    if baseline_ref == "0" * 40:
        # GitHub's initial-push sentinel: there is no previous published catalog.
        return []
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{baseline_ref}^{{commit}}"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    if resolved.returncode:
        return ["Trusted baseline commit cannot be resolved"]
    commit = resolved.stdout.strip()
    tree = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", commit],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    errors: list[str] = []
    for path in tree.stdout.splitlines():
        if Path(path).name != "contracts.lock.json":
            continue
        raw = subprocess.run(
            ["git", "show", f"{commit}:{path}"],
            cwd=repo,
            capture_output=True,
            check=True,
        ).stdout
        try:
            baseline = parse_lock_bytes(raw)
            candidate = read_lock_file(repo / path)
        except PromptContractError as exc:
            errors.append(f"Catalog {path} is missing or invalid ({exc.code})")
            continue
        current = {entry.ref: entry.bundle_digest for entry in candidate.contracts}
        for entry in baseline.contracts:
            if current.get(entry.ref) != entry.bundle_digest:
                errors.append(f"Published contract {entry.ref} was removed or modified in {path}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = verify_repository_contracts(args.repo, args.baseline_ref)
    for error in errors:
        sys.stderr.write(error + "\n")
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
