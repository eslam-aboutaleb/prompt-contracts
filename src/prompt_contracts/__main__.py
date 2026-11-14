"""Allow running the CLI via ``python -m prompt_contracts``."""

from __future__ import annotations

import sys

from prompt_contracts.cli.main import run_cli

if __name__ == "__main__":
    raise SystemExit(run_cli(sys.argv[1:]))
