from __future__ import annotations

import logging
import re
from textwrap import dedent
from typing import Iterable, Optional

import httpx

from src.core.models import Answer, Question, TranslationResult
from src.utils.text import html_to_text
from src.prompts import TRANSLATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class Translator:
    def __init__(
        self,
        base_url: str = "http://localhost:4141",
        api_key: str = "test-key",
        model: str = "gpt-4o",
        session: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._client = session or httpx.Client(timeout=httpx.Timeout(60.0))

    def translate(self, question: Question) -> TranslationResult:
        prompt = self._build_prompt(question, question.answers)
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": TRANSLATION_SYSTEM_PROMPT,
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        logger.info("Sending translation request for question %s", question.question_id)
        resp = self._client.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        body = resp.json()
        message = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        translated_question_answers, gpt_answer = self._split_translations(message)
        return TranslationResult(
            translated_question_answers=translated_question_answers,
            gpt_answer=gpt_answer,
            model=self.model,
            raw_response=body,
        )

    @staticmethod
    def _split_translations(text: str) -> tuple[str, str]:
        """Parse model output into translated Q&A and new Chinese answer."""
        lines = text.strip().splitlines()
        qa_lines: list[str] = []
        answer_lines: list[str] = []

        def is_qa_header(line: str) -> bool:
            return re.match(r"^#+\s*翻译后问题与回答", line.strip()) is not None

        def is_ans_header(line: str) -> bool:
            return (
                re.match(r"^#+\s*gpt4o回答", line.strip(), flags=re.IGNORECASE)
                is not None
            )

        mode = "qa"
        for line in lines:
            if is_qa_header(line):
                mode = "qa"
                continue
            if is_ans_header(line):
                mode = "answer"
                continue
            if mode == "qa":
                qa_lines.append(line)
            else:
                answer_lines.append(line)

        qa_text = "\n".join(qa_lines).strip()
        ans_text = "\n".join(answer_lines).strip()
        return qa_text or text.strip(), ans_text

    @staticmethod
    def _build_prompt(question: Question, answers: Iterable[Answer]) -> str:
        answer_blocks = []
        for idx, answer in enumerate(answers, start=1):
            answer_blocks.append(
                dedent(
                    f"""
                    Answer {idx} (accepted={answer.is_accepted}, score={answer.score}):
                    {html_to_text(answer.body)}
                    """
                ).strip()
            )
        joined_answers = "\n\n".join(answer_blocks) if answer_blocks else "No answers."
        return dedent(
            f"""
            Translate the following Stack Overflow question and all answers into concise Chinese.
            Then provide a new concise Chinese answer from yourself.
            Output format:
            ### 翻译后问题与回答
            <translated question text and all answers in order>
            ### gpt4o回答
            <your Chinese answer>

            Title: {question.title}
            Body: {html_to_text(question.body)}
            Answers:
            {joined_answers}
            """
        ).strip()
