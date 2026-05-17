import json
import os
import time
from typing import Any

import httpx
import structlog
from tenacity import (
    RetryCallState,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = structlog.get_logger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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
        self.api_key = api_key or os.environ["OPENROUTER_API_KEY"]
        self.model = model or os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-20250514")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=OPENROUTER_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.environ.get("APP_URL", "http://localhost:8000"),
                "X-Title": "Multi-Agent PR Reviewer",
            },
            timeout=httpx.Timeout(self.timeout),
        )

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
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
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        if response_format:
            payload["response_format"] = response_format

        start = time.monotonic()
        logger.info("llm_request_start", model=self.model, max_tokens=self.max_tokens, temperature=self.temperature)

        response = await self._client.post("/chat/completions", json=payload)
        response.raise_for_status()

        data = response.json()
        content = data["choices"][0]["message"]["content"]

        parsed = self._parse_json(content)

        elapsed = time.monotonic() - start
        usage = data.get("usage", {})

        logger.info(
            "llm_request_success",
            model=self.model,
            latency=round(elapsed, 2),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
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
