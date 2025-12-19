from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Sequence, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
import json

import httpx

from src.domain.models import Question
from src.conf.config import settings
from src.services.stack_client import StackOverflowClient
from src.services.storage import Storage
from src.agents.translator import Translator
from src.agents.evaluator import Evaluator
from src.utils.rehydrate import load_questions_from_dir
from src.utils.text import is_file_chinese, is_file_empty, html_to_text
from src.utils.model_name import model_token

logger = logging.getLogger(__name__)


def run_crawl(
    tag: str = "kubernetes",
# ... (lines 24-279 skipped)
    limit: int = 5,
    page_size: int = 50,
    out_dir: str | Path = "data",
    stack_key: Optional[str] = None,
    workers: int = 4,
    checkpoint_file: str | Path | None = None,
    session: Optional[httpx.Client] = None,
) -> None:
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0), http2=False)
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


def run_translate(
    out_dir: str | Path,
    model_url: str = settings.LOCAL_MODEL_URL,
    api_key: str = settings.OPENAI_API_KEY or "test-key",
    workers: int = 2,
    session: Optional[httpx.Client] = None,
    force: bool = False,
    limit: Optional[int] = None,
    skip: int = 0,
) -> None:
    base = Path(out_dir)
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0), http2=False)
    translator = Translator(base_url=model_url, api_key=api_key, session=http_client)
    store = Storage(base)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: list[Future[None]] = []
        processed = 0
        for topic_dir, question in load_questions_from_dir(base, skip=skip):
            if limit is not None and processed >= limit:
                break
            
            # Logic to check if translation is needed is complex now (multiple files).
            # We submit if ANY translation might be needed or let the worker decide.
            futures.append(
                pool.submit(
                    _translate_and_store, translator, store, question, topic_dir, force
                )
            )
            processed += 1
        for fut in as_completed(futures):
            fut.result()


def _translate_and_store(
    translator: Translator, store: Storage, question: Question, topic_dir: Path, force: bool = False
) -> None:
    # 1. Translate Question & StackOverflow Answers (Original behavior)
    # Check if exists
    qa_trans_path = topic_dir / "question_answer_translated.md"
    if force or not qa_trans_path.exists():
        try:
            logger.info("Translating Q&A for %s...", topic_dir.name)
            result = translator.translate(question)
            store.save_translation(topic_dir, result)
        except httpx.HTTPError as exc:
            logger.error("Translation failed for %s: %s", question.link, exc)
    
    # 2. Translate Generated Answers (New behavior detached from answer command)
    # Find all *_answer.md files
    for answer_file in topic_dir.glob("*_answer.md"):
        model_token = answer_file.stem.replace("_answer", "")
        trans_file = topic_dir / f"{model_token}_answer_translated.md"
        
        if force or not trans_file.exists():
            content = answer_file.read_text(encoding="utf-8")
            from src.utils import validators
            if content and not validators.is_chinese(content):
                logger.info("Translating answer %s for %s...", answer_file.name, topic_dir.name)
                try:
                    translated = translator.translate_text(content)
                    store.save_answer_translation(topic_dir, model_token, translated)
                except Exception as exc:
                    logger.error("Failed to translate answer %s: %s", answer_file.name, exc)


def run_batch_answer(
    out_dir: str | Path,
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
    base = Path(out_dir)
    http_client = session or httpx.Client(timeout=httpx.Timeout(60.0), http2=False)

    evaluator = Evaluator(
        base_url=base_url,
        api_key=api_key,
        model=model,
        session=http_client,
        mode="answer",
    )
    # Translator removed from here
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
) -> None:
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

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures: list[Future[None]] = []
        processed = 0
        for topic_dir, question in iterator:
            if limit is not None and processed >= limit:
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
                )
            )
            processed += 1
        for fut in as_completed(futures):
            fut.result()


# Deprecated wrapper for backward compatibility if needed, but we will remove CLI usage
def run_evaluate(*args, **kwargs):
    # This function is being removed in favor of strict separation
    # but we might keep it if any external scripts rely on it.
    # For this refactor, we replace it with `run_batch_evaluate` logic if called as evaluate,
    # but since main.py is switching, we leave run_evaluate as a dummy or remove it.
    logger.warning("run_evaluate is deprecated.")
    pass 


def _process_answer(
    evaluator: Evaluator,
    store: Storage,
    question: Question,
    topic_dir: Path,
    force: bool,
    model: str,
) -> None:
    try:
        # Save Question metadata/content always (idempotent)
        store.save_question(topic_dir, question)

        # 1. Answer Generation / Loading
        gpt_answer_content = ""
        
        # Logic:
        # 1. If FORCE -> Generate (Ignore CSV input, Ignore Disk)
        # 2. If CSV Input has answer -> Use it (Save to disk)
        # 3. If Disk has answer -> Skip (Use it)
        # 4. Generate
        
        should_generate = force
        
        if not should_generate:
            # Check if we should use existing answer from Data (CSV)
            if question.answers and len(question.answers) > 0:
                gpt_answer_content = question.answers[0].body
                logger.info("Using existing answer from CSV/Input for %s", topic_dir.name)
                store.save_answer(topic_dir, model, gpt_answer_content, question=question)
                return # Done
            
            # Check if exists on disk
            if store.has_answer(topic_dir, model):
                logger.info("Answer for %s already exists, skipping generation.", topic_dir.name)
                # gpt_answer_content = store.get_answer_content(topic_dir, model) 
                return # Done
            
            # If neither, proceed to generate
            should_generate = True

        if should_generate:
            question_text = f"{question.title}\n\n{html_to_text(question.body)}"
            gpt_answer_content, raw_resp = evaluator.generate_answer(question_text)
            store.save_answer(topic_dir, model, gpt_answer_content, raw_response=raw_resp, question=question)

    except Exception as exc:
        logger.error("Error processing answer for %s: %s", topic_dir.name, exc)


def _process_evaluation(
    evaluator: Evaluator,
    store: Storage,
    question: Question,
    topic_dir: Path,
    force: bool,
    model: str,
) -> None:
    try:
        # We need an answer to evaluate.
        # We check store or question.answers logic?
        # Standard flow: Answer should exist in local storage (md file) or passed in Question.
        # Since CSV loading might not populate Question.answers unless we modified loader widely,
        # but we did modify loader to populate it.
        # However, `run_batch_evaluate` might be run on existing directory WITHOUT CSV input.
        # So we look at Storage first.
        
        gpt_answer_content = store.get_answer_content(topic_dir, model)
        
        if not gpt_answer_content:
            # Check if passed explicitly via question object (from Input CSV)
             if question.answers and len(question.answers) > 0:
                 gpt_answer_content = question.answers[0].body
        
        if not gpt_answer_content:
            logger.warning("No answer found for %s (model: %s), skipping evaluation.", topic_dir.name, model)
            return

        # Check existence
        if force or not store.has_evaluation(topic_dir, model, model):
                # Format Q&A for evaluator
                formatted_qa = Storage._format_question_answers(question)
                evaluation, raw_resp = evaluator.evaluate(formatted_qa, gpt_answer_content, model)
                store.save_evaluation(topic_dir, model, model, evaluation, raw_resp)
        else:
                logger.info("Evaluation for %s already exists.", topic_dir.name)

    except Exception as exc:
        logger.error("Error evaluating %s: %s", topic_dir.name, exc)



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
