from __future__ import annotations

import logging
import time
from datetime import datetime, UTC
from typing import Iterable, Iterator, List, Optional, Tuple

import httpx

from src.domain.models import Answer, Question

STACK_EXCHANGE_API = "https://api.stackexchange.com/2.3"

logger = logging.getLogger(__name__)


def _to_datetime(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, UTC)


class StackOverflowClient:
    def __init__(
        self, session: httpx.Client | None = None, key: Optional[str] = None
    ) -> None:
        self._client = session or httpx.Client(timeout=15)
        self.key = key

    def fetch_paginated_questions(
        self,
        tag: str = "kubernetes",
        limit: int = 100,
        page_size: int = 50,
        start_page: int = 1,
    ) -> Iterator[Tuple[int, List[Question]]]:
        fetched = 0
        page = start_page
        while fetched < limit:
            params = {
                "order": "desc",
                "sort": "creation",
                "tagged": tag,
                "site": "stackoverflow",
                "pagesize": min(page_size, 100),
                "page": page,
                "filter": "withbody",
            }
            if self.key:
                params["key"] = self.key
            logger.info(
                "Fetching questions page %s for tag '%s' (page_size=%s)",
                page,
                tag,
                page_size,
            )
            resp = self._client.get(f"{STACK_EXCHANGE_API}/questions", params=params)
            resp.raise_for_status()
            data = resp.json()
            backoff = data.get("backoff")
            quota_remaining = data.get("quota_remaining")
            if quota_remaining is not None and quota_remaining < 10:
                logger.warning(
                    "Low Stack Exchange quota remaining: %s", quota_remaining
                )
            items = data.get("items", [])
            questions: List[Question] = []
            for item in items:
                questions.append(
                    Question(
                        question_id=item["question_id"],
                        title=item.get("title", ""),
                        body=item.get("body", ""),
                        creation_date=_to_datetime(item["creation_date"]),
                        link=item.get("link", ""),
                        tags=item.get("tags", []),
                    )
                )
            if not questions:
                break
            yield page, questions[: max(0, limit - fetched)]
            fetched += len(questions)
            if not data.get("has_more") or fetched >= limit:
                break
            page += 1
            if backoff:
                logger.info("API asked for backoff: sleeping %s seconds", backoff)
                time.sleep(backoff)

    def fetch_answers(self, question_id: int, pagesize: int = 10) -> List[Answer]:
        params = {
            "order": "desc",
            "sort": "creation",
            "site": "stackoverflow",
            "filter": "withbody",
            "pagesize": pagesize,
        }
        if self.key:
            params["key"] = self.key
        resp = self._client.get(
            f"{STACK_EXCHANGE_API}/questions/{question_id}/answers", params=params
        )
        resp.raise_for_status()
        data = resp.json()
        answers: List[Answer] = []
        for item in data.get("items", []):
            answers.append(
                Answer(
                    answer_id=item["answer_id"],
                    body=item.get("body", ""),
                    creation_date=_to_datetime(item["creation_date"]),
                    is_accepted=item.get("is_accepted", False),
                    link=item.get("link", ""),
                    score=item.get("score", 0),
                )
            )
        return answers

    def fetch_with_answers(
        self, tag: str = "kubernetes", limit: int = 5
    ) -> Iterable[Question]:
        for question in self.fetch_recent_questions(tag=tag, limit=limit):
            try:
                question.answers = self.fetch_answers(question.question_id)
            except httpx.HTTPError as exc:
                logger.warning("Failed to fetch answers for %s: %s", question.link, exc)
                question.answers = []
            yield question
