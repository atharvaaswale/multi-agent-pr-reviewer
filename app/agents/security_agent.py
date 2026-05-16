import time

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.schemas.review import AgentReview, Finding, FindingCategory, Severity
from app.services.llm_service import LLMService, LLMServiceError

logger = structlog.get_logger(__name__)

SYSTEM_PROMPT = """You are a security engineer reviewing a pull request.

Analyze the provided diffs for security vulnerabilities including:
- Exposed secrets, API keys, credentials
- Unsafe deserialization (pickle, yaml.load, eval, exec)
- SQL injection risks
- Authentication/authorization bypasses
- Dangerous subprocess or shell execution
- Insecure configurations (debug mode, permissive CORS, etc.)
- Path traversal vulnerabilities
- Insecure cryptographic practices

Return your findings as a JSON object with this exact schema:
{
  "summary": "Brief security assessment summary",
  "confidence": 0.0 to 1.0,
  "findings": [
    {
      "title": "Short finding title",
      "description": "Detailed explanation",
      "severity": "critical|high|medium|low|info",
      "category": "security",
      "file_path": "path/to/file.py",
      "line_number": 42,
      "code_snippet": "relevant code",
      "suggested_fix": "how to fix it"
    }
  ]
}

If no security issues are found, return an empty findings array with a summary stating the code appears secure.
Return ONLY valid JSON. No markdown, no explanations."""


def build_user_prompt(pr_title: str, pr_body: str, diffs: dict[str, str]) -> str:
    parts = [f"Pull Request: {pr_title}", f"Description: {pr_body}", ""]

    if not diffs:
        parts.append("No file diffs available for review.")
    else:
        parts.append(f"Changed files ({len(diffs)}):")
        for filename, diff in diffs.items():
            parts.append(f"\n--- {filename} ---\n{diff}")

    return "\n".join(parts)


@retry(
    retry=retry_if_exception_type(LLMServiceError),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
)
async def run_security_review(
    llm: LLMService,
    pr_title: str,
    pr_body: str,
    diffs: dict[str, str],
) -> AgentReview:
    start = time.monotonic()

    logger.info("security_agent_started", file_count=len(diffs))

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(pr_title, pr_body, diffs)},
    ]

    response = await llm.chat_completion(messages)

    findings = [
        Finding(
            title=f["title"],
            description=f["description"],
            severity=Severity(f["severity"]),
            category=FindingCategory.security,
            file_path=f.get("file_path"),
            line_number=f.get("line_number"),
            code_snippet=f.get("code_snippet"),
            suggested_fix=f.get("suggested_fix"),
        )
        for f in response.get("findings", [])
    ]

    elapsed = time.monotonic() - start

    review = AgentReview(
        agent_name="security",
        summary=response["summary"],
        confidence=response["confidence"],
        findings=findings,
        agent_execution_time=round(elapsed, 2),
    )

    logger.info(
        "security_agent_completed",
        finding_count=len(findings),
        confidence=review.confidence,
        execution_time=review.agent_execution_time,
    )

    return review
