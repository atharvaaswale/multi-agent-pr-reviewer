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

SYSTEM_PROMPT = """You are a senior code quality engineer reviewing a pull request.

Your scope is STRICTLY readability, naming, comments, and maintainability.
Analyze the provided diffs only for code-quality issues, including:
- Readability issues (unclear logic, complex expressions, overly long functions)
- Naming issues (unclear, misleading, or inconsistent names)
- Missing, outdated, or unhelpful comments and docstrings
- Duplicated logic or copy-paste code
- Missing or inadequate error handling
- Code style inconsistencies and small maintainability improvements

Do NOT report security vulnerabilities, nor architectural concerns such as
module coupling, system design, or scalability. Dedicated security and
architecture agents own those areas; raising them here only creates duplicate
findings. If an issue is not a readability, naming, comment, or
maintainability concern, omit it entirely.

Return your findings as a JSON object with this exact schema:
{
  "summary": "Brief quality assessment summary",
  "confidence": 0.0 to 1.0,
  "findings": [
    {
      "title": "Short finding title",
      "description": "Detailed explanation",
      "severity": "critical|high|medium|low|info",
      "category": "quality",
      "file_path": "path/to/file.py",
      "line_number": 42,
      "code_snippet": "relevant code",
      "suggested_fix": "how to fix it"
    }
  ]
}

If no quality issues are found, return an empty findings array with a summary stating the code quality appears good.
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
async def run_quality_review(
    llm: LLMService,
    pr_title: str,
    pr_body: str,
    diffs: dict[str, str],
) -> AgentReview:
    start = time.monotonic()

    logger.info(
        "agent_started",
        agent="quality",
        file_count=len(diffs),
    )

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
            category=FindingCategory.quality,
            file_path=f.get("file_path"),
            line_number=f.get("line_number"),
            code_snippet=f.get("code_snippet"),
            suggested_fix=f.get("suggested_fix"),
        )
        for f in response.get("findings", [])
    ]

    elapsed = time.monotonic() - start

    review = AgentReview(
        agent_name="quality",
        summary=response["summary"],
        confidence=response["confidence"],
        findings=findings,
        agent_execution_time=round(elapsed, 2),
    )

    logger.info(
        "agent_completed",
        agent="quality",
        finding_count=len(findings),
        confidence=review.confidence,
        latency=round(elapsed, 2),
    )

    return review
