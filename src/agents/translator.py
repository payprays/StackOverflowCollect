from __future__ import annotations

import logging
import re
from typing import Iterable, Optional

import httpx

from textwrap import dedent
from src.conf.prompts import TRANSLATION_SYSTEM_PROMPT
from src.domain.models import Answer, Question, TranslationResult
from src.utils.text import html_to_text

logger = logging.getLogger(__name__)


from src.services.llm_client import LLMClient

class Translator:
    def __init__(
        self,
        base_url: str = "http://localhost:4141",
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        session: Optional[httpx.Client] = None,
    ) -> None:
        self.llm_client = LLMClient(
            base_url=base_url, api_key=api_key, model=model, session=session
        )
        self.model = model

    def translate(self, question: Question) -> TranslationResult:
        prompt = self._build_prompt(question, question.answers)
        messages = [
            {
                "role": "system",
                "content": TRANSLATION_SYSTEM_PROMPT,
            },
            {"role": "user", "content": prompt},
        ]
        logger.info("Sending translation request for question %s", question.question_id)
        
        # We need the raw response for TranslationResult? 
        # The LLMClient only returns content string.
        # But TranslationResult expects `raw_response`.
        # For now, let's reconstruct a minimal raw response or adjust TranslationResult usage.
        # Or LLMClient could return full response?
        # Let's adjust LLMClient or just pass a simulated one?
        # The prompt says LLMClient returns string.
        # Let's clean up TranslationResult usage - raw_response is optional.
        
        content = self.llm_client.chat_completion(messages)
        
        translated_question_answers, gpt_answer = self._split_translations(content)
        return TranslationResult(
            translated_question_answers=translated_question_answers,
            gpt_answer=gpt_answer,
            model=self.model,
            raw_response={"choices": [{"message": {"content": content}}]}, # Simulated for now
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

    def translate_text(self, text: str) -> str:
        """Translate arbitrary text to Chinese."""
        prompt = f"Translate the following text to concise Chinese:\n\n{text}"
        messages = [{"role": "user", "content": prompt}]
        return self.llm_client.chat_completion(messages)

