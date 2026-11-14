"""Promptfoo custom Python provider delegating to the production ``prompt-contracts`` renderer."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

# Ensure repo src/ is importable when invoked by the external Promptfoo Node CLI
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _REPO_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from prompt_contracts.adapters.gateway import GatewayRequest  # noqa: E402
from prompt_contracts.adapters.promptfoo import (  # noqa: E402
    execute_promptfoo_case,
    parse_promptfoo_provider_config,
)
from prompt_contracts.types import RenderedPrompt  # noqa: E402


def _default_offline_responder(
    _rendered: RenderedPrompt,
    _request: GatewayRequest,
    context_vars: Mapping[str, Any],
) -> str:
    if "_mock_response" in context_vars and isinstance(context_vars["_mock_response"], str):
        return context_vars["_mock_response"]
    question = str(context_vars.get("question", ""))
    return json.dumps(
        {
            "answer": f"Offline grounded response for: {question}",
            "evidence_ids": ["fact-1"],
            "needs_review": False,
        }
    )


def call_api(
    prompt: str,
    options: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Promptfoo Python provider entry point ``call_api(prompt, options, context)``."""
    _ = prompt  # Sentinel only; rendering uses typed context['vars'] via Contract.render
    examples_dir = Path(__file__).resolve().parent.parent
    cfg = parse_promptfoo_provider_config(options, allowed_base_dir=examples_dir)
    raw_vars = context.get("vars", {}) if isinstance(context, Mapping) else {}
    vars_map = raw_vars if isinstance(raw_vars, Mapping) else {}

    result = execute_promptfoo_case(
        config=cfg,
        context_vars=vars_map,
        offline_responder=_default_offline_responder,
    )
    provider_config = options.get("config", {}) if isinstance(options, Mapping) else {}
    include_rendered = (
        isinstance(provider_config, Mapping)
        and provider_config.get("include_rendered_prompt") is True
    )
    return result.to_promptfoo_response(include_rendered_prompt=include_rendered)
