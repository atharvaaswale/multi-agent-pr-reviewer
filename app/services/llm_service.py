import json
import os
import time
from typing import Any

import structlog
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)


class LLMServiceError(Exception):
    pass


def _log_retry_attempt(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception()
    logger.warning(
        "llm_request_retry",
        attempt_number=retry_state.attempt_number,
        error_type=type(exc).__name__,
        error=str(exc),
    )


class LLMService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ["NVIDIA_API_KEY"]
        self.model = model or os.environ.get("NVIDIA_MODEL", "stepfun-ai/step-3.5-flash")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._client = ChatNVIDIA(
            model=self.model,
            api_key=self.api_key,
            temperature=self.temperature,
            top_p=0.9,
            max_tokens=self.max_tokens,
        )

    async def close(self) -> None:
        pass

    @retry(
        retry=retry_if_exception_type((Exception,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
        before_sleep=_log_retry_attempt,
    )
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "llm_request_start",
            model=self.model,
            provider="nvidia",
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        start = time.monotonic()

        langchain_messages = [(m["role"], m["content"]) for m in messages]
        response = self._client.invoke(langchain_messages)

        content = response.content if hasattr(response, "content") else str(response)

        parsed = self._parse_json(content)

        elapsed = time.monotonic() - start
        response_size = len(content)

        logger.info(
            "llm_request_success",
            model=self.model,
            provider="nvidia",
            latency=round(elapsed, 2),
            response_size=response_size,
        )

        return parsed

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        content = content.strip()

        if content.startswith("```json"):
            content = content.removeprefix("```json").removesuffix("```").strip()
        elif content.startswith("```"):
            content = content.removeprefix("```").removesuffix("```").strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("llm_json_parse_failed", error=str(exc), content_preview=content[:200])
            raise LLMServiceError(f"Failed to parse LLM response as JSON: {exc}") from exc
