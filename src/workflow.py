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
from .evaluator import Evaluator
from .utils.rehydrate import load_questions_from_dir
from .utils.text import is_file_chinese, is_file_empty
from .utils.model_name import model_token

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
) -> None:
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0))
    fetcher = StackOverflowClient(session=http_client, key=stack_key)
    store = Storage(Path(out_dir))

    checkpoint_path = (
        Path(checkpoint_file) if checkpoint_file else Path(out_dir) / "checkpoint.json"
    )
    start_page, fetched_so_far = _load_checkpoint(checkpoint_path, tag)
    logger.info(
        "Starting crawl for tag '%s' with limit=%s, page_size=%s, resume_page=%s, already_fetched=%s",
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

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for page, questions in fetcher.fetch_paginated_questions(
            tag=tag, limit=limit, page_size=page_size, start_page=start_page
        ):
            logger.info(
                "Fetched page %s with %s questions, dispatching answer fetch",
                page,
                len(questions),
            )
            answers_list = list(pool.map(_get_answers, questions))
            for question, answers in zip(questions, answers_list):
                question.answers = answers
                store.save_raw(question)

            fetched_so_far += len(questions)
            _save_checkpoint(
                checkpoint_path, tag, page + 1, fetched_so_far, limit, page_size
            )
            if fetched_so_far >= limit:
                break

    if checkpoint_path.exists() and fetched_so_far >= limit:
        checkpoint_path.unlink()
        logger.info("Reached limit; checkpoint removed.")


def run_translate(
    out_dir: str | Path,
    model_url: str = "http://localhost:4141",
    api_key: str = "test-key",
    workers: int = 2,
    session: Optional[httpx.Client] = None,
    force: bool = False,
    limit: Optional[int] = None,
    skip: int = 0,
) -> None:
    base = Path(out_dir)
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0))
    translator = Translator(base_url=model_url, api_key=api_key, session=http_client)
    store = Storage(base)

    def needs_translation(topic_dir: Path) -> bool:
        if force:
            return True
        return not (topic_dir / "question_answer_translated.md").exists()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: list[Future[None]] = []
        processed = 0
        for topic_dir, question in load_questions_from_dir(base, skip=skip):
            if limit is not None and processed >= limit:
                break
            if not needs_translation(topic_dir):
                continue
            futures.append(
                pool.submit(
                    _translate_and_store, translator, store, question, topic_dir
                )
            )
            processed += 1
        for fut in as_completed(futures):
            fut.result()


def run_evaluate(
    out_dir: str | Path,
    model: str = "gpt-4o",
    base_url: str = "https://api.openai.com/v1/chat/completions",
    api_key: Optional[str] = None,
    workers: int = 2,
    session: Optional[httpx.Client] = None,
    force: bool = False,
    reverse: bool = False,
    limit: Optional[int] = None,
    mode: str = "answer",
    skip: int = 0,
) -> None:
    base = Path(out_dir)
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0))
    evaluator = Evaluator(
        base_url=base_url,
        api_key=api_key,
        model=model,
        session=http_client,
        mode=mode,
    )
    store = Storage(base)
    answer_token = model_token(model)
    eval_token = model_token(model)
    answer_filename = f"{answer_token}_answer.md"
    eval_filename = f"{eval_token}_evaluate_{answer_token}_answer.md"

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: list[Future[None]] = []
        processed = 0
        for topic_dir, question in load_questions_from_dir(
            base, reverse=reverse, skip=skip
        ):
            if limit is not None and processed >= limit:
                break
            futures.append(
                pool.submit(
                    _evaluate_and_store,
                    evaluator,
                    store,
                    question,
                    topic_dir,
                    force,
                    answer_filename,
                    eval_filename,
                    model,
                )
            )
            processed += 1
        for fut in as_completed(futures):
            fut.result()


def _translate_and_store(
    translator: Translator, store: Storage, question: Question, topic_dir: Path
) -> None:
    try:
        result = translator.translate(question)
    except httpx.HTTPError as exc:
        logger.error("Translation failed for %s: %s", question.link, exc)
        return
    store.save_translation(topic_dir, result)


def _evaluate_and_store(
    evaluator: Evaluator,
    store: Storage,
    question: Question,
    topic_dir: Path,
    force: bool,
    answer_filename: str,
    eval_filename: str,
    answer_model: str,
) -> None:
    # 1. Generate Answer if missing
    gpt_answer_path = topic_dir / answer_filename
    gpt_answer_content = ""

    # Only generate if missing. 'force' applies to evaluation, not answer generation.
    if (
        not gpt_answer_path.exists() or is_file_empty(gpt_answer_path) or force
    ) and evaluator.mode == "answer":
        try:
            # We need the question content. question.body is HTML.
            # We should probably use the text version if available, or convert it.
            # load_questions_from_dir returns Question objects which have body as HTML.
            # But we also have question_answer.md which has text.
            # Let's use the question_answer.md content for context if possible,
            # or just convert question.body to text.
            # For simplicity, let's read question_answer.md
            # Ensure we only send the question title and body to the model, not the answers.
            # The question object loaded from disk already has the body converted to text.
            q_text = f"{question.title}\n\n{question.body}"
            gpt_answer_content = evaluator.generate_answer(q_text)
            gpt_answer_path.write_text(gpt_answer_content, encoding="utf-8")
            logger.info("Generated answer for %s", topic_dir.name)
        except Exception as exc:
            logger.error("Answer generation failed for %s: %s", topic_dir.name, exc)
            return
    elif evaluator.mode == "answer":
        logger.info("Answer already exists for %s, skipping answer", topic_dir.name)
        gpt_answer_content = gpt_answer_path.read_text(encoding="utf-8")

    # 2. Evaluate
    eval_path = topic_dir / eval_filename
    if (
        not eval_path.exists()
        or is_file_empty(eval_path)
        or not is_file_chinese(eval_path)
        or force
    ) and evaluator.mode == "evaluate":
        try:
            qa_path = topic_dir / "question_answer.md"
            if qa_path.exists():
                qa_content = qa_path.read_text(encoding="utf-8")
                eval_content = evaluator.evaluate(
                    qa_content, gpt_answer_content, answer_model
                )
                eval_path.write_text(eval_content, encoding="utf-8")
                logger.info("Evaluated %s", topic_dir.name)
        except Exception as exc:
            logger.error("Evaluation failed for %s: %s", topic_dir.name, exc)
    elif evaluator.mode == "evaluate":
        print(f"Evaluation already exists for {topic_dir.name}, skipping evaluation")


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
