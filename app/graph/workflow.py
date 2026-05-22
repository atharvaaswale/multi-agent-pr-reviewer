import uuid
from datetime import datetime, timezone

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.architecture_agent import run_architecture_review
from app.agents.quality_agent import run_quality_review
from app.agents.security_agent import run_security_review
from app.github.client import GitHubClient
from app.graph.state import ApprovalStatus, WorkflowState, WorkflowStatus
from app.schemas.review import AgentReview, AggregatedReview, Severity
from app.services.llm_service import LLMService
from app.services.review_service import format_review_body
from app.utils.dedup import deduplicate_findings

logger = structlog.get_logger(__name__)


def _build_llm_service() -> LLMService:
    return LLMService()


async def security_review_node(state: WorkflowState) -> dict:
    llm = _build_llm_service()
    try:
        review = await run_security_review(
            llm=llm,
            pr_title=state.pr_title,
            pr_body=state.pr_body,
            diffs=state.diffs,
        )
        logger.info(
            "workflow_node_success",
            node="security_review",
            pr_number=state.pr_number,
            finding_count=len(review.findings),
            latency=review.agent_execution_time,
        )
        return {"security_review": review}
    except Exception as exc:
        logger.error(
            "workflow_node_failed",
            node="security_review",
            pr_number=state.pr_number,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {"security_error": str(exc)}
    finally:
        await llm.close()


async def architecture_review_node(state: WorkflowState) -> dict:
    llm = _build_llm_service()
    try:
        review = await run_architecture_review(
            llm=llm,
            pr_title=state.pr_title,
            pr_body=state.pr_body,
            diffs=state.diffs,
        )
        logger.info(
            "workflow_node_success",
            node="architecture_review",
            pr_number=state.pr_number,
            finding_count=len(review.findings),
            latency=review.agent_execution_time,
        )
        return {"architecture_review": review}
    except Exception as exc:
        logger.error(
            "workflow_node_failed",
            node="architecture_review",
            pr_number=state.pr_number,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {"architecture_error": str(exc)}
    finally:
        await llm.close()


async def quality_review_node(state: WorkflowState) -> dict:
    llm = _build_llm_service()
    try:
        review = await run_quality_review(
            llm=llm,
            pr_title=state.pr_title,
            pr_body=state.pr_body,
            diffs=state.diffs,
        )
        logger.info(
            "workflow_node_success",
            node="quality_review",
            pr_number=state.pr_number,
            finding_count=len(review.findings),
            latency=review.agent_execution_time,
        )
        return {"quality_review": review}
    except Exception as exc:
        logger.error(
            "workflow_node_failed",
            node="quality_review",
            pr_number=state.pr_number,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {"quality_error": str(exc)}
    finally:
        await llm.close()


def aggregation_node(state: WorkflowState) -> dict:
    agent_reviews: list[AgentReview] = []
    all_findings = []
    failed_agents = []

    if state.security_review:
        agent_reviews.append(state.security_review)
        all_findings.extend(state.security_review.findings)
    elif state.security_error:
        failed_agents.append("security")

    if state.architecture_review:
        agent_reviews.append(state.architecture_review)
        all_findings.extend(state.architecture_review.findings)
    elif state.architecture_error:
        failed_agents.append("architecture")

    if state.quality_review:
        agent_reviews.append(state.quality_review)
        all_findings.extend(state.quality_review.findings)
    elif state.quality_error:
        failed_agents.append("quality")

    raw_finding_count = len(all_findings)
    all_findings = deduplicate_findings(all_findings)
    duplicates_removed = raw_finding_count - len(all_findings)

    completed_agents = [r.agent_name for r in agent_reviews]

    if not agent_reviews:
        overall_confidence = 0.0
        overall_severity = Severity.info
        summary = "No agent reviews completed."
    else:
        overall_confidence = round(
            sum(r.confidence for r in agent_reviews) / len(agent_reviews), 2
        )
        severity_scores = {
            Severity.critical: 4,
            Severity.high: 3,
            Severity.medium: 2,
            Severity.low: 1,
            Severity.info: 0,
        }
        max_sev = max(
            (f.severity for f in all_findings),
            key=lambda s: severity_scores.get(s, 0),
            default=Severity.info,
        )
        overall_severity = max_sev if all_findings else Severity.info
        summary = _build_summary(agent_reviews)

    warnings = []
    if failed_agents:
        warnings.append(f"Failed agents: {', '.join(failed_agents)}")

    requires_approval = _requires_human_approval(all_findings, failed_agents)

    aggregated = AggregatedReview(
        pr_url=state.pr_url,
        pr_title=state.pr_title,
        pr_number=state.pr_number,
        summary=summary,
        overall_confidence=overall_confidence,
        overall_severity=overall_severity,
        findings=all_findings,
        agent_reviews=agent_reviews,
        warnings=warnings,
        requires_approval=requires_approval,
    )

    elapsed = (datetime.now(timezone.utc) - state.created_at).total_seconds()

    logger.info(
        "workflow_aggregation_completed",
        pr_number=state.pr_number,
        completed_agents=completed_agents,
        failed_agents=failed_agents,
        finding_count=len(all_findings),
        duplicates_removed=duplicates_removed,
        overall_confidence=overall_confidence,
        overall_severity=overall_severity.value,
        requires_approval=requires_approval,
        elapsed=round(elapsed, 2),
    )

    return {
        "aggregated_review": aggregated,
        "workflow_status": WorkflowStatus.completed,
        "completed_at": datetime.now(timezone.utc),
        "execution_time_seconds": round(elapsed, 2),
        "failed_agents": failed_agents,
    }


def _build_summary(agent_reviews: list[AgentReview]) -> str:
    parts = []
    for review in agent_reviews:
        parts.append(f"**{review.agent_name}**: {review.summary}")
    return "\n\n".join(parts)


def _requires_human_approval(findings: list, failed_agents: list[str]) -> bool:
    if failed_agents:
        return True

    for f in findings:
        if f.severity in (Severity.critical, Severity.high):
            return True

    return False


def human_approval_node(state: WorkflowState) -> dict:
    review = state.aggregated_review

    if review is None:
        logger.warning(
            "human_approval_no_review",
            pr_number=state.pr_number,
        )
        return {
            "approval_status": ApprovalStatus.rejected,
            "workflow_status": WorkflowStatus.completed,
        }

    if not review.requires_approval:
        logger.info(
            "human_approval_auto_approved",
            pr_number=state.pr_number,
            overall_severity=review.overall_severity.value,
            overall_confidence=review.overall_confidence,
        )
        return {
            "aggregated_review": AggregatedReview(
                **{**review.model_dump(), "approved": True},
            ),
            "approval_status": ApprovalStatus.approved,
            "workflow_status": WorkflowStatus.completed,
        }

    logger.info(
        "human_approval_required",
        pr_number=state.pr_number,
        overall_severity=review.overall_severity.value,
        finding_count=len(review.findings),
        failed_agents=state.failed_agents,
    )

    return {
        "approval_status": ApprovalStatus.rejected,
        "workflow_status": WorkflowStatus.completed,
    }


def post_review_node(state: WorkflowState) -> dict:
    if state.approval_status != ApprovalStatus.approved:
        logger.info(
            "post_review_skipped",
            pr_number=state.pr_number,
            approval_status=state.approval_status.value,
        )
        return {}

    review = state.aggregated_review
    if review is None:
        logger.warning("post_review_no_review", pr_number=state.pr_number)
        return {}

    try:
        client = GitHubClient()
        body = format_review_body(review)
        client.post_pr_review(state.repo_owner, state.repo_name, state.pr_number, body)
        logger.info(
            "github_review_posted",
            pr_number=state.pr_number,
            repo=f"{state.repo_owner}/{state.repo_name}",
            overall_severity=review.overall_severity.value,
            finding_count=len(review.findings),
        )
        return {"workflow_status": WorkflowStatus.completed}
    except Exception as exc:
        logger.error(
            "github_review_post_failed",
            pr_number=state.pr_number,
            repo=f"{state.repo_owner}/{state.repo_name}",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        warnings = state.aggregated_review.warnings + [f"Failed to post review: {exc}"]
        return {
            "aggregated_review": AggregatedReview(
                **{**review.model_dump(), "warnings": warnings},
            ),
            "workflow_status": WorkflowStatus.completed,
        }


def build_workflow() -> StateGraph:
    graph = StateGraph(WorkflowState)

    graph.add_node("security_review", security_review_node)
    graph.add_node("architecture_review", architecture_review_node)
    graph.add_node("quality_review", quality_review_node)
    graph.add_node("aggregate", aggregation_node)
    graph.add_node("human_approval", human_approval_node)
    graph.add_node("post_review", post_review_node)

    graph.add_edge(START, "security_review")
    graph.add_edge(START, "architecture_review")
    graph.add_edge(START, "quality_review")

    graph.add_edge("security_review", "aggregate")
    graph.add_edge("architecture_review", "aggregate")
    graph.add_edge("quality_review", "aggregate")

    graph.add_edge("aggregate", "human_approval")
    graph.add_edge("human_approval", "post_review")
    graph.add_edge("post_review", END)

    return graph


async def run_workflow(pr_url: str, repo_owner: str, repo_name: str, pr_number: int, **kwargs) -> dict:
    workflow_id = str(uuid.uuid4())[:8]

    logger.info(
        "workflow_started",
        workflow_id=workflow_id,
        pr_url=pr_url,
        pr_number=pr_number,
        repo=f"{repo_owner}/{repo_name}",
    )

    initial_state = WorkflowState(
        pr_url=pr_url,
        repo_owner=repo_owner,
        repo_name=repo_name,
        pr_number=pr_number,
        **kwargs,
    )

    graph = build_workflow().compile()
    result = await graph.ainvoke(initial_state)

    final_state = result if isinstance(result, dict) else result.model_dump()
    review = final_state.get("aggregated_review")

    logger.info(
        "workflow_completed",
        workflow_id=workflow_id,
        pr_number=pr_number,
        approval_status=final_state.get("approval_status", "unknown"),
        overall_severity=review.overall_severity.value if review else "unknown",
        finding_count=len(review.findings) if review else 0,
        failed_agents=final_state.get("failed_agents", []),
        execution_time=final_state.get("execution_time_seconds"),
    )

    return final_state
