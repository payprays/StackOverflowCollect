from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional


@dataclass
class Answer:
    answer_id: int
    body: str
    creation_date: datetime
    is_accepted: bool
    link: str
    score: int


@dataclass
class Question:
    question_id: int
    title: str
    body: str
    creation_date: datetime
    link: str
    tags: List[str]
    answers: List[Answer] = field(default_factory=list)


@dataclass
class TranslationResult:
    translated_question_answers: str
    gpt_answer: str
    model: str
    raw_response: Optional[dict] = None
