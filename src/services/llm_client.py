import logging
import time
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        session: Optional[httpx.Client] = None,
    ) -> None:
        self.base_url = self._normalize_url(base_url)
        self.api_key = api_key
        self.model = model
        self._client = session or httpx.Client(timeout=httpx.Timeout(60.0))

    def _normalize_url(self, url: str) -> str:
        """Ensures the URL ends with /v1/chat/completions if it looks like a base URL."""
        if not url.endswith("/v1/chat/completions"):
            return f"{url.rstrip('/')}/v1/chat/completions"
        return url

    def chat_completion_full(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> tuple[str, Dict[str, Any]]:
        """
        Sends a chat completion request to the LLM and returns (content, raw_response).
        """
        if not self.api_key:
            raise RuntimeError("Missing API Key for LLMClient")

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        for attempt in range(max_retries):
            try:
                resp = self._client.post(
                    self.base_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                return content, data
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500 and attempt < max_retries - 1:
                    logger.warning(
                        "LLM server error %s, retrying (%d/%d)...",
                        exc.response.status_code,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(2)
                    continue
                logger.error("LLM call failed: %s", exc)
                raise
            except httpx.HTTPError as exc:
                logger.error("LLM call failed: %s", exc)
                raise

        raise RuntimeError("Max retries exceeded")

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_retries: int = 3,
    ) -> str:
        """Wrapper for backward compatibility returning only content string."""
        content, _ = self.chat_completion_full(messages, temperature, max_retries)
        return content
