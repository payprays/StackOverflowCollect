"""Evaluate command - Run evaluation modules on LLM answers."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

import httpx
import pandas as pd

from src.domain.models import Question
from src.conf.config import settings
from src.core.evaluator import Evaluator
from src.io.storage import Storage
from src.utils.rehydrate import load_questions_from_dir
from src.utils.model_name import model_token

logger = logging.getLogger(__name__)


def run_batch_evaluate(
    out_dir: str | Path,
    model: str = settings.DEFAULT_MODEL_ANSWER,
    base_url: str = settings.OPENAI_BASE_URL,
    api_key: Optional[str] = None,
    workers: int = 2,
    session: Optional[httpx.Client] = None,
    force: bool = False,
    reverse: bool = False,
    limit: Optional[int] = None,
    skip: int = 0,
    input_csv: Optional[str | Path] = None,
    output_csv: Optional[str | Path] = None,
    modules: Optional[Sequence[str]] = None,
    no_reference: bool = False,
) -> None:
    """Run evaluation on all LLM answers in the directory."""
    # Normalize modules
    if modules is None or "all" in modules:
        enabled_modules = {"lint", "coverage", "llm-eval", "compare"}
    else:
        enabled_modules = set(modules)

    logger.info("🧩 Enabled evaluation modules: %s", ", ".join(sorted(enabled_modules)))

    base = Path(out_dir)
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0), http2=False)

    evaluator = Evaluator(
        base_url=base_url,
        api_key=api_key,
        model=model,
        session=http_client,
        mode="evaluate",
    )
    store = Storage(base, out_csv=Path(output_csv) if output_csv else None)

    if input_csv:
        from src.utils.csv_loader import load_questions_from_csv

        iterator = load_questions_from_csv(Path(input_csv), base)
    else:
        iterator = load_questions_from_dir(base, reverse=reverse, skip=skip)

    # Track if we're in CSV input mode
    csv_mode = input_csv is not None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: list[Future[None]] = []
        processed = 0
        skipped = 0
        for topic_dir, question in iterator:
            if limit is not None and processed >= limit:
                logger.debug("Reached limit %d, breaking", limit)
                break
            futures.append(
                pool.submit(
                    _process_evaluation,
                    evaluator,
                    store,
                    question,
                    topic_dir,
                    force,
                    model,
                    csv_mode,
                    enabled_modules,
                    no_reference,
                )
            )
            processed += 1

        logger.info(
            "📤 Submitted %d items for evaluation (skipped: %d)", processed, skipped
        )

        completed = 0
        for fut in as_completed(futures):
            fut.result()
            completed += 1

        logger.info("🏁 Evaluate complete: %d/%d items processed", completed, processed)

        # Print Coverage Summary (only if coverage module was enabled)
        if store.out_csv and "coverage" in enabled_modules:
            _print_coverage_summary(store.out_csv, model)


def _process_evaluation(
    evaluator: Evaluator,
    store: Storage,
    question: Question,
    topic_dir: Path,
    force: bool,
    model: str,
    csv_mode: bool = False,
    enabled_modules: Optional[set] = None,
    no_reference: bool = False,
) -> None:
    """Process a single question through enabled evaluation modules."""
    if enabled_modules is None:
        enabled_modules = {"lint", "coverage", "llm-eval", "compare"}

    try:
        # Get LLM and human answer content
        llm_answer_content = ""
        human_answer_content = ""

        if csv_mode:
            if question.answers and len(question.answers) > 0:
                llm_answer_content = question.answers[0].body
            if question.answers and len(question.answers) > 1:
                human_answer_content = question.answers[1].body
            if not llm_answer_content:
                llm_answer_content = store.get_answer_content(topic_dir, model)
        else:
            llm_answer_content = store.get_answer_content(topic_dir, model)
            if not llm_answer_content:
                if question.answers and len(question.answers) > 0:
                    llm_answer_content = question.answers[0].body
            if question.answers and len(question.answers) > 0:
                human_answer_content = question.answers[0].body

        if not llm_answer_content:
            logger.warning(
                "⚠️ [%s] No LLM answer found (model: %s), skipping",
                topic_dir.name.split("_")[0],
                model,
            )
            return

        store.ensure_question_in_csv(question)

        q_name = topic_dir.name.split("_")[0]
        logger.info("📋 [%s] Processing: %s", q_name, topic_dir.name)

        # 1. Lint module
        if "lint" in enabled_modules:
            from src.evaluate.lint import run_lint

            lint_result, _, _ = run_lint(
                llm_answer_content, store, topic_dir, question, model
            )
            logger.info("🔍 [%s] Lint: %s", q_name, lint_result)

        # 2. Coverage module
        if "coverage" in enabled_modules:
            if human_answer_content:
                from src.evaluate.coverage import run_coverage

                coverage_results = run_coverage(
                    human_answer_content,
                    llm_answer_content,
                    evaluator,
                    store,
                    topic_dir,
                    question,
                    model,
                )
                if coverage_results:
                    logger.info(
                        "✅ [%s] Coverage saved: %s%%",
                        q_name,
                        coverage_results.get("coverage_percentage", 0),
                    )
            else:
                logger.warning("⚠️ [%s] No human answer for coverage check", q_name)

        # 3. LLM Eval module
        if "llm-eval" in enabled_modules:
            from src.evaluate.llm_eval import run_llm_eval

            result = run_llm_eval(
                question,
                human_answer_content,
                llm_answer_content,
                evaluator,
                store,
                topic_dir,
                model,
                force,
            )
            if result:
                logger.info("✅ [%s] Evaluation saved", q_name)
            else:
                logger.info("⏭️ [%s] Evaluation already exists, skipping", q_name)

        # 4. Compare module - compare all LLM answers against reference
        if "compare" in enabled_modules:
            if human_answer_content or no_reference:
                from src.evaluate.compare import (
                    run_compare,
                    find_llm_answers,
                    save_compare_prompt_only,
                )

                # Find all available LLM answers
                llm_answers = find_llm_answers(store, topic_dir, question, csv_mode)

                if len(llm_answers) >= 1:
                    # Always save prompt for manual use
                    save_compare_prompt_only(
                        question,
                        human_answer_content if not no_reference else "",
                        llm_answers,
                        topic_dir,
                        model,
                        no_reference=no_reference,
                    )

                    if force or not store.has_comparison(topic_dir, model):
                        logger.info(
                            "🔄 [%s] Comparing %d LLM answers...",
                            q_name,
                            len(llm_answers),
                        )
                        result = run_compare(
                            question,
                            human_answer_content if not no_reference else "",
                            llm_answers,
                            evaluator,
                            store,
                            topic_dir,
                            model,
                            no_reference=no_reference,
                        )
                        if result:
                            logger.info("✅ [%s] Comparison saved", q_name)
                    else:
                        logger.info(
                            "⏭️ [%s] Comparison already exists, skipping", q_name
                        )
                else:
                    logger.warning("⚠️ [%s] Not enough LLM answers to compare", q_name)
            else:
                logger.warning("⚠️ [%s] No reference answer for comparison", q_name)

    except Exception as exc:
        logger.error("Error evaluating %s: %s", topic_dir.name, exc)


def _print_coverage_summary(csv_path: Path, model: str) -> None:
    """Print coverage summary statistics."""
    try:
        if not csv_path.exists():
            return

        df = pd.read_csv(csv_path)
        col_name = f"{model_token(model)}_Coverage"

        if col_name not in df.columns:
            logger.warning("No coverage column '%s' found in results.", col_name)
            return

        coverages = []
        for val in df[col_name]:
            if pd.isna(val):
                continue
            match = re.search(r"([\d\.]+)%", str(val))
            if match:
                try:
                    coverages.append(float(match.group(1)))
                except:
                    pass

        if not coverages:
            logger.info("No valid coverage data found.")
            return

        avg = sum(coverages) / len(coverages)
        max_cov = max(coverages)
        min_cov = min(coverages)

        full = sum(1 for c in coverages if c == 100)
        high = sum(1 for c in coverages if 90 <= c < 100)
        medium = sum(1 for c in coverages if 60 <= c < 90)
        low = sum(1 for c in coverages if c < 60)

        print("\n" + "=" * 60)
        print("COMPARISON RESULT STATISTICS")
        print("=" * 60)
        print(f"Total Records: {len(df)}")
        print(f"Valid Comparisons: {len(coverages)}")
        print(f"Average Coverage: {avg:.2f}%")
        print(f"Max Coverage: {max_cov:.2f}%")
        print(f"Min Coverage: {min_cov:.2f}%")
        print()
        print("Coverage Distribution:")
        print(f"  100%:    {full} ({full / len(coverages) * 100:.1f}%)")
        print(f"  90-99%:  {high} ({high / len(coverages) * 100:.1f}%)")
        print(f"  60-89%:  {medium} ({medium / len(coverages) * 100:.1f}%)")
        print(f"  <60%:    {low} ({low / len(coverages) * 100:.1f}%)")
        print("=" * 60)

    except Exception as e:
        logger.warning("Could not print coverage summary: %s", e)
