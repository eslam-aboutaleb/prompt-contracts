"""Argument parser and entry point for ``prompt-contracts`` CLI."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn, TextIO

from prompt_contracts.cli.commands import (
    EXIT_INTERNAL_ERROR,
    EXIT_USAGE_ERROR,
    run_diff_command,
    run_lint_command,
    run_lock_command,
    run_render_command,
    run_verify_command,
)
from prompt_contracts.cli.reporting import format_error_report
from prompt_contracts.compatibility.models import CompatibilityPolicy
from prompt_contracts.errors import PromptContractError

__all__ = ["build_parser", "main", "run_cli"]


class _CLIArgumentParser(argparse.ArgumentParser):
    """Custom ArgumentParser that exits with code 2 on usage errors."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        sys.stderr.write(f"prompt-contracts: error: {message}\n")
        raise SystemExit(EXIT_USAGE_ERROR)


def build_parser() -> argparse.ArgumentParser:
    """Construct the ``prompt-contracts`` CLI parser."""
    from prompt_contracts import __version__

    parser = _CLIArgumentParser(
        prog="prompt-contracts",
        description="Explicit, versioned, immutable prompt contracts CLI.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"prompt-contracts {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # lint
    lint_parser = subparsers.add_parser(
        "lint",
        help="Validate contract manifests, schemas, templates, and asset closure.",
    )
    lint_parser.add_argument(
        "contracts_dir",
        type=Path,
        help="Path to contracts directory or single contract bundle.",
    )
    lint_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Output report format (default: text).",
    )

    # lock
    lock_parser = subparsers.add_parser(
        "lock",
        help="Compute pc-bundle-v1 digests and write an atomic lockfile.",
    )
    lock_parser.add_argument(
        "contracts_dir",
        type=Path,
        help="Path to contracts directory.",
    )
    lock_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination path for contracts.lock.json.",
    )
    lock_parser.add_argument(
        "--update",
        action="store_true",
        help="Allow replacing an existing lockfile whose contents differ.",
    )
    lock_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Output report format (default: text).",
    )

    # verify
    verify_parser = subparsers.add_parser(
        "verify",
        help="Verify contract bundles on disk against a trusted lockfile.",
    )
    verify_parser.add_argument(
        "contracts_dir",
        type=Path,
        help="Path to contracts directory.",
    )
    verify_parser.add_argument(
        "--lock",
        type=Path,
        required=True,
        dest="lock_file",
        help="Path to contracts.lock.json.",
    )
    verify_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Output report format (default: text).",
    )

    # render
    render_parser = subparsers.add_parser(
        "render",
        help="Verify lock, validate inputs from file/stdin, and render ordered messages.",
    )
    render_parser.add_argument(
        "contracts_dir",
        type=Path,
        help="Path to contracts directory.",
    )
    render_parser.add_argument(
        "--lock",
        type=Path,
        required=True,
        dest="lock_file",
        help="Path to contracts.lock.json.",
    )
    render_parser.add_argument(
        "--ref",
        type=str,
        required=True,
        dest="contract_ref",
        help="Exact contract reference '<name>@<version>'.",
    )
    render_parser.add_argument(
        "--input-file",
        type=str,
        required=True,
        help=(
            "Path to JSON input file, or '-' for stdin (never pass raw values on the command line)."
        ),
    )
    render_parser.add_argument(
        "--format",
        choices=("json", "text"),
        default="json",
        dest="output_format",
        help="Rendered output format (default: json).",
    )

    # diff
    diff_parser = subparsers.add_parser(
        "diff",
        help="Analyze directional compatibility between two contract bundle directories.",
    )
    diff_parser.add_argument(
        "old_dir",
        type=Path,
        help="Path to baseline/old contract version directory.",
    )
    diff_parser.add_argument(
        "new_dir",
        type=Path,
        help="Path to candidate/new contract version directory.",
    )
    diff_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Report format (default: text).",
    )
    diff_parser.add_argument(
        "--policy",
        choices=("compatible-only", "report-only"),
        default="compatible-only",
        dest="policy_mode",
        help="Promotion policy (default: compatible-only, exits 5 on breaking or unknown).",
    )

    return parser


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Execute the CLI and return the documented integer exit code."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    stderr = stderr if stderr is not None else sys.stderr
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else EXIT_USAGE_ERROR

    cmd = str(args.command)
    out_fmt = str(getattr(args, "output_format", "text"))

    try:
        if cmd == "lint":
            return run_lint_command(
                args.contracts_dir,
                output_format=out_fmt,
                stdout=stdout,
            )
        if cmd == "lock":
            return run_lock_command(
                args.contracts_dir,
                args.output,
                allow_update=bool(args.update),
                output_format=out_fmt,
                stdout=stdout,
            )
        if cmd == "verify":
            return run_verify_command(
                args.contracts_dir,
                args.lock_file,
                output_format=out_fmt,
                stdout=stdout,
            )
        if cmd == "render":
            return run_render_command(
                args.contracts_dir,
                lock_path=args.lock_file,
                ref_str=args.contract_ref,
                input_file=args.input_file,
                output_format=out_fmt,
                stdin=stdin,
                stdout=stdout,
            )
        if cmd == "diff":
            return run_diff_command(
                args.old_dir,
                args.new_dir,
                policy_mode=CompatibilityPolicy(args.policy_mode),
                output_format=out_fmt,
                stdout=stdout,
            )
        stderr.write(f"prompt-contracts: error: unknown command {cmd!r}\n")
        return EXIT_USAGE_ERROR
    except PromptContractError as exc:
        err_out_fmt = "json" if out_fmt == "json" and cmd != "render" else "text"
        report = format_error_report(exc, command=cmd, output_format=err_out_fmt)
        target_stream = stdout if err_out_fmt == "json" else stderr
        target_stream.write(report + "\n")
        return exc.exit_code
    except Exception:
        stderr.write(
            "[PC_INTERNAL_ERROR] An unexpected internal error "
            "occurred (details suppressed for data safety).\n"
        )
        return EXIT_INTERNAL_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    """Console script entry point."""
    code = run_cli(argv)
    if argv is None:
        raise SystemExit(code)
    return code
