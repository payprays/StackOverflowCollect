"""LLM evaluation module - Use LLM to evaluate answer quality."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple, Optional

from src.io.storage import Storage
from src.core.evaluator import Evaluator
from src.domain.models import Question

logger = logging.getLogger(__name__)


def run_llm_eval(
    question: Question,
    human_answer_content: str,
    llm_answer_content: str,
    evaluator: Evaluator,
    store: Storage,
    topic_dir: Path,
    model: str,
    force: bool = False,
) -> Optional[Tuple[str, dict]]:
    """
    Run LLM-based evaluation of the answer quality.
    
    Returns:
        Tuple of (evaluation, raw_response) or None if skipped
    """
    if not force and store.has_evaluation(topic_dir, model, model):
        logger.info("Evaluation already exists, skipping")
        return None
    
    # Format Q&A includes question + human answer as reference
    formatted_qa = Storage._format_question_answers(question, human_answer_content)
    
    evaluation, raw_resp = evaluator.evaluate(
        formatted_qa, llm_answer_content, model
    )
    
    # Save results
    store.save_evaluation(topic_dir, model, model, evaluation, raw_resp)
    
    return evaluation, raw_resp
