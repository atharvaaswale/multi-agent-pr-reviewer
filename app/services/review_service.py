import structlog

from app.schemas.review import AggregatedReview, FindingCategory, Severity

logger = structlog.get_logger(__name__)

SEVERITY_EMOJI = {
    Severity.critical: "🔴",
    Severity.high: "🟠",
    Severity.medium: "🟡",
    Severity.low: "🔵",
    Severity.info: "⚪",
}


def format_review_body(review: AggregatedReview) -> str:
    lines = [
        "## AI Review Summary",
        "",
        f"**Overall Severity**: {SEVERITY_EMOJI.get(review.overall_severity, '')} {review.overall_severity.value}",
        f"**Confidence**: {review.overall_confidence:.0%}",
        "",
        review.summary,
    ]

    if review.warnings:
        lines.append("")
        lines.append("### Warnings")
        for w in review.warnings:
            lines.append(f"- {w}")

    grouped = _group_findings_by_category(review.findings)

    if grouped:
        lines.append("")
        lines.append("### Findings")
        for category, findings in grouped.items():
            lines.append("")
            lines.append(f"**{category.value}** ({len(findings)})")
            for f in findings:
                emoji = SEVERITY_EMOJI.get(f.severity, "")
                location = f" in `{f.file_path}`" if f.file_path else ""
                lines.append(f"- {emoji} **{f.title}**{location}")
                if f.suggested_fix:
                    lines.append(f"  - Fix: {f.suggested_fix}")

    lines.append("")
    lines.append("---")
    lines.append("*Posted by Multi-Agent PR Reviewer*")

    return "\n".join(lines)


def _group_findings_by_category(findings: list) -> dict[FindingCategory, list]:
    grouped: dict[FindingCategory, list] = {}
    for f in findings:
        grouped.setdefault(f.category, []).append(f)
    return grouped
