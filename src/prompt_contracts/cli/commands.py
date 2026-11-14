"""CLI command handlers routing directly into public runtime, lock, and compatibility services."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TextIO

from prompt_contracts.cli.reporting import (
    format_diff_report,
    format_lint_report,
    format_lock_report,
    format_render_output,
    format_verify_report,
)
from prompt_contracts.compatibility.compare import compare_contracts
from prompt_contracts.compatibility.models import CompatibilityPolicy
from prompt_contracts.errors import ErrorCode, InputValidationError
from prompt_contracts.identity.lock import read_lock_file, write_lock_atomic
from prompt_contracts.loading.loader import load_contract_from_directory
from prompt_contracts.loading.paths import read_bounded_file_bytes
from prompt_contracts.registry import (
    PromptRegistry,
    generate_lock_for_directory,
    verify_directory_against_lock,
)
from prompt_contracts.types import DEFAULT_RUNTIME_POLICY, ContractRef, RuntimePolicy
from prompt_contracts.validation.json_io import parse_strict_json

__all__ = [
    "EXIT_COMPATIBILITY_FAILURE",
    "EXIT_INTERNAL_ERROR",
    "EXIT_LOCK_OR_IDENTITY_ERROR",
    "EXIT_SUCCESS",
    "EXIT_USAGE_ERROR",
    "EXIT_VALIDATION_ERROR",
    "run_diff_command",
    "run_lint_command",
    "run_lock_command",
    "run_render_command",
    "run_verify_command",
]

EXIT_SUCCESS = 0
EXIT_INTERNAL_ERROR = 1
EXIT_USAGE_ERROR = 2
EXIT_VALIDATION_ERROR = 3
EXIT_LOCK_OR_IDENTITY_ERROR = 4
EXIT_COMPATIBILITY_FAILURE = 5


def run_lint_command(
    contracts_path: Path,
    *,
    output_format: str = "text",
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    stdout: TextIO = sys.stdout,
) -> int:
    """Validate all contract bundles under ``contracts_path``."""
    _, contracts = generate_lock_for_directory(contracts_path, policy=policy)
    report = format_lint_report(contracts, output_format=output_format)
    stdout.write(report + "\n")
    return EXIT_SUCCESS


def run_lock_command(
    contracts_path: Path,
    output_path: Path,
    *,
    allow_update: bool = False,
    output_format: str = "text",
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    stdout: TextIO = sys.stdout,
) -> int:
    """Generate and atomically write a lockfile for ``contracts_path``."""
    lock, _ = generate_lock_for_directory(contracts_path, policy=policy)
    write_lock_atomic(lock, output_path, allow_update=allow_update, policy=policy)
    report = format_lock_report(
        lock,
        output_path.as_posix(),
        output_format=output_format,
    )
    stdout.write(report + "\n")
    return EXIT_SUCCESS


def run_verify_command(
    contracts_path: Path,
    lock_path: Path,
    *,
    output_format: str = "text",
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    stdout: TextIO = sys.stdout,
) -> int:
    """Verify all contract bundles under ``contracts_path`` against ``lock_path``."""
    lock = read_lock_file(lock_path, policy=policy)
    verified = verify_directory_against_lock(contracts_path, lock, policy=policy)
    report = format_verify_report(
        verified,
        lock_path.as_posix(),
        output_format=output_format,
    )
    stdout.write(report + "\n")
    return EXIT_SUCCESS


def run_render_command(
    contracts_path: Path,
    *,
    lock_path: Path,
    ref_str: str,
    input_file: str,
    output_format: str = "json",
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
) -> int:
    """Verify lock, load ``ref_str``, validate inputs from ``input_file`` (or ``-``), and emit
    rendered messages.
    """
    ref = ContractRef.parse(ref_str)
    registry = PromptRegistry.from_directory(
        root=contracts_path,
        lock_file=lock_path.resolve(),
        policy=policy,
    )
    registry.freeze()
    contract = registry.get(ref)

    if input_file == "-":
        raw_input: str | bytes = stdin.read(policy.max_input_bytes + 1)
    else:
        in_path = Path(input_file)
        raw_input = read_bounded_file_bytes(
            in_path,
            max_bytes=policy.max_input_bytes,
            logical_path=in_path.name,
            contract_ref=str(ref),
        )

    parsed_inputs = parse_strict_json(
        raw_input,
        max_bytes=policy.max_input_bytes,
        max_depth=policy.max_nesting_depth,
        error_cls=InputValidationError,
        contract_ref=str(ref),
    )
    if not isinstance(parsed_inputs, dict):
        raise InputValidationError(
            "Input JSON document must be an object",
            code=ErrorCode.INPUT_NOT_OBJECT,
            contract_ref=str(ref),
        )

    rendered = contract.render(parsed_inputs, policy=policy)
    out = format_render_output(rendered, output_format=output_format)
    stdout.write(out + "\n")
    return EXIT_SUCCESS


def run_diff_command(
    old_bundle_path: Path,
    new_bundle_path: Path,
    *,
    policy_mode: CompatibilityPolicy = CompatibilityPolicy.COMPATIBLE_ONLY,
    output_format: str = "text",
    policy: RuntimePolicy = DEFAULT_RUNTIME_POLICY,
    stdout: TextIO = sys.stdout,
) -> int:
    """Compare two contract directories and return exit code 0 or 5 under ``policy_mode``."""
    old_contract = load_contract_from_directory(old_bundle_path, policy=policy)
    new_contract = load_contract_from_directory(new_bundle_path, policy=policy)
    report = compare_contracts(old_contract, new_contract, policy=policy)
    passed = report.passes_policy(policy_mode)
    formatted = format_diff_report(
        report,
        policy_name=str(policy_mode),
        passed=passed,
        output_format=output_format,
    )
    stdout.write(formatted + "\n")
    return EXIT_SUCCESS if passed else EXIT_COMPATIBILITY_FAILURE
