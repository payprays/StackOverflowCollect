import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv
from .utils.model_name import model_token


logger = logging.getLogger(__name__)

EVALUATION_SYSTEM_PROMPT = """你是一名研究型专家，专注评估 LLM 生成的 Kubernetes/云原生答案与 YAML。请用中文给出简明结论，重点关注：
1) 正确性：API 版本/字段/缩进是否符合规范？是否引用不存在的 CRD、占位符或过时字段？逻辑上能否解决原问题？
2) 幻觉：是否编造了资源、字段、命令或行为（特别是未声明的 CRD/operator/插件）？标记出可能的幻觉点。
3) 可运行性与可运维性：缺失的必需字段（selector、labels、ports）、探针、资源限制、安全上下文、镜像可拉取性、命名空间/依赖关系。
4) 改进建议：若有问题，给出更好的修订思路或示例片段，并解释原因。
输出中文，不重复提示。"""

ANSWER_SYSTEM_PROMPT = """你是一名 Kubernetes/云原生专家，请用中文回答。要求：
1) 先简要说明问题成因或诊断思路。
2) 给出可直接应用的完整 YAML 示例（如 Deployment/Service/Ingress 等），必要时包含命名空间、选择器、端口、探针、资源限制与安全配置，避免占位符，完整的可部署yaml示例应该使用```yaml: complete```包裹。
3) 若依赖额外组件（Ingress Controller、CRD/Operator 等），明确指出前置条件。
如果实在缺少完整的其他示例，使用最小的完整YAML实践方式。
回答保持简洁、步骤清晰。"""


class Evaluator:
    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1/chat/completions",
        api_key: Optional[str] = None,
        model: str | bool = False,
        session: Optional[httpx.Client] = None,
        mode: str = "answer",
    ) -> None:
        if model == "gpt-4o":
            self.base_url = "http://localhost:4141/v1/chat/completions"
        else:
            self.base_url = self._normalize_url(base_url)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            # Try loading from .env if not provided
            load_dotenv()
            self.api_key = os.getenv("OPENAI_API_KEY")

        self.model_answer = model
        self.model_evaluate = model
        self.mode = mode
        self._client = session or httpx.Client(timeout=httpx.Timeout(60.0))

    def _normalize_url(self, url: str) -> str:
        """Ensures the URL ends with /v1/chat/completions if it looks like a base URL."""
        if not url.endswith("/v1/chat/completions"):
            return f"{url.rstrip('/')}/v1/chat/completions"
        return url

    def generate_answer(self, question_content: str) -> str:
        """Generates an answer for the given question using the answer model."""
        payload = {
            "model": self.model_answer,
            "messages": [
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": question_content},
            ],
            "temperature": 0.2,
        }
        return self._call_llm(payload, url=self.base_url)

    def evaluate(
        self,
        question_answer_content: str,
        gpt_answer_content: str,
        answer_model: str,
    ) -> str:
        """Evaluates the GPT answer against the original Q&A using the evaluation model."""
        answer_label = model_token(answer_model)
        user_content = (
            f"# Question and Original Answer\n{question_answer_content}\n\n"
            f"# {answer_label} Answer\n{gpt_answer_content}"
        )
        payload = {
            "model": self.model_evaluate,
            "messages": [
                {"role": "system", "content": EVALUATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.2,
        }
        return self._call_llm(payload, url=self.base_url)

    def _call_llm(self, payload: dict, url: str) -> str:
        if not self.api_key:
            raise RuntimeError("Missing API Key for Evaluator")

        import time

        max_retries = 3
        for attempt in range(max_retries):
            try:
                resp = self._client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
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
