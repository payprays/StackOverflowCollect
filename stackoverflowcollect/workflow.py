from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
import json

import httpx

from .models import Question
from .stack_client import StackOverflowClient
from .storage import Storage
from .translator import Translator

logger = logging.getLogger(__name__)


def run_pipeline(
    tag: str = "kubernetes",
    limit: int = 5,
    page_size: int = 50,
    out_dir: str | Path = "data",
    translate: bool = True,
    model_url: str = "http://localhost:4141",
    api_key: str = "test-key",
    stack_key: Optional[str] = None,
    workers: int = 4,
    checkpoint_file: str | Path | None = None,
    session: Optional[httpx.Client] = None,
) -> None:
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0))
    fetcher = StackOverflowClient(session=http_client, key=stack_key)
    store = Storage(Path(out_dir))
    translator = Translator(
        base_url=model_url, api_key=api_key, session=http_client
    ) if translate else None

    checkpoint_path = (
        Path(checkpoint_file) if checkpoint_file else Path(out_dir) / "checkpoint.json"
    )
    start_page, fetched_so_far = _load_checkpoint(checkpoint_path, tag)
    logger.info(
        "Starting run for tag '%s' with limit=%s, page_size=%s, resume_page=%s, already_fetched=%s",
        tag,
        limit,
        page_size,
        start_page,
        fetched_so_far,
    )

    def _get_answers(question: Question):
        try:
            return fetcher.fetch_answers(question.question_id)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch answers for %s: %s", question.link, exc)
            return []

    translation_futures: list[Future[None]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for page, questions in fetcher.fetch_paginated_questions(
            tag=tag, limit=limit, page_size=page_size, start_page=start_page
        ):
            logger.info(
                "Fetched page %s with %s questions, dispatching answer fetch and translations",
                page,
                len(questions),
            )
            answers_list = list(pool.map(_get_answers, questions))
            for question, answers in zip(questions, answers_list):
                question.answers = answers
                topic_dir = store.save_raw(question)
                if translator:
                    translation_futures.append(
                        pool.submit(_translate_and_store, translator, store, question, topic_dir)
                    )
            fetched_so_far += len(questions)
            _save_checkpoint(checkpoint_path, tag, page + 1, fetched_so_far, limit, page_size)
            if fetched_so_far >= limit:
                break

        for fut in as_completed(translation_futures):
            fut.result()

    if checkpoint_path.exists() and fetched_so_far >= limit:
        checkpoint_path.unlink()
        logger.info("Reached limit; checkpoint removed.")


def _translate_and_store(
    translator: Translator, store: Storage, question: Question, topic_dir: Path
) -> None:
    try:
        result = translator.translate(question)
    except httpx.HTTPError as exc:
        logger.error("Translation failed for %s: %s", question.link, exc)
        return
    store.save_translation(topic_dir, result)


def _load_checkpoint(path: Path, tag: str) -> tuple[int, int]:
    if not path.exists():
        return 1, 0
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return 1, 0
    if data.get("tag") != tag:
        return 1, 0
    return int(data.get("next_page", 1)), int(data.get("fetched", 0))


def _save_checkpoint(
    path: Path, tag: str, next_page: int, fetched: int, limit: int, page_size: int
) -> None:
    payload = {
        "tag": tag,
        "next_page": next_page,
        "fetched": fetched,
        "limit": limit,
        "page_size": page_size,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    logger.info("Checkpoint saved: %s", payload)


def build_question_summary(question: Question) -> str:
    answer_count = len(question.answers)
    return f"{question.title} (answers: {answer_count}, link: {question.link})"
