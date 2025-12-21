"""Translate command - Translate Q&A and answers to Chinese."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, Future

import httpx

from src.domain.models import Question
from src.conf.config import settings
from src.core.translator import Translator
from src.io.storage import Storage
from src.utils.rehydrate import load_questions_from_dir

logger = logging.getLogger(__name__)


def run_translate(
    out_dir: str | Path,
    model_url: str = settings.LOCAL_MODEL_URL,
    api_key: str = settings.OPENAI_API_KEY or "test-key",
    workers: int = 2,
    session: Optional[httpx.Client] = None,
    force: bool = False,
    limit: Optional[int] = None,
    skip: int = 0,
    input_csv: Optional[str | Path] = None,
    output_csv: Optional[str | Path] = None,
) -> None:
    """Translate questions and answers to Chinese."""
    base = Path(out_dir)
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0), http2=False)
    translator = Translator(base_url=model_url, api_key=api_key, session=http_client)
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
                    _translate_and_store, translator, store, question, topic_dir, force
                )
            )
            processed += 1
        for fut in as_completed(futures):
            fut.result()


def _translate_and_store(
    translator: Translator,
    store: Storage,
    question: Question,
    topic_dir: Path,
    force: bool = False,
) -> None:
    """Translate a single question and its answers."""
    # 1. Translate Question & StackOverflow Answers
    qa_trans_path = topic_dir / "question_answer_translated.md"
    if force or not qa_trans_path.exists():
        try:
            logger.info("Translating Q&A for %s...", topic_dir.name)
            result = translator.translate(question)
            store.save_translation(topic_dir, result)
        except httpx.HTTPError as exc:
            logger.error("Translation failed for %s: %s", question.link, exc)

    # 2. Translate Generated Answers
    for answer_file in topic_dir.glob("*_answer.md"):
        ans_token = answer_file.stem.replace("_answer", "")
        trans_file = topic_dir / f"{ans_token}_answer_translated.md"

        if force or not trans_file.exists():
            content = answer_file.read_text(encoding="utf-8")
            from src.utils import validators

            if content and not validators.is_chinese(content):
                logger.info(
                    "Translating answer %s for %s...", answer_file.name, topic_dir.name
                )
                try:
                    translated = translator.translate_text(content)
                    store.save_answer_translation(topic_dir, ans_token, translated)
                except Exception as exc:
                    logger.error(
                        "Failed to translate answer %s: %s", answer_file.name, exc
                    )
