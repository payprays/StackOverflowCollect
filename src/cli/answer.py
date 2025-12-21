"""Answer command - Generate LLM answers for questions."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

import httpx

from src.domain.models import Question
from src.conf.config import settings
from src.core.evaluator import Evaluator
from src.io.storage import Storage
from src.utils.rehydrate import load_questions_from_dir
from src.utils.text import html_to_text

logger = logging.getLogger(__name__)


def run_batch_answer(
    input_dir: str | Path,
    model: str = settings.DEFAULT_MODEL_ANSWER,
    base_url: str = settings.OPENAI_BASE_URL,
    api_key: Optional[str] = None,
    workers: int = 2,
    session: Optional[httpx.Client] = None,
    force: bool = False,
    limit: Optional[int] = None,
    skip: int = 0,
    input_csv: Optional[str | Path] = None,
    output_csv: Optional[str | Path] = None,
) -> None:
    """Generate LLM answers for all questions in the directory."""
    base = Path(input_dir)
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0), http2=False)

    evaluator = Evaluator(
        base_url=base_url,
        api_key=api_key,
        model=model,
        session=http_client,
        mode="answer",
    )
    store = Storage(base, out_csv=Path(output_csv) if output_csv else None)

    if input_csv:
        from src.utils.csv_loader import load_questions_from_csv

        iterator = load_questions_from_csv(Path(input_csv), base)
    else:
        iterator = load_questions_from_dir(base, skip=skip)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: list[Future[None]] = []
        processed = 0
        for topic_dir, question in iterator:
            if limit is not None and processed >= limit:
                break
            futures.append(
                pool.submit(
                    _process_answer,
                    evaluator,
                    store,
                    question,
                    topic_dir,
                    force,
                    model,
                )
            )
            processed += 1
        for fut in as_completed(futures):
            fut.result()


def _process_answer(
    evaluator: Evaluator,
    store: Storage,
    question: Question,
    topic_dir: Path,
    force: bool,
    model: str,
) -> None:
    """Process a single question - generate answer if needed."""
    try:
        # Save Question metadata/content always (idempotent)
        store.save_question(topic_dir, question)

        # Use short name for logs (question ID)
        q_name = topic_dir.name.split("_")[0]
        logger.info("📋 [%s] Processing: %s", q_name, topic_dir.name)

        should_generate = force

        if not should_generate:
            # Check if exists on disk
            if store.has_answer(topic_dir, model):
                logger.info("⏭️ [%s] Answer already exists, skipping", q_name)
                return

            should_generate = True

        if should_generate:
            logger.info("🤖 [%s] Generating answer with %s...", q_name, model)
            question_text = f"{question.title}\n\n{html_to_text(question.body)}"
            gpt_answer_content, raw_resp = evaluator.generate_answer(question_text)
            store.save_answer(
                topic_dir,
                model,
                gpt_answer_content,
                raw_response=raw_resp,
                question=question,
            )
            logger.info("✅ [%s] Answer saved", q_name)

    except Exception as exc:
        logger.error("Error processing answer for %s: %s", topic_dir.name, exc)
