"""Synthetic packaged consumer application for ``prompt-contracts``."""

from __future__ import annotations

from .generation import (
    EvaluationGenerationResult,
    generate_for_evaluation,
    load_consumer_registry,
)

__all__ = [
    "EvaluationGenerationResult",
    "generate_for_evaluation",
    "load_consumer_registry",
]
