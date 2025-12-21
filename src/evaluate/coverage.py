"""Coverage evaluation module - Compare LLM answer vs human answer YAML coverage."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from src.io.storage import Storage
from src.core.evaluator import Evaluator
from src.domain.models import Question

logger = logging.getLogger(__name__)


def run_coverage(
    human_answer_content: str,
    llm_answer_content: str,
    evaluator: Evaluator,
    store: Storage,
    topic_dir: Path,
    question: Question,
    model: str,
) -> Optional[Dict[str, Any]]:
    """
    Run coverage check comparing LLM answer against human answer.
    
    Returns:
        Coverage results dict or None if no human answer
    """
    if not human_answer_content:
        logger.warning("No human answer for coverage check")
        return None
    
    coverage_results = evaluator.check_coverage(human_answer_content, llm_answer_content)
    
    # Save results
    store.save_coverage_result(topic_dir, model, coverage_results, question)
    
    return coverage_results
