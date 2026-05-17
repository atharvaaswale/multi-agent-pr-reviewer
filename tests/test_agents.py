import pytest

from app.agents.architecture_agent import build_user_prompt as build_arch_prompt
from app.agents.architecture_agent import run_architecture_review
from app.agents.quality_agent import build_user_prompt as build_quality_prompt
from app.agents.quality_agent import run_quality_review
from app.agents.security_agent import build_user_prompt as build_security_prompt
from app.agents.security_agent import run_security_review
from app.schemas.review import FindingCategory, Severity
from app.services.llm_service import LLMServiceError


class FakeLLMService:
    def __init__(self, response: dict):
        self._response = response
        self.chat_called = False

    async def chat_completion(self, messages):
        self.chat_called = True
        return self._response

    async def close(self):
        pass


VALID_RESPONSE = {
    "summary": "Test summary",
    "confidence": 0.85,
    "findings": [
        {
            "title": "Test finding",
            "description": "A test finding",
            "severity": "high",
            "category": "security",
            "file_path": "test.py",
            "line_number": 10,
            "code_snippet": "code",
            "suggested_fix": "fix it",
        }
    ],
}

EMPTY_RESPONSE = {
    "summary": "No issues found",
    "confidence": 0.95,
    "findings": [],
}


class TestBuildUserPrompt:
    def test_security_prompt_with_diffs(self):
        result = build_security_prompt("Fix bug", "Fixes a bug", {"app.py": "+print('hello')"})
        assert "Pull Request: Fix bug" in result
        assert "Description: Fixes a bug" in result
        assert "--- app.py ---" in result
        assert "+print('hello')" in result

    def test_security_prompt_without_diffs(self):
        result = build_security_prompt("Title", "Body", {})
        assert "No file diffs available" in result

    def test_architecture_prompt_with_diffs(self):
        result = build_arch_prompt("Refactor", "Restructure", {"core.py": "diff"})
        assert "Pull Request: Refactor" in result
        assert "--- core.py ---" in result

    def test_quality_prompt_with_diffs(self):
        result = build_quality_prompt("Cleanup", "Clean up", {"util.py": "diff"})
        assert "Pull Request: Cleanup" in result
        assert "--- util.py ---" in result

    def test_prompt_includes_file_count(self):
        diffs = {"a.py": "x", "b.py": "y", "c.py": "z"}
        result = build_security_prompt("Title", "Body", diffs)
        assert "Changed files (3)" in result


class TestSecurityAgent:
    @pytest.mark.asyncio
    async def test_successful_review_with_findings(self):
        llm = FakeLLMService(VALID_RESPONSE)
        review = await run_security_review(llm, "Title", "Body", {"test.py": "diff"})

        assert review.agent_name == "security"
        assert review.summary == "Test summary"
        assert review.confidence == 0.85
        assert len(review.findings) == 1
        assert review.findings[0].severity == Severity.high
        assert review.findings[0].category == FindingCategory.security
        assert review.agent_execution_time is not None

    @pytest.mark.asyncio
    async def test_successful_review_no_findings(self):
        llm = FakeLLMService(EMPTY_RESPONSE)
        review = await run_security_review(llm, "Title", "Body", {})

        assert len(review.findings) == 0
        assert review.summary == "No issues found"

    @pytest.mark.asyncio
    async def test_llm_error_raises(self):
        class FailingLLM:
            async def chat_completion(self, messages):
                raise LLMServiceError("API error")

            async def close(self):
                pass

        llm = FailingLLM()
        with pytest.raises(LLMServiceError):
            await run_security_review(llm, "Title", "Body", {"test.py": "diff"})


class TestArchitectureAgent:
    @pytest.mark.asyncio
    async def test_successful_review_with_findings(self):
        response = {
            "summary": "Architecture review summary",
            "confidence": 0.7,
            "findings": [
                {
                    "title": "Tight coupling",
                    "description": "Modules are tightly coupled",
                    "severity": "medium",
                    "category": "architecture",
                    "file_path": "core.py",
                    "line_number": 5,
                }
            ],
        }
        llm = FakeLLMService(response)
        review = await run_architecture_review(llm, "Title", "Body", {"core.py": "diff"})

        assert review.agent_name == "architecture"
        assert len(review.findings) == 1
        assert review.findings[0].category == FindingCategory.architecture
        assert review.findings[0].severity == Severity.medium

    @pytest.mark.asyncio
    async def test_successful_review_no_findings(self):
        llm = FakeLLMService(EMPTY_RESPONSE)
        review = await run_architecture_review(llm, "Title", "Body", {})

        assert len(review.findings) == 0


class TestQualityAgent:
    @pytest.mark.asyncio
    async def test_successful_review_with_findings(self):
        response = {
            "summary": "Quality review summary",
            "confidence": 0.9,
            "findings": [
                {
                    "title": "Unclear variable name",
                    "description": "Variable x is unclear",
                    "severity": "low",
                    "category": "quality",
                    "file_path": "util.py",
                    "line_number": 15,
                    "suggested_fix": "Rename to descriptive name",
                }
            ],
        }
        llm = FakeLLMService(response)
        review = await run_quality_review(llm, "Title", "Body", {"util.py": "diff"})

        assert review.agent_name == "quality"
        assert len(review.findings) == 1
        assert review.findings[0].category == FindingCategory.quality
        assert review.findings[0].suggested_fix is not None

    @pytest.mark.asyncio
    async def test_successful_review_no_findings(self):
        llm = FakeLLMService(EMPTY_RESPONSE)
        review = await run_quality_review(llm, "Title", "Body", {})

        assert len(review.findings) == 0


class TestMalformedLLMResponses:
    @pytest.mark.asyncio
    async def test_missing_summary_raises(self):
        response = {"confidence": 0.8, "findings": []}
        llm = FakeLLMService(response)
        with pytest.raises(KeyError):
            await run_security_review(llm, "Title", "Body", {})

    @pytest.mark.asyncio
    async def test_missing_confidence_raises(self):
        response = {"summary": "ok", "findings": []}
        llm = FakeLLMService(response)
        with pytest.raises(KeyError):
            await run_security_review(llm, "Title", "Body", {})

    @pytest.mark.asyncio
    async def test_invalid_severity_raises(self):
        response = {
            "summary": "ok",
            "confidence": 0.8,
            "findings": [
                {
                    "title": "Test",
                    "description": "Test",
                    "severity": "invalid",
                    "category": "security",
                }
            ],
        }
        llm = FakeLLMService(response)
        with pytest.raises(ValueError):
            await run_security_review(llm, "Title", "Body", {})

    @pytest.mark.asyncio
    async def test_empty_findings_handled(self):
        response = {"summary": "ok", "confidence": 0.8, "findings": []}
        llm = FakeLLMService(response)
        review = await run_security_review(llm, "Title", "Body", {})
        assert review.findings == []

    @pytest.mark.asyncio
    async def test_missing_optional_fields_defaults(self):
        response = {
            "summary": "ok",
            "confidence": 0.8,
            "findings": [
                {
                    "title": "Test",
                    "description": "Test",
                    "severity": "low",
                    "category": "security",
                }
            ],
        }
        llm = FakeLLMService(response)
        review = await run_security_review(llm, "Title", "Body", {})

        finding = review.findings[0]
        assert finding.file_path is None
        assert finding.line_number is None
        assert finding.code_snippet is None
        assert finding.suggested_fix is None
