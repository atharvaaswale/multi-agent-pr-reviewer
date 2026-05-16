from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from app.schemas.review import AgentReview, AggregatedReview


class ApprovalStatus(str, Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class WorkflowStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class WorkflowState(BaseModel):
    pr_url: str
    repo_owner: str
    repo_name: str
    pr_number: int
    pr_title: str = ""
    pr_body: str = ""
    commit_sha: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    diffs: dict[str, str] = Field(default_factory=dict)
    security_review: AgentReview | None = None
    architecture_review: AgentReview | None = None
    quality_review: AgentReview | None = None
    failed_agents: list[str] = Field(default_factory=list)
    aggregated_review: AggregatedReview | None = None
    approval_status: ApprovalStatus = ApprovalStatus.pending
    workflow_status: WorkflowStatus = WorkflowStatus.pending
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    execution_time_seconds: float | None = None
