import logging
import os
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv
from src.utils.model_name import model_token

from src.core.llm_client import LLMClient
from src.conf.prompts import (
    FULL_EVALUATION_SYSTEM_PROMPT,
    ANSWER_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


class Evaluator:
    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1/chat/completions",
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        session: Optional[httpx.Client] = None,
        mode: str = "answer",
    ) -> None:
        # We can either accept an LLMClient or create one.
        # To maintain signature compatibility for now, we create one.
        # Ideally, we should inject LLMClient.
        self.llm_client = LLMClient(
            base_url=base_url, api_key=api_key, model=model, session=session
        )
        self.mode = mode

    def generate_answer(self, question_content: str) -> tuple[str, Dict[str, Any]]:
        """Generates an answer for the given question using the answer model."""
        messages = [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": question_content},
        ]
        return self.llm_client.chat_completion_full(messages)

    def evaluate(
        self,
        question_answer_content: str,
        gpt_answer_content: str,
        answer_model: str,
    ) -> tuple[str, Dict[str, Any]]:
        """Evaluates the GPT answer against the original Q&A using the evaluation model."""
        # Split original content into Question and Human Answers
        parts = question_answer_content.split("## Answers")
        question_part = parts[0].strip()
        human_answers_part = (
            parts[1].strip()
            if len(parts) > 1
            else "No human reference answers provided."
        )

        user_content = (
            f"[Question]\n{question_part}\n\n"
            f"[LLM Answer]\n{gpt_answer_content}\n\n"
            f"[Human Reference Answer]\n{human_answers_part}"
        )

        messages = [
            {"role": "system", "content": FULL_EVALUATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]
        return self.llm_client.chat_completion_full(messages)

    def check_coverage(self, human_answer: str, llm_answer: str) -> Dict[str, Any]:
        """Calculates YAML field coverage of LLM answer vs Human answer (Benchmark Logic)."""
        from src.utils.coverage import calculate_coverage
        return calculate_coverage(human_answer, llm_answer)


