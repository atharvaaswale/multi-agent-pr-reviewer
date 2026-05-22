import pytest

from app.graph.state import ApprovalStatus, WorkflowState, WorkflowStatus
from app.graph.workflow import (
    _build_summary,
    _requires_human_approval,
    aggregation_node,
    build_workflow,
    human_approval_node,
    post_review_node,
)
from app.schemas.review import AgentReview, AggregatedReview, Finding, FindingCategory, Severity


def _make_state(**kwargs) -> WorkflowState:
    defaults = {
        "pr_url": "https://github.com/owner/repo/pull/42",
        "repo_owner": "owner",
        "repo_name": "repo",
        "pr_number": 42,
    }
    return WorkflowState(**{**defaults, **kwargs})


def _make_review(agent_name: str, findings: list[Finding] | None = None, confidence: float = 0.8) -> AgentReview:
    return AgentReview(
        agent_name=agent_name,
        summary=f"{agent_name} summary",
        confidence=confidence,
        findings=findings or [],
    )


def _make_finding(
    severity: Severity = Severity.medium,
    title: str = "Test finding",
    file_path: str = "test.py",
    line_number: int = 10,
    category: FindingCategory = FindingCategory.security,
) -> Finding:
    return Finding(
        title=title,
        description="A test finding",
        severity=severity,
        category=category,
        file_path=file_path,
        line_number=line_number,
    )


class TestRequiresHumanApproval:
    def test_failed_agents_triggers_approval(self):
        assert _requires_human_approval([], ["security"]) is True

    def test_critical_finding_triggers_approval(self):
        findings = [_make_finding(Severity.critical)]
        assert _requires_human_approval(findings, []) is True

    def test_high_finding_triggers_approval(self):
        findings = [_make_finding(Severity.high)]
        assert _requires_human_approval(findings, []) is True

    def test_medium_finding_does_not_trigger(self):
        findings = [_make_finding(Severity.medium)]
        assert _requires_human_approval(findings, []) is False

    def test_low_finding_does_not_trigger(self):
        findings = [_make_finding(Severity.low)]
        assert _requires_human_approval(findings, []) is False

    def test_empty_findings_no_approval(self):
        assert _requires_human_approval([], []) is False

    def test_mixed_severity_triggers_on_high(self):
        findings = [
            _make_finding(Severity.info),
            _make_finding(Severity.high),
            _make_finding(Severity.low),
        ]
        assert _requires_human_approval(findings, []) is True


class TestBuildSummary:
    def test_single_review(self):
        reviews = [_make_review("security")]
        result = _build_summary(reviews)
        assert "**security**: security summary" in result

    def test_multiple_reviews(self):
        reviews = [_make_review("security"), _make_review("quality")]
        result = _build_summary(reviews)
        assert "**security**: security summary" in result
        assert "**quality**: quality summary" in result

    def test_empty_reviews(self):
        assert _build_summary([]) == ""


class TestAggregationNode:
    def test_all_agents_complete(self):
        state = _make_state(
            security_review=_make_review(
                "security",
                [_make_finding(Severity.high, title="SQL injection", category=FindingCategory.security)],
            ),
            architecture_review=_make_review(
                "architecture",
                [_make_finding(Severity.medium, title="Tight coupling", category=FindingCategory.architecture)],
            ),
            quality_review=_make_review("quality"),
        )

        result = aggregation_node(state)

        assert result["aggregated_review"] is not None
        review = result["aggregated_review"]
        assert len(review.findings) == 2
        assert len(review.agent_reviews) == 3
        assert review.overall_severity == Severity.high
        assert review.overall_confidence == 0.8
        assert result["workflow_status"] == WorkflowStatus.completed

    def test_no_agents_complete(self):
        state = _make_state()

        result = aggregation_node(state)

        review = result["aggregated_review"]
        assert review.summary == "No agent reviews completed."
        assert review.overall_confidence == 0.0
        assert review.overall_severity == Severity.info
        assert len(review.findings) == 0

    def test_failed_agents_included_in_warnings(self):
        state = _make_state(
            security_review=_make_review("security"),
            architecture_error="architecture agent failed",
            quality_error="quality agent failed",
        )

        result = aggregation_node(state)

        review = result["aggregated_review"]
        assert len(review.warnings) == 1
        assert "architecture" in review.warnings[0]
        assert "quality" in review.warnings[0]
        assert review.requires_approval is True

    def test_requires_approval_set_on_critical(self):
        state = _make_state(
            security_review=_make_review("security", [_make_finding(Severity.critical)]),
        )

        result = aggregation_node(state)

        assert result["aggregated_review"].requires_approval is True

    def test_requires_approval_false_for_low_risk(self):
        state = _make_state(
            quality_review=_make_review("quality", [_make_finding(Severity.low)]),
        )

        result = aggregation_node(state)

        assert result["aggregated_review"].requires_approval is False

    def test_aggregation_sets_execution_time(self):
        state = _make_state(security_review=_make_review("security"))

        result = aggregation_node(state)

        assert result["execution_time_seconds"] is not None
        assert result["completed_at"] is not None

    def test_aggregation_deduplicates_overlapping_findings(self):
        # Two agents report the same issue (same file/line/title) at
        # different severities; aggregation should keep one, highest severity.
        state = _make_state(
            security_review=_make_review(
                "security", [_make_finding(Severity.low, title="Hardcoded secret")]
            ),
            architecture_review=_make_review(
                "architecture", [_make_finding(Severity.critical, title="Hardcoded secret")]
            ),
        )

        result = aggregation_node(state)

        review = result["aggregated_review"]
        assert len(review.findings) == 1
        assert review.findings[0].severity == Severity.critical
        assert review.overall_severity == Severity.critical


class TestHumanApprovalNode:
    def test_auto_approve_low_risk(self):
        review = AggregatedReview(
            pr_url="https://github.com/owner/repo/pull/1",
            pr_title="Test PR",
            pr_number=1,
            summary="All good",
            overall_confidence=0.9,
            overall_severity=Severity.low,
            requires_approval=False,
        )
        state = _make_state(aggregated_review=review)

        result = human_approval_node(state)

        assert result["approval_status"] == ApprovalStatus.approved
        assert result["aggregated_review"].approved is True

    def test_reject_requires_approval(self):
        review = AggregatedReview(
            pr_url="https://github.com/owner/repo/pull/1",
            pr_title="Test PR",
            pr_number=1,
            summary="Issues found",
            overall_confidence=0.7,
            overall_severity=Severity.critical,
            requires_approval=True,
        )
        state = _make_state(aggregated_review=review)

        result = human_approval_node(state)

        assert result["approval_status"] == ApprovalStatus.rejected

    def test_reject_no_review(self):
        state = _make_state(aggregated_review=None)

        result = human_approval_node(state)

        assert result["approval_status"] == ApprovalStatus.rejected
        assert result["workflow_status"] == WorkflowStatus.completed


class TestPostReviewNode:
    def test_skip_when_rejected(self, monkeypatch):
        review = AggregatedReview(
            pr_url="https://github.com/owner/repo/pull/1",
            pr_title="Test PR",
            pr_number=1,
            summary="Issues found",
            overall_confidence=0.7,
            overall_severity=Severity.critical,
            requires_approval=True,
        )
        state = _make_state(
            aggregated_review=review,
            approval_status=ApprovalStatus.rejected,
        )

        result = post_review_node(state)

        assert result == {}

    def test_skip_when_pending(self, monkeypatch):
        review = AggregatedReview(
            pr_url="https://github.com/owner/repo/pull/1",
            pr_title="Test PR",
            pr_number=1,
            summary="All good",
            overall_confidence=0.9,
            overall_severity=Severity.low,
            requires_approval=False,
        )
        state = _make_state(
            aggregated_review=review,
            approval_status=ApprovalStatus.pending,
        )

        result = post_review_node(state)

        assert result == {}

    def test_skip_when_no_review(self):
        state = _make_state(approval_status=ApprovalStatus.approved, aggregated_review=None)

        result = post_review_node(state)

        assert result == {}

    def test_posts_when_approved(self, monkeypatch):
        posted = {}

        class FakeClient:
            def __init__(self, token=None):
                pass

            def post_pr_review(self, owner, repo, number, body):
                posted["owner"] = owner
                posted["repo"] = repo
                posted["number"] = number
                posted["body"] = body

        monkeypatch.setattr("app.graph.workflow.GitHubClient", FakeClient)

        review = AggregatedReview(
            pr_url="https://github.com/owner/repo/pull/1",
            pr_title="Test PR",
            pr_number=1,
            summary="All good",
            overall_confidence=0.9,
            overall_severity=Severity.low,
            requires_approval=False,
        )
        state = _make_state(
            aggregated_review=review,
            approval_status=ApprovalStatus.approved,
        )

        result = post_review_node(state)

        assert result["workflow_status"] == WorkflowStatus.completed
        assert posted["owner"] == "owner"
        assert posted["repo"] == "repo"
        assert posted["number"] == 42
        assert "AI Review Summary" in posted["body"]

    def test_error_appends_warning(self, monkeypatch):
        class FakeClient:
            def __init__(self, token=None):
                pass

            def post_pr_review(self, owner, repo, number, body):
                raise Exception("GitHub API error")

        monkeypatch.setattr("app.graph.workflow.GitHubClient", FakeClient)

        review = AggregatedReview(
            pr_url="https://github.com/owner/repo/pull/1",
            pr_title="Test PR",
            pr_number=1,
            summary="All good",
            overall_confidence=0.9,
            overall_severity=Severity.low,
            requires_approval=False,
            warnings=["Existing warning"],
        )
        state = _make_state(
            aggregated_review=review,
            approval_status=ApprovalStatus.approved,
        )

        result = post_review_node(state)

        assert result["workflow_status"] == WorkflowStatus.completed
        assert len(result["aggregated_review"].warnings) == 2
        assert "GitHub API error" in result["aggregated_review"].warnings[1]


class TestBuildWorkflow:
    def test_graph_has_all_nodes(self):
        graph = build_workflow()
        nodes = list(graph.nodes.keys())
        assert "security_review" in nodes
        assert "architecture_review" in nodes
        assert "quality_review" in nodes
        assert "aggregate" in nodes
        assert "human_approval" in nodes
        assert "post_review" in nodes

    def test_graph_starts_with_parallel_agents(self):
        graph = build_workflow()
        start_edges = [e[1] for e in graph.edges if e[0] == "__start__"]
        assert "security_review" in start_edges
        assert "architecture_review" in start_edges
        assert "quality_review" in start_edges

    def test_graph_ends_after_post_review(self):
        graph = build_workflow()
        end_edges = [e[0] for e in graph.edges if e[1] == "__end__"]
        assert "post_review" in end_edges
