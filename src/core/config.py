import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Settings:
    # Stack Overflow / Stack Exchange
    STACK_API_KEY: Optional[str] = os.getenv("STACK_API_KEY")

    # OpenAI / LLM
    OPENAI_BASE_URL: str = os.getenv(
        "OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions"
    )
    OPENAI_API_KEY: Optional[str] = os.getenv("OPENAI_API_KEY")

    # Local Model
    LOCAL_MODEL_URL: str = os.getenv(
        "LOCAL_MODEL_URL", "http://localhost:4141/v1/chat/completions"
    )

    # Defaults
    DEFAULT_MODEL_ANSWER: str = "gpt-4o"
    DEFAULT_MODEL_EVALUATE: str = "gpt-4o"
    DEFAULT_TIMEOUT: float = 60.0


settings = Settings()
