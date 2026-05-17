from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Severity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


class FindingCategory(str, Enum):
    security = "security"
    architecture = "architecture"
    quality = "quality"
    performance = "performance"
    maintainability = "maintainability"


class Finding(BaseModel):
    title: str
    description: str
    severity: Severity
    category: FindingCategory
    file_path: str | None = None
    line_number: int | None = None
    code_snippet: str | None = None
    suggested_fix: str | None = None


class AgentReview(BaseModel):
    agent_name: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[Finding] = Field(default_factory=list)
    agent_execution_time: float | None = None


class AggregatedReview(BaseModel):
    pr_url: str
    pr_title: str
    pr_number: int
    summary: str
    overall_confidence: float = Field(ge=0.0, le=1.0)
    overall_severity: Severity
    findings: list[Finding] = Field(default_factory=list)
    agent_reviews: list[AgentReview] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approved: bool = False
    requires_approval: bool = False

    @field_validator("findings")
    @classmethod
    def sort_findings_by_severity(cls, v: list[Finding]) -> list[Finding]:
        severity_order = {
            Severity.critical: 0,
            Severity.high: 1,
            Severity.medium: 2,
            Severity.low: 3,
            Severity.info: 4,
        }
        return sorted(v, key=lambda f: severity_order.get(f.severity, 5))
