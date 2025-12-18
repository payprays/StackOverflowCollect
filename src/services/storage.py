from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

from src.core.models import Answer, Question, TranslationResult
from src.utils.text import html_to_text

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug[:80] or "topic"


class Storage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _topic_dir(self, question: Question) -> Path:
        prefix = question.creation_date.strftime("%Y%m%d_%H%M%S")
        return self.base_dir / f"{prefix}_{slugify(question.title)}"

    def save_raw(self, question: Question) -> Path:
        topic_dir = self._topic_dir(question)
        topic_dir.mkdir(parents=True, exist_ok=True)
        (topic_dir / "metadata.json").write_text(
            json.dumps(
                {
                    "question_id": question.question_id,
                    "link": question.link,
                    "tags": question.tags,
                    "created_at": question.creation_date.isoformat(),
                    "answer_count": len(question.answers),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (topic_dir / "question_answer.md").write_text(
            self._format_question_answers(question), encoding="utf-8"
        )
        logger.info("Saved raw content to %s", topic_dir)
        return topic_dir

    def save_translation(self, topic_dir: Path, result: TranslationResult) -> None:
        (topic_dir / "question_answer_translated.md").write_text(
            result.translated_question_answers, encoding="utf-8"
        )
        # We do not save gpt4o_answer.md here anymore, as it is handled by the evaluator/solver step.
        # If the translator produced an extra answer, we ignore it or save it to a different file if needed.
        # (topic_dir / "gpt4o_answer.md").write_text(result.gpt_answer, encoding="utf-8")

        if result.raw_response is not None:
            (topic_dir / "translation_raw.json").write_text(
                json.dumps(result.raw_response, indent=2), encoding="utf-8"
            )
        logger.info("Saved translation output to %s", topic_dir)

    @staticmethod
    def _format_question_answers(question: Question) -> str:
        header = [
            f"# {question.title}",
            f"Link: {question.link}",
            f"Created: {question.creation_date.isoformat()}",
            f"Tags: {', '.join(question.tags)}",
            "",
            "## Question",
            html_to_text(question.body),
            "",
            "## Answers",
        ]
        if question.answers:
            for idx, answer in enumerate(question.answers, start=1):
                header.extend(
                    [
                        f"### Answer {idx}",
                        f"Accepted: {answer.is_accepted}",
                        f"Score: {answer.score}",
                        f"Link: {answer.link}",
                        f"Created: {answer.creation_date.isoformat()}",
                        "",
                        html_to_text(answer.body),
                        "",
                    ]
                )
        else:
            header.append("No answers retrieved.")
        return "\n".join(header)
