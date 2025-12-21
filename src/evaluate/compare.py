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
    no_reference: bool = False,
) -> Optional[Tuple[str, dict]]:
    """
    Compare multiple LLM answers.

    Args:
        question: The question being evaluated
        human_answer_content: The human answer (used as reference when no_reference=False)
        llm_answers: Dict mapping model names to their answer content
        evaluator: The evaluator instance for LLM calls
        store: Storage instance for saving results
        topic_dir: Directory for this question
        primary_model: The primary model (used for naming the comparison result)
        no_reference: If True, compare only LLM answers (no human reference)
                      If False, use human answer as reference (default)

    Returns:
        Tuple of (comparison_result, raw_response) or None if skipped
    """
    from src.utils.text import html_to_text

    if len(llm_answers) < 1:
        logger.warning("No LLM answers to compare")
        return None

    # Build question text
    question_text = (
        f"**Title:** {question.title}\n\n**Body:**\n{html_to_text(question.body)}"
    )

    # Build candidates section (only LLM answers, no human answer)
    all_candidates = dict(llm_answers)  # Copy
    model_names = sorted(all_candidates.keys())

    if no_reference:
        # NO-REFERENCE MODE: Only compare LLM answers among themselves
        from src.conf.prompts import (
            COMPARE_NO_REF_SYSTEM_PROMPT,
            COMPARE_NO_REF_USER_TEMPLATE,
        )

        # Build candidates section (LLM answers only, no human answer)
        candidates_parts = []
        for name in model_names:
            candidates_parts.append(f"**[{name}]**:\n{all_candidates[name]}")
        candidates_text = "\n\n".join(candidates_parts)

        # Format message for no-reference mode
        user_content = COMPARE_NO_REF_USER_TEMPLATE.format(
            question=question_text,
            candidates=candidates_text,
        )
        system_prompt = COMPARE_NO_REF_SYSTEM_PROMPT
        mode_label = "NO-REFERENCE (LLMs only, no human answer)"

    else:
        # REFERENCE MODE: Use human answer as gold standard
        from src.conf.prompts import COMPARE_SYSTEM_PROMPT, COMPARE_USER_TEMPLATE

        if not human_answer_content:
            logger.warning("No reference answer for comparison")
            return None

        # Build candidates section (LLM answers only)
        candidates_parts = []
        for name in model_names:
            candidates_parts.append(f"**[{name}]**:\n{all_candidates[name]}")
        candidates_text = "\n\n".join(candidates_parts)

        # Format message for reference mode
        user_content = COMPARE_USER_TEMPLATE.format(
            question=question_text,
            reference_answer=human_answer_content,
            candidates=candidates_text,
        )
        system_prompt = COMPARE_SYSTEM_PROMPT
        mode_label = "REFERENCE (human answer as gold standard)"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # Debug logging
    logger.debug("=" * 60)
    logger.debug("COMPARE DEBUG INFO")
    logger.debug("=" * 60)
    logger.debug("Mode: %s", mode_label)
    logger.debug("Question ID: %s", question.question_id)
    logger.debug("Question Title: %s", question.title[:80] if question.title else "N/A")
    logger.debug("Candidates being compared: %s", ", ".join(model_names))
    if not no_reference and human_answer_content:
        logger.debug("Reference answer length: %d chars", len(human_answer_content))
    for name in model_names:
        logger.debug("  - %s answer length: %d chars", name, len(all_candidates[name]))
    logger.debug("System prompt length: %d chars", len(system_prompt))
    logger.debug("User content length: %d chars", len(user_content))
    logger.debug(
        "Total prompt length: ~%d chars", len(system_prompt) + len(user_content)
    )
    logger.debug("=" * 60)

    # Save prompt to file for manual use
    from src.utils.model_name import model_token

    token = model_token(primary_model)
    prompt_filename = f"{token}_compare{'_no_reference' if no_reference else ''}_prompt.txt"
    prompt_content = f"""=== SYSTEM PROMPT ===
{system_prompt}

=== USER PROMPT ===
{user_content}
"""
    (topic_dir / prompt_filename).write_text(prompt_content, encoding="utf-8")
    logger.info("📝 Saved prompt to %s", topic_dir / prompt_filename)

    # Call LLM
    comparison_result, raw_resp = evaluator.llm_client.chat_completion_full(messages)

    # Save comparison result
    store.save_comparison_result(
        topic_dir,
        primary_model,
        comparison_result,
        raw_resp,
        question,
        no_reference=no_reference,
    )

    return comparison_result, raw_resp


def save_compare_prompt_only(
    question: Question,
    human_answer_content: str,
    llm_answers: Dict[str, str],
    topic_dir: Path,
    primary_model: str,
    no_reference: bool = False,
) -> Optional[Path]:
    """
    Save the comparison prompt to a file without calling the LLM.
    Useful for generating prompts for manual use.
    
    Returns:
        Path to the saved prompt file, or None if failed
    """
    from src.utils.text import html_to_text
    from src.utils.model_name import model_token

    if len(llm_answers) < 1:
        logger.warning("No LLM answers to compare")
        return None

    # Build question text
    question_text = (
        f"**Title:** {question.title}\n\n**Body:**\n{html_to_text(question.body)}"
    )

    # Build candidates section (only LLM answers)
    all_candidates = dict(llm_answers)
    model_names = sorted(all_candidates.keys())

    if no_reference:
        from src.conf.prompts import (
            COMPARE_NO_REF_SYSTEM_PROMPT,
            COMPARE_NO_REF_USER_TEMPLATE,
        )

        candidates_parts = []
        for name in model_names:
            candidates_parts.append(f"**[{name}]**:\n{all_candidates[name]}")
        candidates_text = "\n\n".join(candidates_parts)

        user_content = COMPARE_NO_REF_USER_TEMPLATE.format(
            question=question_text,
            candidates=candidates_text,
        )
        system_prompt = COMPARE_NO_REF_SYSTEM_PROMPT
    else:
        from src.conf.prompts import COMPARE_SYSTEM_PROMPT, COMPARE_USER_TEMPLATE

        if not human_answer_content:
            logger.warning("No reference answer for comparison")
            return None

        candidates_parts = []
        for name in model_names:
            candidates_parts.append(f"**[{name}]**:\n{all_candidates[name]}")
        candidates_text = "\n\n".join(candidates_parts)

        user_content = COMPARE_USER_TEMPLATE.format(
            question=question_text,
            reference_answer=human_answer_content,
            candidates=candidates_text,
        )
        system_prompt = COMPARE_SYSTEM_PROMPT

    # Save prompt to file
    token = model_token(primary_model)
    prompt_filename = f"{token}_compare{'_no_reference' if no_reference else ''}_prompt.txt"
    prompt_content = f"""=== SYSTEM PROMPT ===
{system_prompt}

=== USER PROMPT ===
{user_content}
"""
    prompt_path = topic_dir / prompt_filename
    prompt_path.write_text(prompt_content, encoding="utf-8")
    logger.info("📝 Saved prompt to %s", prompt_path)
    
    return prompt_path


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
            filename = (
                answer_file.stem
            )  # e.g., "gpt5_1_answer" or "gpt5_1_evaluate_gpt5_1_answer"

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
