"""Compare evaluation module - Compare multiple LLM answers against reference."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from src.io.storage import Storage
from src.core.evaluator import Evaluator
from src.domain.models import Question

logger = logging.getLogger(__name__)


def run_compare(
    question: Question,
    human_answer_content: str,
    llm_answers: Dict[str, str],  # model_name -> answer_content
    evaluator: Evaluator,
    store: Storage,
    topic_dir: Path,
    primary_model: str,
) -> Optional[Tuple[str, dict]]:
    """
    Compare multiple LLM answers against the human reference answer.

    Args:
        question: The question being evaluated
        human_answer_content: The reference (human) answer
        llm_answers: Dict mapping model names to their answer content
        evaluator: The evaluator instance for LLM calls
        store: Storage instance for saving results
        topic_dir: Directory for this question
        primary_model: The primary model (used for naming the comparison result)

    Returns:
        Tuple of (comparison_result, raw_response) or None if skipped
    """
    if not human_answer_content:
        logger.warning("No reference answer for comparison")
        return None

    if len(llm_answers) < 1:
        logger.warning("No LLM answers to compare")
        return None

    from src.conf.prompts import COMPARE_SYSTEM_PROMPT, COMPARE_USER_TEMPLATE
    from src.utils.text import html_to_text

    # Build question text
    question_text = f"**Title:** {question.title}\n\n**Body:**\n{html_to_text(question.body)}"

    # Build candidates section
    candidates_parts = []
    model_names = sorted(llm_answers.keys())
    for i, model_name in enumerate(model_names):
        label = chr(ord('A') + i)  # A, B, C, ...
        candidates_parts.append(f"**[Candidate {label}: {model_name}]**:\n{llm_answers[model_name]}")

    candidates_text = "\n\n".join(candidates_parts)

    # Format user message
    user_content = COMPARE_USER_TEMPLATE.format(
        question=question_text,
        reference_answer=human_answer_content,
        candidates=candidates_text,
    )

    messages = [
        {"role": "system", "content": COMPARE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # Call LLM
    comparison_result, raw_resp = evaluator.llm_client.chat_completion_full(messages)

    # Save comparison result
    store.save_comparison_result(topic_dir, primary_model, comparison_result, raw_resp, question)

    return comparison_result, raw_resp


def find_llm_answers(
    store: Storage,
    topic_dir: Path,
    question: Question,
    csv_mode: bool = False,
) -> Dict[str, str]:
    """
    Find all available LLM answers for a question.

    Only includes pure LLM answer files (e.g., gpt5_1_answer.md),
    excludes evaluation files (e.g., gpt5_1_evaluate_gpt5_1_answer.md).

    Returns:
        Dict mapping model names to their answer content
    """
    llm_answers = {}

    # Method 1: Look for *_answer.md files in topic_dir (excluding *_evaluate_*_answer.md)
    if topic_dir.exists():
        for answer_file in topic_dir.glob("*_answer.md"):
            filename = answer_file.stem  # e.g., "gpt5_1_answer" or "gpt5_1_evaluate_gpt5_1_answer"

            # Skip question_answer.md (human answers from Stack Overflow)
            if filename == "question_answer":
                continue

            # Skip evaluation files (contain "_evaluate_")
            if "_evaluate_" in filename:
                continue

            # Skip compare files
            if "_compare" in filename:
                continue

            # Must end with _answer (check there's something before it)
            if not filename.endswith("_answer"):
                continue

            # Extract model token from filename (e.g., gpt5_1_answer -> gpt5_1)
            model_token = filename.replace("_answer", "")
            if not model_token:  # Empty token means just "answer.md"
                continue

            content = answer_file.read_text(encoding="utf-8")
            if content.strip():
                llm_answers[model_token] = content

    # Method 2: Check CSV columns for *_Answer pattern (excluding *_Evaluate_*_Answer)
    # Only load from CSV if not already found from files
    if store.out_csv and store.out_csv.exists():
        try:
            import pandas as pd
            from src.utils.model_name import model_token as get_model_token

            df = pd.read_csv(store.out_csv)

            # Find the row for this question
            q_id = question.question_id
            row = df[df["Question ID"] == q_id]

            if not row.empty:
                row = row.iloc[0]
                # Find columns ending with _Answer (but not _Evaluate_*_Answer or _Answer_CodeBlocks)
                for col in df.columns:
                    # Must end with _Answer
                    if not col.endswith("_Answer"):
                        continue
                    # Skip CodeBlocks columns
                    if col.endswith("_Answer_CodeBlocks"):
                        continue
                    # Skip Evaluate columns (contain "_Evaluate_")
                    if "_Evaluate_" in col:
                        continue

                    model_name = col.replace("_Answer", "")
                    # Convert to token format for consistent keys (gpt-5.1 -> gpt5_1)
                    token_key = get_model_token(model_name)

                    value = row[col]
                    if pd.notna(value) and str(value).strip():
                        # Use token_key for lookup to avoid duplicates with file-based entries
                        if token_key not in llm_answers:
                            llm_answers[token_key] = str(value)
        except Exception as e:
            logger.debug("Could not read LLM answers from CSV: %s", e)

    return llm_answers

