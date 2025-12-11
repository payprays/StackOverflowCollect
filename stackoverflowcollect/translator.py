from __future__ import annotations

import logging
from textwrap import dedent
from typing import Iterable, Optional

import httpx

from .models import Answer, Question, TranslationResult
from .text import html_to_text

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
                    "content": "You are a bilingual cloud-native expert. Translate to concise Chinese and then answer succinctly in Chinese.",
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
        translated_question, assistant_answer = self._split_response(message)
        return TranslationResult(
            translated_question=translated_question,
            assistant_answer=assistant_answer,
            model=self.model,
            raw_response=body,
        )

    @staticmethod
    def _split_response(text: str) -> tuple[str, str]:
        if "\n\nAnswer:" in text:
            translated, answer = text.split("\n\nAnswer:", 1)
            return translated.strip(), answer.strip()
        return text.strip(), ""

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
            Translate the following Stack Overflow question and answers into concise Chinese.
            After the translation, provide your own concise Chinese answer to the question.
            Format:
            Translated Question (include title/body)
            Answer: <your Chinese answer>

            Title: {question.title}
            Body: {html_to_text(question.body)}
            Answers:
            {joined_answers}
            """
        ).strip()
