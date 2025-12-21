"""Crawl command - Fetch questions from Stack Overflow."""

from __future__ import annotations

import logging
import json
from pathlib import Path
from typing import Optional, Tuple
from concurrent.futures import ThreadPoolExecutor

import httpx

from src.domain.models import Question
from src.io.stack_client import StackOverflowClient
from src.io.storage import Storage

logger = logging.getLogger(__name__)


def run_crawl(
    tag: str = "kubernetes",
    limit: int = 5,
    page_size: int = 50,
    out_dir: str | Path = "data",
    stack_key: Optional[str] = None,
    workers: int = 4,
    checkpoint_file: str | Path | None = None,
    session: Optional[httpx.Client] = None,
    output_csv: Optional[str | Path] = None,
    force: bool = False,
) -> None:
    """Crawl Stack Overflow for questions with the given tag."""
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0), http2=False)
    fetcher = StackOverflowClient(session=http_client, key=stack_key)
    store = Storage(Path(out_dir), out_csv=Path(output_csv) if output_csv else None)

    checkpoint_path = (
        Path(checkpoint_file) if checkpoint_file else Path(out_dir) / "checkpoint.json"
    )
    if force and checkpoint_path.exists():
        logger.warning("Force mode: Ignoring existing checkpoint to start fresh.")
        start_page, fetched_so_far = 1, 0
    else:
        start_page, fetched_so_far = _load_checkpoint(checkpoint_path, tag)
    
    logger.info(
        "Starting crawl for tag '%s' with limit=%s, page_size=%s, resume_page=%s, already_fetched=%s",
        tag, limit, page_size, start_page, fetched_so_far,
    )

    def _get_answers(question: Question):
        try:
            return fetcher.fetch_answers(question.question_id)
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch answers for %s: %s", question.link, exc)
            return []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for page, questions in fetcher.fetch_paginated_questions(
            tag=tag, limit=limit, page_size=page_size, start_page=start_page
        ):
            logger.info(
                "Fetched page %s with %s questions, dispatching answer fetch",
                page, len(questions),
            )
            answers_list = list(pool.map(_get_answers, questions))
            for question, answers in zip(questions, answers_list):
                question.answers = answers
                topic_dir = store._topic_dir(question)
                store.save_question(topic_dir, question)

            fetched_so_far += len(questions)
            _save_checkpoint(
                checkpoint_path, tag, page + 1, fetched_so_far, limit, page_size
            )
            if fetched_so_far >= limit:
                break

    if checkpoint_path.exists() and fetched_so_far >= limit:
        checkpoint_path.unlink()
        logger.info("Reached limit; checkpoint removed.")


def _load_checkpoint(path: Path, tag: str) -> Tuple[int, int]:
    """Load checkpoint file for resuming crawl."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("tag") == tag:
                return data.get("next_page", 1), data.get("fetched", 0)
        except Exception:
            pass
    return 1, 0


def _save_checkpoint(
    path: Path, tag: str, next_page: int, fetched: int, limit: int, page_size: int
) -> None:
    """Save checkpoint for resuming crawl."""
    data = {
        "tag": tag,
        "next_page": next_page,
        "fetched": fetched,
        "limit": limit,
        "page_size": page_size,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
