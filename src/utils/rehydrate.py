from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

from src.domain.models import Answer, Question
from .text import html_to_text

logger = logging.getLogger(__name__)


def load_questions_from_dir(
    base_dir: Path, reverse: bool = False, skip: int = 0
) -> Iterable[tuple[Path, Question]]:
    topic_dirs = sorted((p for p in base_dir.iterdir() if p.is_dir()), reverse=reverse)
    for topic_dir in topic_dirs[skip:]:
        question = _parse_question(topic_dir)
        if question is None:
            logger.warning("Skipping %s: missing question/answers files", topic_dir)
            continue
        yield topic_dir, question


def _parse_question(topic_dir: Path) -> Question | None:
    meta = _load_metadata(topic_dir / "metadata.json")
    combined_path = topic_dir / "question_answer.md"
    if combined_path.exists():
        return _parse_combined(combined_path, meta)
    return None


def _parse_combined(path: Path, meta: dict) -> Question | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    title = (
        lines[0].lstrip("#").strip() if lines else meta.get("title", "Unknown title")
    )
    body_lines, answer_sections = _split_question_answers(lines)
    answers = [
        _build_answer(sec, idx) for idx, sec in enumerate(answer_sections, start=1)
    ]
    return Question(
        question_id=meta.get("question_id", 0),
        title=title,
        body="\n".join(body_lines).strip(),
        creation_date=_parse_dt(meta.get("created_at")),
        link=meta.get("link", ""),
        tags=meta.get("tags", []),
        answers=answers,
    )


def _split_question_answers(lines: List[str]) -> Tuple[List[str], List[List[str]]]:
    # Find the separator line index
    separator_index = -1
    for i, line in enumerate(lines):
        if line.strip().lower() == "## answers":
            separator_index = i
            break

    if separator_index == -1:
        # No answers section, everything is question
        return lines, []

    question_lines = lines[:separator_index]
    answers_lines = lines[separator_index + 1 :]

    # Parse answers from the answers section
    answers: List[List[str]] = []
    current_answer: List[str] | None = None

    for line in answers_lines:
        if line.strip().lower().startswith("### answer"):
            if current_answer is not None:
                answers.append(current_answer)
            current_answer = []
            continue

        if current_answer is not None:
            current_answer.append(line)

    if current_answer is not None:
        answers.append(current_answer)

    return question_lines, answers


def _build_answer(lines: List[str], idx: int) -> Answer:
    meta = {}
    body: List[str] = []
    for line in lines:
        if ":" in line and line.lower().startswith(
            ("accepted", "score", "link", "created")
        ):
            key, _, val = line.partition(":")
            meta[key.strip().lower()] = val.strip()
        else:
            body.append(line)
    return Answer(
        answer_id=idx,
        body="\n".join(body).strip(),
        creation_date=_parse_dt(meta.get("created")),
        is_accepted=meta.get("accepted", "").lower() == "true",
        link=meta.get("link", ""),
        score=int(meta.get("score", "0") or 0),
    )


def _load_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    import json

    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _parse_dt(raw: str | None) -> datetime:
    if not raw:
        return datetime.utcnow()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return datetime.utcnow()
