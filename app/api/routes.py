from pydantic import BaseModel, Field

import structlog
from fastapi import APIRouter, HTTPException, status

from app.github.client import GitHubClient
from app.graph.state import WorkflowState
from app.graph.workflow import build_workflow
from app.schemas.review import AggregatedReview

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1")


class PRReviewRequest(BaseModel):
    pr_url: str = Field(..., description="GitHub pull request URL")


class PRReviewResponse(BaseModel):
    review: AggregatedReview
    execution_time_seconds: float | None
    failed_agents: list[str]


class ErrorResponse(BaseModel):
    detail: str


@router.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@router.post(
    "/review",
    response_model=PRReviewResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def review_pr(request: PRReviewRequest) -> PRReviewResponse:
    logger.info("review_request_received", pr_url=request.pr_url)

    github_client = GitHubClient()

    try:
        owner, repo, pr_number = github_client.parse_pr_url(request.pr_url)
        metadata, changed_files, diffs = github_client.fetch_pr_data(request.pr_url)
    except Exception as exc:
        logger.error("github_fetch_failed", pr_url=request.pr_url, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch PR data: {exc}",
        ) from exc

    state = WorkflowState(
        pr_url=request.pr_url,
        repo_owner=owner,
        repo_name=repo,
        pr_number=pr_number,
        pr_title=metadata.title,
        pr_body=metadata.body,
        commit_sha=metadata.head_sha,
        changed_files=[f.filename for f in changed_files],
        diffs=diffs,
    )

    logger.info("workflow_starting", pr_number=pr_number, file_count=len(changed_files))

    workflow = build_workflow().compile()

    try:
        final_state = await workflow.ainvoke(state.model_dump())
    except Exception as exc:
        logger.error("workflow_execution_failed", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow execution failed: {exc}",
        ) from exc

    aggregated = final_state.get("aggregated_review")
    if not aggregated:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workflow completed without aggregated review",
        )

    response = PRReviewResponse(
        review=aggregated,
        execution_time_seconds=final_state.get("execution_time_seconds"),
        failed_agents=final_state.get("failed_agents", []),
    )

    logger.info(
        "review_completed",
        pr_number=pr_number,
        finding_count=len(aggregated.findings),
        failed_agents=response.failed_agents,
    )

    return response
