import time
from datetime import datetime, timezone

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.security_agent import run_security_review
from app.graph.state import WorkflowState, WorkflowStatus
from app.schemas.review import AgentReview, AggregatedReview, Severity
from app.services.llm_service import LLMService

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
        logger.info("workflow_security_success", finding_count=len(review.findings))
        return {"security_review": review}
    except Exception as exc:
        logger.error("workflow_security_failed", error=str(exc))
        return {"failed_agents": state.failed_agents + ["security"]}
    finally:
        await llm.close()


def aggregation_node(state: WorkflowState) -> dict:
    agent_reviews: list[AgentReview] = []
    all_findings = []

    if state.security_review:
        agent_reviews.append(state.security_review)
        all_findings.extend(state.security_review.findings)

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
    if state.failed_agents:
        warnings.append(f"Failed agents: {', '.join(state.failed_agents)}")

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
    )

    elapsed = (datetime.now(timezone.utc) - state.created_at).total_seconds()

    logger.info(
        "workflow_aggregation_completed",
        finding_count=len(all_findings),
        overall_confidence=overall_confidence,
        failed_agents=state.failed_agents,
    )

    return {
        "aggregated_review": aggregated,
        "workflow_status": WorkflowStatus.completed,
        "completed_at": datetime.now(timezone.utc),
        "execution_time_seconds": round(elapsed, 2),
    }


def _build_summary(agent_reviews: list[AgentReview]) -> str:
    parts = []
    for review in agent_reviews:
        parts.append(f"**{review.agent_name}**: {review.summary}")
    return "\n\n".join(parts)


def build_workflow() -> StateGraph:
    graph = StateGraph(WorkflowState)

    graph.add_node("security_review", security_review_node)
    graph.add_node("aggregate", aggregation_node)

    graph.add_edge(START, "security_review")
    graph.add_edge("security_review", "aggregate")
    graph.add_edge("aggregate", END)

    return graph
