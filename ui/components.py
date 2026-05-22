"""Reusable Streamlit UI components for the Multi-Agent PR Reviewer.

Each function renders one self-contained section of the dashboard. Keeping
them here keeps ``streamlit_app.py`` a short, readable orchestration layer.
"""

from collections import Counter

import streamlit as st

from ui.styles import (
    ACCENT,
    MUTED_COLOR,
    OK_COLOR,
    SEVERITY_COLORS,
    SEVERITY_EMOJI,
    SEVERITY_ORDER,
    WARN_COLOR,
)

# Per-agent tab specs: (agent_name as returned by the backend, display label).
AGENT_TABS = [
    ("security", "Security"),
    ("architecture", "Architecture"),
    ("quality", "Quality"),
]

_EXT_LANG = {
    "py": "python", "js": "javascript", "jsx": "jsx", "ts": "typescript",
    "tsx": "tsx", "java": "java", "go": "go", "rb": "ruby", "rs": "rust",
    "cpp": "cpp", "cc": "cpp", "c": "c", "h": "c", "cs": "csharp",
    "php": "php", "sh": "bash", "bash": "bash", "yml": "yaml", "yaml": "yaml",
    "json": "json", "sql": "sql", "html": "html", "css": "css",
    "md": "markdown", "kt": "kotlin", "swift": "swift", "scala": "scala",
}


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def _language_for(file_path: str | None) -> str:
    """Best-effort source language for syntax-highlighting a code snippet."""
    if not file_path or "." not in file_path:
        return "text"
    return _EXT_LANG.get(file_path.rsplit(".", 1)[-1].lower(), "text")


def severity_badge_html(severity: str) -> str:
    """Return a compact, color-coded severity badge as HTML."""
    sev = (severity or "info").lower()
    color = SEVERITY_COLORS.get(sev, SEVERITY_COLORS["info"])
    return (
        f"<span class='sev-badge' style='background:{color}1f;color:{color};"
        f"border:1px solid {color}3d;'>{sev}</span>"
    )


def category_badge_html(category: str) -> str:
    """Return a neutral, uppercase category badge as HTML."""
    cat = (category or "general").lower()
    return f"<span class='cat-badge'>{cat}</span>"


def _sort_by_severity(findings: list[dict]) -> list[dict]:
    rank = {sev: i for i, sev in enumerate(SEVERITY_ORDER)}
    return sorted(
        findings, key=lambda f: rank.get((f.get("severity") or "info").lower(), 99)
    )


def _metric_card(
    label: str,
    value: str,
    sub: str = "",
    value_color: str | None = None,
    bar: float | None = None,
) -> str:
    """Build one compact metric card. ``bar`` is a 0-100 progress fill."""
    vc = f"color:{value_color};" if value_color else ""
    bar_html = ""
    if bar is not None:
        pct = max(0.0, min(100.0, bar))
        bar_html = (
            f"<div class='mc-bar'><span style='width:{pct:.0f}%;"
            f"background:{value_color or ACCENT};'></span></div>"
        )
    sub_html = f"<div class='mc-sub'>{sub}</div>" if sub else ""
    return (
        f"<div class='metric-card'>"
        f"<div class='mc-label'>{label}</div>"
        f"<div class='mc-value' style='{vc}'>{value}</div>"
        f"{sub_html}{bar_html}</div>"
    )


# --------------------------------------------------------------------------
# Page chrome
# --------------------------------------------------------------------------
def render_navbar(provider: str, model: str, online: bool) -> None:
    """Render the top navbar: project title, provider/model, workflow status."""
    status_cls = "up" if online else "down"
    status_txt = "Backend Online" if online else "Backend Offline"
    st.markdown(
        f"<div class='navbar'>"
        f"<div class='nav-left'>"
        f"<div class='nav-mark'>◆</div>"
        f"<div><div class='nav-title'>Multi-Agent PR Reviewer</div>"
        f"<div class='nav-sub'>AI code-review workflow · 3 agents</div></div>"
        f"</div>"
        f"<div class='nav-right'>"
        f"<span class='nav-chip'><span class='k'>Provider</span>"
        f"<span class='v'>{provider}</span></span>"
        f"<span class='nav-chip'><span class='k'>Model</span>"
        f"<span class='v'>{model}</span></span>"
        f"<span class='nav-status {status_cls}'>"
        f"<span class='dot' style='background:currentColor;'></span>{status_txt}"
        f"</span></div></div>",
        unsafe_allow_html=True,
    )


def render_sidebar(provider: str, model: str) -> None:
    """Render the sidebar: architecture, workflow steps, providers, stack."""
    steps = [
        "Fetch PR diff via the GitHub API",
        "Security agent — vulnerabilities &amp; secrets",
        "Architecture agent — design &amp; coupling",
        "Quality agent — readability &amp; naming",
        "Aggregate &amp; de-duplicate findings",
        "Human approval gate",
        "Post the review back to the PR",
    ]
    step_html = "".join(
        f"<div class='step'><span class='step-n'>{i}</span><span>{s}</span></div>"
        for i, s in enumerate(steps, 1)
    )

    arch = [
        ("FastAPI", "orchestration API"),
        ("LangGraph", "stateful agent graph"),
        ("3 agents", "run in parallel"),
        ("Aggregator", "semantic de-duplication"),
        ("Approval gate", "human-in-the-loop"),
    ]
    arch_html = "".join(
        f"<div class='side-row'><span class='sr-k'>{k}</span>"
        f"<span class='sr-v'>{v}</span></div>"
        for k, v in arch
    )

    stack = [
        "Python 3.12", "FastAPI", "LangGraph", "Pydantic",
        "Streamlit", "structlog", "PyGithub",
    ]
    stack_html = "".join(f"<span class='tag'>{t}</span>" for t in stack)

    providers_html = (
        f"<div class='side-row'>"
        f"<span class='dot' style='background:var(--ok);'></span>"
        f"<span class='sr-k'>NVIDIA NIM</span>"
        f"<span class='sr-v'>active · {model}</span></div>"
        f"<div class='side-row'>"
        f"<span class='dot' style='background:var(--text-dim);'></span>"
        f"<span class='sr-k'>OpenRouter</span>"
        f"<span class='sr-v'>OpenAI-compatible drop-in</span></div>"
    )

    with st.sidebar:
        st.markdown(
            f"<div class='side-brand'>"
            f"<div class='nav-mark'>◆</div>"
            f"<div class='sb-name'>PR Reviewer</div></div>"
            f"<div class='side-desc'>An AI engineering workflow that reviews "
            f"GitHub pull requests with three specialized agents, then merges "
            f"their output into one de-duplicated report.</div>"
            f"<div class='side-h'>Architecture</div>{arch_html}"
            f"<div class='side-h'>Workflow</div>{step_html}"
            f"<div class='side-h'>Supported Providers</div>{providers_html}"
            f"<div class='side-h'>Tech Stack</div><div>{stack_html}</div>"
            f"<div class='side-foot'>Provider: {provider} · portfolio project</div>",
            unsafe_allow_html=True,
        )


def render_footer() -> None:
    """Render the minimal page footer."""
    st.markdown(
        "<div class='app-footer'>Multi-Agent PR Reviewer · "
        "FastAPI · LangGraph · Streamlit</div>",
        unsafe_allow_html=True,
    )


def render_empty_state() -> None:
    """Render the compact placeholder shown before the first analysis."""
    st.markdown(
        "<div class='empty'>"
        "<h3>Ready to review</h3>"
        "<p>Paste a public GitHub pull request URL above. Three specialized "
        "agents analyze the diff in parallel, then their findings are "
        "aggregated and de-duplicated into a single structured report.</p>"
        "<div class='agent-row'>"
        "<div class='agent-card'><div class='ac-name'>Security</div>"
        "<div class='ac-desc'>Vulnerabilities, leaked secrets, unsafe patterns.</div></div>"
        "<div class='agent-card'><div class='ac-name'>Architecture</div>"
        "<div class='ac-desc'>Coupling, modularity, scalability concerns.</div></div>"
        "<div class='agent-card'><div class='ac-name'>Quality</div>"
        "<div class='ac-desc'>Readability, naming, maintainability.</div></div>"
        "</div></div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Results -- metrics, findings, tabs
# --------------------------------------------------------------------------
def render_pr_header(review: dict) -> None:
    """Render the PR identity line with a link out to GitHub."""
    title = review.get("pr_title") or "Pull Request"
    number = review.get("pr_number")
    url = review.get("pr_url")

    col_title, col_link = st.columns([5, 1], vertical_alignment="center")
    with col_title:
        num = f"#{number}" if number else ""
        st.markdown(
            f"<div class='pr-head'><span class='pr-num'>{num}</span>"
            f"<span class='pr-title'>{title}</span></div>",
            unsafe_allow_html=True,
        )
    with col_link:
        if url:
            st.link_button("View on GitHub", url, use_container_width=True)


def render_metrics(
    review: dict, execution_time: float | None, findings: list[dict]
) -> None:
    """Render the compact four-card metrics row."""
    severity = (review.get("overall_severity") or "info").lower()
    confidence = review.get("overall_confidence") or 0.0
    counts = Counter((f.get("severity") or "info").lower() for f in findings)

    parts = [f"{counts[s]} {s}" for s in SEVERITY_ORDER if counts.get(s)]
    findings_sub = " · ".join(parts) if parts else "clean diff"
    sev_color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS["info"])
    exec_text = f"{execution_time:.1f}s" if execution_time else "—"

    cards = [
        _metric_card("Total Findings", str(len(findings)), findings_sub),
        _metric_card("Overall Severity", severity.upper(), "highest detected", sev_color),
        _metric_card(
            "Confidence", f"{confidence * 100:.0f}%", "aggregate agent score",
            bar=confidence * 100,
        ),
        _metric_card("Execution Time", exec_text, "end-to-end wall clock"),
    ]
    st.markdown(
        f"<div class='mgrid mgrid-4'>{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )


def render_approval_strip(review: dict) -> None:
    """Render the workflow approval status as a compact strip."""
    if review.get("approved"):
        color, label, note = (
            OK_COLOR, "Approved", "Meets the auto-approval threshold.",
        )
    elif review.get("requires_approval"):
        color, label, note = (
            WARN_COLOR, "Needs human review",
            "Findings require a maintainer's sign-off before posting.",
        )
    else:
        color, label, note = (
            MUTED_COLOR, "Pending", "Review has not been finalized.",
        )
    st.markdown(
        f"<div class='status-strip' style='border-color:{color}40;'>"
        f"<span class='dot' style='background:{color};'></span>"
        f"<span class='ss-label' style='color:{color};'>{label}</span>"
        f"<span class='ss-note'>{note}</span></div>",
        unsafe_allow_html=True,
    )


def _severity_breakdown_html(counts: Counter) -> str:
    """Build the row of severity-count chips shown above the findings list."""
    total = sum(counts.values())
    chips = [f"<span class='sev-chip'><b>{total}</b>&nbsp;total</span>"]
    for sev in SEVERITY_ORDER:
        n = counts.get(sev, 0)
        if not n:
            continue
        color = SEVERITY_COLORS[sev]
        chips.append(
            f"<span class='sev-chip'>"
            f"<span class='dot' style='background:{color};'></span>"
            f"<b style='color:{color};'>{n}</b>&nbsp;{sev}</span>"
        )
    return f"<div class='sev-chips'>{''.join(chips)}</div>"


def render_finding(finding: dict, expanded: bool = False) -> None:
    """Render a single finding as an expandable accordion."""
    severity = (finding.get("severity") or "info").lower()
    title = finding.get("title") or "Untitled finding"
    file_path = finding.get("file_path")
    line = finding.get("line_number")
    emoji = SEVERITY_EMOJI.get(severity, "⚪")

    with st.expander(f"{emoji}  {title}", expanded=expanded):
        loc_html = ""
        if file_path:
            loc = file_path + (f":{line}" if line else "")
            loc_html = f"<span class='finding-loc'>{loc}</span>"
        st.markdown(
            f"<div class='finding-top'>"
            f"<div>{severity_badge_html(severity)}"
            f"{category_badge_html(finding.get('category'))}</div>"
            f"{loc_html}</div>",
            unsafe_allow_html=True,
        )

        st.markdown(finding.get("description") or "_No description provided._")

        if finding.get("suggested_fix"):
            st.markdown(
                "<div class='kv-label'>Suggested fix</div>",
                unsafe_allow_html=True,
            )
            with st.container(border=True):
                st.markdown(finding["suggested_fix"])

        if finding.get("code_snippet"):
            st.markdown("<div class='kv-label'>Code</div>", unsafe_allow_html=True)
            st.code(finding["code_snippet"], language=_language_for(file_path))


def render_findings(
    findings: list[dict], key: str, expand_first: bool = False
) -> None:
    """Render the findings centerpiece: breakdown chips, filter, accordions."""
    if not findings:
        st.markdown(
            "<div class='status-strip' style='border-color:#3fb95040;'>"
            "<span class='dot' style='background:var(--ok);'></span>"
            "<span class='ss-label' style='color:var(--ok);'>No issues found</span>"
            "<span class='ss-note'>The agents reported a clean diff.</span></div>",
            unsafe_allow_html=True,
        )
        return

    counts = Counter((f.get("severity") or "info").lower() for f in findings)
    st.markdown(_severity_breakdown_html(counts), unsafe_allow_html=True)

    present = [s for s in SEVERITY_ORDER if counts.get(s)]
    selected = st.pills(
        "Filter by severity",
        options=present,
        default=present,
        selection_mode="multi",
        format_func=str.capitalize,
        label_visibility="collapsed",
        key=f"filter_{key}",
    )
    # An empty selection means "no filter applied" -> show everything.
    active = selected or present

    visible = [
        f for f in _sort_by_severity(findings)
        if (f.get("severity") or "info").lower() in active
    ]
    if not visible:
        st.caption("No findings match the selected severities.")
        return

    for i, finding in enumerate(visible):
        render_finding(finding, expanded=expand_first and i == 0)


def render_overview(review: dict, findings: list[dict]) -> None:
    """Render the Overview tab: approval status, summary, aggregated findings."""
    render_approval_strip(review)

    st.markdown(
        "<div class='section-title'>Aggregated Summary</div>",
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        st.markdown(review.get("summary") or "_No summary provided._")

    st.markdown("<div class='section-title'>Findings</div>", unsafe_allow_html=True)
    render_findings(findings, key="overview", expand_first=True)


def render_agent_tab(
    name: str, agent_reviews: list[dict], failed_agents: list[str]
) -> None:
    """Render one per-agent tab: mini metrics, summary and that agent's findings."""
    review = {a.get("agent_name"): a for a in agent_reviews}.get(name)
    if review is None:
        if name in failed_agents:
            st.error(f"The {name} agent failed to complete.")
        else:
            st.info(f"No output available from the {name} agent.")
        return

    findings = review.get("findings") or []
    confidence = review.get("confidence") or 0.0
    exec_time = review.get("agent_execution_time")
    cards = [
        _metric_card("Findings", str(len(findings)), "reported by this agent"),
        _metric_card(
            "Confidence", f"{confidence * 100:.0f}%", "agent self-assessment",
            bar=confidence * 100,
        ),
        _metric_card(
            "Execution Time",
            f"{exec_time:.1f}s" if exec_time else "—",
            "agent runtime",
        ),
    ]
    st.markdown(
        f"<div class='mgrid mgrid-3'>{''.join(cards)}</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        "<div class='section-title'>Agent Summary</div>", unsafe_allow_html=True
    )
    with st.container(border=True):
        st.markdown(review.get("summary") or "_No summary provided._")

    st.markdown("<div class='section-title'>Findings</div>", unsafe_allow_html=True)
    render_findings(findings, key=f"agent_{name}")


def render_results(payload: dict) -> None:
    """Render the full results dashboard from a backend review payload."""
    review = payload.get("review") or {}
    execution_time = payload.get("execution_time_seconds")
    failed_agents = payload.get("failed_agents") or []
    findings = review.get("findings") or []
    agent_reviews = review.get("agent_reviews") or []

    render_pr_header(review)
    render_metrics(review, execution_time, findings)

    if failed_agents:
        st.warning("Some agents did not complete: " + ", ".join(failed_agents))
    for warning in review.get("warnings") or []:
        st.warning(warning)

    tabs = st.tabs(["Overview", "Security", "Architecture", "Quality", "Raw JSON"])

    with tabs[0]:
        render_overview(review, findings)
    for tab, (name, _label) in zip(tabs[1:4], AGENT_TABS):
        with tab:
            render_agent_tab(name, agent_reviews, failed_agents)
    with tabs[4]:
        st.markdown(
            "<div class='section-title'>Raw API Response</div>",
            unsafe_allow_html=True,
        )
        st.json(payload)
