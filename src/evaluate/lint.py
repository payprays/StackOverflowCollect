"""Lint evaluation module - YAML syntax validation using kubeval, datree, kubectl."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple, List

from src.io.storage import Storage
from src.domain.models import Question

logger = logging.getLogger(__name__)


def run_lint(
    llm_answer_content: str,
    store: Storage,
    topic_dir: Path,
    question: Question,
    model: str,
) -> Tuple[str, str, str]:
    """
    Run lint checks on LLM answer content.

    Returns:
        Tuple of (lint_result, code_blocks, detailed_logs)
    """
    from src.utils.yaml_lint import lint_answer_full

    lint_result, code_blocks, detailed_logs = lint_answer_full(llm_answer_content)

    # Save results
    store.save_lint_result(
        topic_dir, question, model, lint_result, code_blocks, detailed_logs
    )

    return lint_result, code_blocks, detailed_logs
