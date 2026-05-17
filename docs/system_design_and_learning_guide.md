# Multi-Agent PR Reviewer — System Design & Learning Guide

> A senior engineer walkthrough of how this agentic AI system works internally.
> Read this alongside the source code. Every section references specific files.

---

## Table of Contents

1. [High-Level Purpose](#1-high-level-purpose)
2. [What Problem This System Solves](#2-what-problem-this-system-solves)
3. [What a GitHub Pull Request Is](#3-what-a-github-pull-request-is)
4. [How PR Review Works in Real Companies](#4-how-pr-review-works-in-real-companies)
5. [Why Multi-Agent Architecture](#5-why-multi-agent-architecture)
6. [Why LangGraph](#6-why-langgraph)
7. [Full Request Lifecycle Walkthrough](#7-full-request-lifecycle-walkthrough)
8. [Step-by-Step Execution Trace](#8-step-by-step-execution-trace)
9. [How Workflow State Changes Over Time](#9-how-workflow-state-changes-over-time)
10. [How Context Moves Between Components](#10-how-context-moves-between-components)
11. [Responsibility of Each Folder](#11-responsibility-of-each-folder)
12. [Responsibility of Each Major File](#12-responsibility-of-each-major-file)
13. [Responsibility of Each Major Class/Function](#13-responsibility-of-each-major-classfunction)
14. [How the Security Agent Works Internally](#14-how-the-security-agent-works-internally)
15. [How OpenRouter Interaction Works](#15-how-openrouter-interaction-works)
16. [How GitHub Data Retrieval Works](#16-how-github-data-retrieval-works)
17. [How Structured Outputs Are Validated](#17-how-structured-outputs-are-validated)
18. [Failure Handling and Retries](#18-failure-handling-and-retries)
19. [Why Pydantic Is Important Here](#19-why-pydantic-is-important-here)
20. [Current MVP Limitations](#20-current-mvp-limitations)
21. [Future Roadmap](#21-future-roadmap)
22. [Glossary of Agentic AI Concepts](#22-glossary-of-important-agentic-ai-concepts)

---

## 1. High-Level Purpose

This project is an **API service** that receives a GitHub Pull Request URL, fetches the PR data, runs it through an AI-powered review workflow (currently one agent: security), and returns a structured review as JSON.

It is built with:
- **FastAPI** — HTTP API framework
- **LangGraph** — graph-based workflow orchestration for agents
- **Pydantic** — data validation and schema definitions
- **PyGithub** — GitHub REST API client
- **httpx** — async HTTP client for calling LLMs
- **OpenRouter** — LLM API gateway (currently using DeepSeek or Claude models)
- **tenacity** — retry logic
- **structlog** — structured JSON logging

```
┌─────────────────────────────────────────────────────────┐
│                    Multi-Agent PR Reviewer               │
│                                                         │
│  Input:  GitHub PR URL                                  │
│  Output: Structured AI review (JSON)                    │
│                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────┐   │
│  │ GitHub   │───▶│ LangGraph│───▶│ Aggregated       │   │
│  │ Client   │    │ Workflow │    │ Review Response  │   │
│  └──────────┘    └──────────┘    └──────────────────┘   │
│                      │                                  │
│                      ▼                                  │
│                ┌──────────┐                             │
│                │ Security │ (more agents planned)       │
│                │ Agent    │                             │
│                └──────────┘                             │
└─────────────────────────────────────────────────────────┘
```

---

## 2. What Problem This System Solves

In real software teams, code review is:

1. **Slow** — humans are busy, PRs sit waiting
2. **Inconsistent** — different reviewers catch different things
3. **Exhausting** — reviewing large diffs is mentally taxing
4. **Easy to miss** — security issues, architectural problems, and quality regressions slip through

This system automates the **first pass** of code review. An AI agent reads the PR diffs and checks for problems before a human ever looks at it. The multi-agent design means different "specialists" can focus on different aspects: security, architecture, code quality, etc.

**It does NOT replace human reviewers.** It augments them by surfacing issues early.

---

## 3. What a GitHub Pull Request Is

A Pull Request (PR) is GitHub's mechanism for proposing changes to a repository.

```
Developer's Fork/Branch                    Main Repository
┌──────────────────────┐                  ┌──────────────────────┐
│                      │                  │                      │
│  main branch         │                  │  main branch         │
│  ┌──────────────┐    │                  │  ┌──────────────┐    │
│  │ original code │    │                  │  │ original code │    │
│  └──────────────┘    │                  │  └──────────────┘    │
│                      │                  │                      │
│  feature branch      │     ┌───────┐    │                      │
│  ┌──────────────┐    │────▶│  PR   │───▶│  (review → merge)   │
│  │ changed code  │    │     └───────┘    │                      │
│  └──────────────┘    │                  │                      │
│                      │                  │                      │
└──────────────────────┘                  └──────────────────────┘
```

A PR contains:
- **Title** — short description of the change
- **Body/description** — longer explanation
- **Diffs** — line-by-line changes (additions, deletions) per file
- **Changed files list** — which files were modified
- **Metadata** — author, base branch, head branch, commit SHA, status

A PR URL looks like: `https://github.com/owner/repo/pull/42`

---

## 4. How PR Review Works in Real Companies

```
┌─────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐     ┌────────┐
│Developer│────▶│   PR     │────▶  CI/CD   │────▶  Review  │────▶│ Merge  │
│pushes   │     │ created  │     │  runs    │     │  humans  │     │ to main│
│code     │     │          │     │  tests   │     │  approve │     │        │
└─────────┘     └──────────┘     └──────────┘     └──────────┘     └────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │  AI Review (this │
                              │  system) runs    │
                              │  BEFORE humans   │
                              └──────────────────┘
```

Typical flow:

1. Developer pushes code and opens a PR
2. CI runs tests, linters, build checks
3. **AI review runs** (our system) — catches issues automatically
4. Human reviewers look at the PR + AI feedback
5. Developer addresses feedback
6. PR is merged

The AI review step is what this project provides. It runs in parallel with or before human review.

---

## 5. Why Multi-Agent Architecture

Instead of one giant prompt that says "review this PR for everything," the system uses **specialized agents**:

```
┌─────────────────────────────────────────────┐
│              Aggregation Node                │
│  (combines all agent results)                │
│                                              │
│  ▲              ▲              ▲             │
│  │              │              │             │
│  │              │              │             │
┌─┴──────┐  ┌────┴─────┐  ┌────┴──────┐       │
│Security│  │Architecture│  │ Quality   │       │
│ Agent  │  │   Agent    │  │  Agent    │       │
└────────┘  └────────────┘  └───────────┘       │
```

**Why not one prompt?**

| One Big Prompt | Multi-Agent |
|---|---|
| LLM context gets diluted | Each agent has focused context |
| Hard to debug which part failed | Each agent is independently traceable |
| One system prompt for everything | Each agent has its own system prompt |
| Cannot retry just one aspect | Failed agents don't block others |
| Hard to add new review types | Just add a new agent node |

**Current state:** Only the security agent is implemented. The `WorkflowState` already has slots for `architecture_review` and `quality_review`, and the aggregation node already handles combining multiple agent reviews. The architecture is designed for multi-agent, but the MVP has one.

---

## 6. Why LangGraph

LangGraph is a library for building **stateful, multi-step AI workflows** as directed graphs.

**What it gives us:**

1. **Explicit state** — `WorkflowState` is a Pydantic model passed through every node
2. **Directed graph** — nodes are connected by edges, execution order is clear
3. **Async support** — nodes can be `async` (important for LLM calls)
4. **Conditional routing** — can branch based on state (not used yet, but available)
5. **Checkpointing** — can save/restore state (not used yet, but available)
6. **Streaming** — can stream partial results (not used yet)

**The alternative without LangGraph:**

```python
# Without LangGraph — manual orchestration
state = WorkflowState(...)
state.security_review = await run_security_review(...)
state.aggregated_review = aggregate(state)
# You manually track state, errors, retries, timing, etc.
```

**With LangGraph:**

```python
# With LangGraph — declarative graph
graph = StateGraph(WorkflowState)
graph.add_node("security_review", security_review_node)
graph.add_node("aggregate", aggregation_node)
graph.add_edge(START, "security_review")
graph.add_edge("security_review", "aggregate")
graph.add_edge("aggregate", END)

final_state = await graph.compile().ainvoke(state.model_dump())
# LangGraph handles: state passing, error propagation, execution order
```

The graph approach makes it trivial to add new agents — just add a node and an edge.

---

## 7. Full Request Lifecycle Walkthrough

Here is the complete journey of a single API request:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        COMPLETE REQUEST LIFECYCLE                        │
│                                                                          │
│  1. HTTP Request arrives                                                │
│     POST /api/v1/review                                                 │
│     Body: {"pr_url": "https://github.com/owner/repo/pull/42"}           │
│                                                                          │
│  2. FastAPI routes.py receives it                                       │
│     - Validates request body with Pydantic (PRReviewRequest)            │
│     - Logs "review_request_received"                                    │
│                                                                          │
│  3. GitHubClient fetches PR data                                        │
│     - parse_pr_url() → extracts owner, repo, pr_number                  │
│     - fetch_pr_metadata() → title, body, branches, commit SHA           │
│     - fetch_changed_files() → list of ChangedFile objects               │
│     - fetch_pr_diffs() → dict of {filename: diff_text}                  │
│                                                                          │
│  4. WorkflowState is created                                            │
│     - All PR data stuffed into a Pydantic model                         │
│     - State initialized: security_review=None, workflow_status=pending  │
│                                                                          │
│  5. LangGraph workflow compiles and executes                            │
│     a. START → security_review_node                                     │
│        - Creates LLMService (OpenRouter client)                         │
│        - Calls run_security_review()                                    │
│        - LLM returns JSON findings                                      │
│        - Returns {"security_review": AgentReview}                       │
│                                                                          │
│     b. security_review → aggregate                                      │
│        - Collects all AgentReview objects from state                    │
│        - Computes overall_confidence (average)                          │
│        - Computes overall_severity (max)                                │
│        - Builds AggregatedReview                                        │
│        - Sets workflow_status=completed, execution_time_seconds         │
│        - Returns {"aggregated_review": ..., "workflow_status": ...}     │
│                                                                          │
│     c. aggregate → END                                                  │
│                                                                          │
│  6. Response is built                                                   │
│     - Extracts aggregated_review from final_state                       │
│     - Builds PRReviewResponse                                           │
│     - Logs "review_completed"                                           │
│                                                                          │
│  7. HTTP Response sent                                                  │
│     200 OK with JSON body                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 8. Step-by-Step Execution Trace

Let's trace a real request line-by-line through the code.

### Step 1: Server Startup

**File:** `app/main.py:24-26`

```python
@app.on_event("startup")
async def startup() -> None:
    structlog.get_logger(__name__).info("application_started")
```

- FastAPI starts, structlog is configured with JSON output
- Router from `app/api/routes.py` is registered at `/api/v1`

### Step 2: Request Arrives

```
POST /api/v1/review
Content-Type: application/json

{"pr_url": "https://github.com/facebook/react/pull/27890"}
```

**File:** `app/api/routes.py:40`

```python
async def review_pr(request: PRReviewRequest) -> PRReviewResponse:
```

- FastAPI parses the JSON body into `PRReviewRequest`
- Pydantic validates that `pr_url` is a non-empty string
- If validation fails → 422 Unprocessable Entity (automatic)

### Step 3: GitHub Data Fetch

**File:** `app/api/routes.py:43-47`

```python
github_client = GitHubClient()
owner, repo, pr_number = github_client.parse_pr_url(request.pr_url)
metadata, changed_files, diffs = github_client.fetch_pr_data(request.pr_url)
```

What happens inside:

1. `GitHubClient.__init__()` reads `GITHUB_TOKEN` from environment
2. `parse_pr_url()` uses regex to extract: `owner="facebook"`, `repo="react"`, `pr_number=27890`
3. `fetch_pr_data()` makes 3 GitHub API calls:
   - `GET /repos/facebook/react` — get repo object
   - `GET /repos/facebook/react/pulls/27890` — get PR metadata
   - `GET /repos/facebook/react/pulls/27890/files` — get changed files

### Step 4: State Initialization

**File:** `app/api/routes.py:55-65`

```python
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
```

State at this point:

```
WorkflowState {
    pr_url: "https://github.com/facebook/react/pull/27890"
    repo_owner: "facebook"
    repo_name: "react"
    pr_number: 27890
    pr_title: "Fix: ..."
    pr_body: "..."
    commit_sha: "abc123"
    changed_files: ["src/file1.js", "src/file2.js"]
    diffs: {"src/file1.js": "@@ -1,3 +1,5 @@\n...", ...}
    security_review: None          ← not yet populated
    architecture_review: None      ← not yet implemented
    quality_review: None           ← not yet implemented
    failed_agents: []              ← empty
    aggregated_review: None        ← not yet computed
    approval_status: pending       ← default
    workflow_status: pending       ← default
    created_at: 2026-05-16T23:00:00Z
    completed_at: None
    execution_time_seconds: None
}
```

### Step 5: Workflow Execution

**File:** `app/api/routes.py:69-72`

```python
workflow = build_workflow().compile()
final_state = await workflow.ainvoke(state.model_dump())
```

`state.model_dump()` converts the Pydantic model to a plain dict that LangGraph can mutate.

### Step 6: Security Review Node Runs

**File:** `app/graph/workflow.py:19-34`

```python
async def security_review_node(state: WorkflowState) -> dict:
    llm = _build_llm_service()
    try:
        review = await run_security_review(llm, state.pr_title, state.pr_body, state.diffs)
        return {"security_review": review}
    except Exception as exc:
        return {"failed_agents": state.failed_agents + ["security"]}
    finally:
        await llm.close()
```

LangGraph merges the returned dict into the state. So `state["security_review"]` is now set.

### Step 7: Aggregation Node Runs

**File:** `app/graph/workflow.py:37-98`

```python
def aggregation_node(state: WorkflowState) -> dict:
    # Collects security_review, computes confidence/severity
    # Returns {"aggregated_review": ..., "workflow_status": completed, ...}
```

### Step 8: Response Built and Returned

**File:** `app/api/routes.py:80-100`

```python
response = PRReviewResponse(
    review=aggregated,
    execution_time_seconds=final_state.get("execution_time_seconds"),
    failed_agents=final_state.get("failed_agents", []),
)
return response
```

---

## 9. How Workflow State Changes Over Time

The `WorkflowState` is the **single source of truth** that flows through every node. Here's how it evolves:

```
┌─────────────────────────────────────────────────────────────────┐
│                    WORKFLOW STATE LIFECYCLE                      │
│                                                                 │
│  PHASE 1: Created in routes.py                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ pr_url, repo_owner, repo_name, pr_number, pr_title,       │  │
│  │ pr_body, commit_sha, changed_files, diffs                 │  │
│  │ security_review: None                                     │  │
│  │ aggregated_review: None                                   │  │
│  │ workflow_status: pending                                  │  │
│  │ failed_agents: []                                         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  PHASE 2: After security_review_node                            │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ ... (all from Phase 1, unchanged)                         │  │
│  │ security_review: AgentReview {                            │  │
│  │   agent_name: "security",                                 │  │
│  │   summary: "...",                                         │  │
│  │   confidence: 0.85,                                       │  │
│  │   findings: [Finding, Finding, ...]                       │  │
│  │ }                                                         │  │
│  │ aggregated_review: None                                   │  │
│  │ workflow_status: pending                                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  PHASE 3: After aggregation_node (final state)                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ ... (all from Phase 2, unchanged)                         │  │
│  │ aggregated_review: AggregatedReview {                     │  │
│  │   pr_url, pr_title, pr_number, summary,                   │  │
│  │   overall_confidence: 0.85,                               │  │
│  │   overall_severity: high,                                 │  │
│  │   findings: [...],                                        │  │
│  │   agent_reviews: [AgentReview],                           │  │
│  │   warnings: [],                                           │  │
│  │   approved: False                                         │  │
│  │ }                                                         │  │
│  │ workflow_status: completed                                │  │
│  │ completed_at: 2026-05-16T23:00:15Z                        │  │
│  │ execution_time_seconds: 15.23                             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Key insight:** State is **immutable in concept, mutable in practice**. Each node returns a dict of *updates*, and LangGraph merges them into the existing state. Nodes don't replace the entire state — they only set the keys they care about.

```python
# security_review_node returns:
{"security_review": AgentReview(...)}

# LangGraph merges this into state:
state["security_review"] = AgentReview(...)
# Everything else in state is untouched
```

### State Transition Diagram

```
┌──────────┐    START     ┌──────────────────────────────────┐
│          │─────────────▶│ security_review_node             │
│  routes  │              │ Input: WorkflowState             │
│  creates │              │ Modifies: security_review        │
│  state   │              │          OR failed_agents        │
│          │              └──────────────┬───────────────────┘
└──────────┘                             │
                                         │ state updated
                                         ▼
                              ┌──────────────────────────────────┐
                              │ aggregation_node                 │
                              │ Input: WorkflowState             │
                              │ Modifies: aggregated_review      │
                              │          workflow_status         │
                              │          completed_at            │
                              │          execution_time_seconds  │
                              └──────────────┬───────────────────┘
                                             │
                                             ▼
                                      ┌──────────┐
                                      │   END    │
                                      │  Return  │
                                      │  state   │
                                      └──────────┘
```

---

## 10. How Context Moves Between Components

"Context" here means the PR data (title, body, diffs) and the review results. Here's how it flows:

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CONTEXT PROPAGATION MAP                        │
│                                                                       │
│  GitHub API                                                           │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ PRMetadata  ───────────────────────────────────────────────┐ │    │
│  │ ChangedFile[] ───────────────────────────────────────────┐ │ │    │
│  │ diffs: dict[str,str] ──────────────────────────────────┐ │ │ │    │
│  └────────────────────────────────────────────────────────┼─┼─┼────┘    │
│                                                           │ │ │         │
│                                                           ▼ ▼ ▼         │
│  WorkflowState (app/graph/state.py)                       │             │
│  ┌────────────────────────────────────────────────────────┼───────┐    │
│  │ pr_title ←─────────────────────────────────────────────┘       │    │
│  │ pr_body ←──────────────────────────────────────────────────────┘    │
│  │ diffs ←───────────────────────────────────────────────────────────┘ │
│  │ changed_files                                                       │
│  │                                                                     │
│  │  ┌─────────────────────────────────────────────────────────┐       │
│  │  │ security_review ──────────────────────────────────────┐ │       │
│  │  │   AgentReview                                         │ │       │
│  │  │     findings: [Finding]                               │ │       │
│  │  │       severity, category, file_path, line_number      │ │       │
│  │  │       code_snippet, suggested_fix                     │ │       │
│  │  └───────────────────────────────────────────────────────┼─┘       │
│  │                                                            │        │
│  │  ┌─────────────────────────────────────────────────────────┐      │
│  │  │ aggregated_review ───────────────────────────────────┐  │      │
│  │  │   AggregatedReview                                   │  │      │
│  │  │     findings: [all findings from all agents]         │  │      │
│  │  │     agent_reviews: [AgentReview, ...]                │  │      │
│  │  │     overall_confidence, overall_severity             │  │      │
│  │  └──────────────────────────────────────────────────────┘  │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                       │
│  HTTP Response                                                        │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │ PRReviewResponse                                             │    │
│  │   review: AggregatedReview ← from state.aggregated_review    │    │
│  │   execution_time_seconds ← from state.execution_time_seconds │    │
│  │   failed_agents ← from state.failed_agents                   │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
```

**Key pattern:** Context flows **one direction** — GitHub → State → Agent → State → Aggregation → Response. No component reaches back to fetch data from another component. Everything passes through state.

---

## 11. Responsibility of Each Folder

```
app/
├── main.py              # Application entry point. Creates FastAPI app, configures logging.
├── api/                 # HTTP layer. Defines routes, request/response models.
│   └── routes.py        # The only route handler. Receives PR URL, orchestrates everything.
├── agents/              # AI agent implementations. Each agent is a specialist.
│   └── security_agent.py # Security-focused code review agent.
├── graph/               # Workflow orchestration. LangGraph state and graph definition.
│   ├── state.py         # WorkflowState model — the data structure passed through the graph.
│   └── workflow.py      # Graph construction: nodes, edges, aggregation logic.
├── github/              # GitHub API integration.
│   └── client.py        # PyGithub wrapper. Fetches PR metadata, files, diffs.
├── schemas/             # Data models and validation schemas.
│   └── review.py        # Pydantic models: Finding, AgentReview, AggregatedReview.
├── services/            # External service integrations.
│   └── llm_service.py   # OpenRouter HTTP client. Handles LLM API calls.
├── utils/               # (empty) — for shared utility functions.
└── prompts/             # (empty) — for system prompts (currently inline in agents).
```

**Design principle:** Each folder has a single concern. `agents` knows nothing about HTTP. `github` knows nothing about LangGraph. `graph` knows nothing about PyGithub. Communication happens through the shared `WorkflowState` model.

---

## 12. Responsibility of Each Major File

### `app/main.py` (31 lines)

**Who calls it:** Uvicorn (the ASGI server) starts this file.

**What it does:**
1. Configures structlog with JSON output
2. Creates the FastAPI application instance
3. Registers the API router
4. Defines startup/shutdown event handlers

**Input:** None (server startup)
**Output:** FastAPI `app` object

### `app/api/routes.py` (100 lines)

**Who calls it:** FastAPI, when a request hits `/api/v1/review` or `/api/v1/health`.

**What it does:**
1. Validates the incoming request body
2. Fetches PR data from GitHub
3. Creates initial `WorkflowState`
4. Builds and executes the LangGraph workflow
5. Constructs and returns the HTTP response

**Input:** `PRReviewRequest` (JSON body with `pr_url`)
**Output:** `PRReviewResponse` (JSON with review, timing, failed agents)
**State modified:** Creates initial `WorkflowState`, receives final state from workflow

### `app/github/client.py` (111 lines)

**Who calls it:** `routes.py` (line 43-47) creates a `GitHubClient` and calls its methods.

**What it does:**
1. Parses GitHub PR URLs with regex
2. Fetches PR metadata (title, body, branches, SHA)
3. Fetches changed files list
4. Fetches file diffs (the actual code changes)

**Input:** PR URL string, or owner/repo/pr_number
**Output:** `PRMetadata`, `list[ChangedFile]`, `dict[str, str]` of diffs
**State modified:** None (pure data fetcher)

### `app/schemas/review.py` (63 lines)

**Who calls it:** Imported by `security_agent.py`, `workflow.py`, `state.py`, `routes.py`.

**What it does:** Defines the data models for the entire review system:
- `Severity` enum — critical, high, medium, low, info
- `FindingCategory` enum — security, architecture, quality, performance, maintainability
- `Finding` — a single issue found by an agent
- `AgentReview` — one agent's complete review
- `AggregatedReview` — combined review from all agents

**Input:** Raw data from LLM responses or aggregation logic
**Output:** Validated Pydantic models (raises validation errors if data is wrong)
**State modified:** None (pure data validation)

### `app/graph/state.py` (41 lines)

**Who calls it:** Imported by `routes.py`, `workflow.py`, `agents/security_agent.py` (indirectly).

**What it does:** Defines `WorkflowState` — the central data structure passed through the LangGraph workflow. Also defines `ApprovalStatus` and `WorkflowStatus` enums.

**Input:** PR data from GitHub client
**Output:** A Pydantic model that LangGraph can mutate
**State modified:** This IS the state

### `app/graph/workflow.py` (118 lines)

**Who calls it:** `routes.py` (line 69) calls `build_workflow().compile()`.

**What it does:**
1. Defines LangGraph nodes (`security_review_node`, `aggregation_node`)
2. Defines the graph topology (START → security → aggregate → END)
3. Implements aggregation logic (combining agent reviews)
4. Computes overall confidence and severity

**Input:** `WorkflowState` (from routes.py)
**Output:** Updated `WorkflowState` (final state after all nodes run)
**State modified:** Sets `security_review`, `aggregated_review`, `workflow_status`, `completed_at`, `execution_time_seconds`

### `app/agents/security_agent.py` (117 lines)

**Who calls it:** `workflow.py` (line 22) calls `run_security_review()`.

**What it does:**
1. Builds system and user prompts for the LLM
2. Sends PR data to the LLM via `LLMService`
3. Parses the LLM's JSON response into `Finding` and `AgentReview` objects
4. Has retry logic for LLM failures

**Input:** `LLMService`, `pr_title`, `pr_body`, `diffs`
**Output:** `AgentReview` Pydantic model
**State modified:** None (returns a dict that workflow.py merges into state)

### `app/services/llm_service.py` (99 lines)

**Who calls it:** `security_agent.py` (line 84) calls `llm.chat_completion()`.

**What it does:**
1. Creates an async HTTP client configured for OpenRouter API
2. Sends chat completion requests with messages
3. Parses JSON responses (handles markdown code blocks)
4. Has retry logic for HTTP errors

**Input:** `messages` (list of role/content dicts), optional `response_format`
**Output:** `dict[str, Any]` (parsed JSON from LLM)
**State modified:** None (pure service)

---

## 13. Responsibility of Each Major Class/Function

### Classes

#### `GitHubClient` (`app/github/client.py:39`)

| Aspect | Detail |
|---|---|
| **Called by** | `routes.py:43` |
| **Input** | `GITHUB_TOKEN` from environment |
| **Output** | PR metadata, changed files, diffs |
| **State modified** | None |

Key methods:
- `parse_pr_url(pr_url)` — regex extraction of owner/repo/number
- `get_repository(owner, repo)` — gets PyGithub Repository object
- `fetch_pr_metadata(owner, repo, pr_number)` — gets PR title, body, branches
- `fetch_changed_files(owner, repo, pr_number)` — gets list of changed files
- `fetch_pr_diffs(owner, repo, pr_number)` — gets {filename: diff} dict
- `fetch_pr_data(pr_url)` — convenience method that calls all of the above

#### `LLMService` (`app/services/llm_service.py:23`)

| Aspect | Detail |
|---|---|
| **Called by** | `security_agent.py:84`, `workflow.py:20` |
| **Input** | API key, model name, temperature, max_tokens |
| **Output** | Parsed JSON dict from LLM response |
| **State modified** | None |

Key methods:
- `__init__()` — creates httpx.AsyncClient with OpenRouter headers
- `chat_completion(messages, response_format)` — sends POST to `/chat/completions`
- `close()` — closes the HTTP client
- `_parse_json(content)` — strips markdown code fences, parses JSON

#### `WorkflowState` (`app/graph/state.py:22`)

| Aspect | Detail |
|---|---|
| **Called by** | `routes.py:55`, `workflow.py:19,37` |
| **Input** | PR data from GitHub |
| **Output** | Pydantic model passed through workflow |
| **State modified** | This IS the state |

This is the most important class in the system. Every node reads from it and writes to it.

#### `AgentReview` (`app/schemas/review.py:33`)

| Aspect | Detail |
|---|---|
| **Called by** | `security_agent.py:102`, `workflow.py:38` |
| **Input** | LLM response data |
| **Output** | Validated review object |
| **State modified** | None |

Represents one agent's complete review. Contains: agent name, summary, confidence (0-1), findings list, execution time.

#### `AggregatedReview` (`app/schemas/review.py:41`)

| Aspect | Detail |
|---|---|
| **Called by** | `workflow.py:72`, `routes.py:87` |
| **Input** | Multiple AgentReview objects |
| **Output** | Combined review with overall metrics |
| **State modified** | None |

The final output. Contains: PR info, summary, overall confidence, overall severity, all findings, all agent reviews, warnings, approval flag.

#### `Finding` (`app/schemas/review.py:22`)

| Aspect | Detail |
|---|---|
| **Called by** | `security_agent.py:87` |
| **Input** | LLM-generated finding data |
| **Output** | Validated finding object |
| **State modified** | None |

A single issue: title, description, severity, category, file path, line number, code snippet, suggested fix.

### Functions

#### `build_workflow()` (`app/graph/workflow.py:108`)

| Aspect | Detail |
|---|---|
| **Called by** | `routes.py:69` |
| **Input** | None |
| **Output** | Compiled LangGraph `StateGraph` |
| **State modified** | None |

Defines the graph: which nodes exist, which edges connect them. Currently: START → security_review → aggregate → END.

#### `security_review_node()` (`app/graph/workflow.py:19`)

| Aspect | Detail |
|---|---|
| **Called by** | LangGraph (during workflow execution) |
| **Input** | `WorkflowState` (current state) |
| **Output** | `{"security_review": AgentReview}` or `{"failed_agents": [...]}` |
| **State modified** | `security_review` or `failed_agents` |

LangGraph node. Creates LLMService, calls the security agent, returns the result as a dict for state merging.

#### `aggregation_node()` (`app/graph/workflow.py:37`)

| Aspect | Detail |
|---|---|
| **Called by** | LangGraph (during workflow execution) |
| **Input** | `WorkflowState` (with agent reviews populated) |
| **Output** | `{"aggregated_review": ..., "workflow_status": ..., "completed_at": ..., "execution_time_seconds": ...}` |
| **State modified** | `aggregated_review`, `workflow_status`, `completed_at`, `execution_time_seconds` |

Combines all agent reviews, computes overall metrics, builds the final `AggregatedReview`.

#### `run_security_review()` (`app/agents/security_agent.py:69`)

| Aspect | Detail |
|---|---|
| **Called by** | `workflow.py:22` |
| **Input** | `LLMService`, `pr_title`, `pr_body`, `diffs` |
| **Output** | `AgentReview` |
| **State modified** | None |

The core agent logic. Builds prompts, calls LLM, parses response into structured objects.

#### `build_user_prompt()` (`app/agents/security_agent.py:50`)

| Aspect | Detail |
|---|---|
| **Called by** | `run_security_review()` at line 81 |
| **Input** | `pr_title`, `pr_body`, `diffs` |
| **Output** | Formatted string for the LLM |
| **State modified** | None |

Formats PR data into a human-readable prompt with file diffs.

#### `_build_summary()` (`app/graph/workflow.py:101`)

| Aspect | Detail |
|---|---|
| **Called by** | `aggregation_node()` at line 66 |
| **Input** | `list[AgentReview]` |
| **Output** | Markdown summary string |
| **State modified** | None |

Simple string builder: joins each agent's name and summary with bold formatting.

---

## 14. How the Security Agent Works Internally

The security agent is the only implemented agent. Here's exactly what it does:

### 14.1 System Prompt

**File:** `app/agents/security_agent.py:16-47`

The system prompt tells the LLM to act as a security engineer. It lists specific vulnerability types to look for:

```
- Exposed secrets, API keys, credentials
- Unsafe deserialization (pickle, yaml.load, eval, exec)
- SQL injection risks
- Authentication/authorization bypasses
- Dangerous subprocess or shell execution
- Insecure configurations (debug mode, permissive CORS, etc.)
- Path traversal vulnerabilities
- Insecure cryptographic practices
```

It also specifies the **exact JSON schema** the LLM must return.

### 14.2 User Prompt Construction

**File:** `app/agents/security_agent.py:50-60`

```python
def build_user_prompt(pr_title: str, pr_body: str, diffs: dict[str, str]) -> str:
    parts = [f"Pull Request: {pr_title}", f"Description: {pr_body}", ""]
    if not diffs:
        parts.append("No file diffs available for review.")
    else:
        parts.append(f"Changed files ({len(diffs)}):")
        for filename, diff in diffs.items():
            parts.append(f"\n--- {filename} ---\n{diff}")
    return "\n".join(parts)
```

This creates a readable prompt:

```
Pull Request: Fix XSS vulnerability in user input
Description: This PR sanitizes user input before rendering.

Changed files (2):

--- src/handler.py ---
@@ -10,3 +10,5 @@
-def render(user_input):
-    return f"<div>{user_input}</div>"
+def render(user_input):
+    sanitized = html.escape(user_input)
+    return f"<div>{sanitized}</div>"

--- src/test_handler.py ---
@@ -5,3 +5,5 @@
-def test_render():
-    assert render("<script>alert(1)</script>") == "..."
+def test_render():
+    assert render("<script>alert(1)</script>") == "<div>&lt;script&gt;alert(1)&lt;/script&gt;</div>"
```

### 14.3 LLM Call

**File:** `app/agents/security_agent.py:79-84`

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": build_user_prompt(pr_title, pr_body, diffs)},
]
response = await llm.chat_completion(messages)
```

Two messages: system prompt (role definition) + user prompt (PR data).

### 14.4 Response Parsing

**File:** `app/agents/security_agent.py:86-98`

```python
findings = [
    Finding(
        title=f["title"],
        description=f["description"],
        severity=Severity(f["severity"]),
        category=FindingCategory.security,
        file_path=f.get("file_path"),
        line_number=f.get("line_number"),
        code_snippet=f.get("code_snippet"),
        suggested_fix=f.get("suggested_fix"),
    )
    for f in response.get("findings", [])
]
```

Each finding from the LLM JSON is validated and converted to a Pydantic `Finding` object. The category is hardcoded to `security` (this agent only does security).

### 14.5 Retry Configuration

**File:** `app/agents/security_agent.py:63-68`

```python
@retry(
    retry=retry_if_exception_type(LLMServiceError),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
)
```

- Retries only on `LLMServiceError` (JSON parse failures)
- Max 2 attempts
- Waits 1s, then up to 5s (exponential backoff)
- Re-raises the exception if all retries fail

### 14.6 Security Agent Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   SECURITY AGENT FLOW                        │
│                                                              │
│  Input: pr_title, pr_body, diffs                            │
│                                                              │
│  1. build_user_prompt()                                     │
│     └── Formats PR data into readable text                  │
│                                                              │
│  2. messages = [SYSTEM_PROMPT, user_prompt]                 │
│                                                              │
│  3. llm.chat_completion(messages)  [with retry]             │
│     └── POST to OpenRouter API                              │
│     └── Parse JSON response                                 │
│                                                              │
│  4. Parse response into Finding objects                     │
│     └── Validate severity enum                              │
│     └── Set category = "security"                           │
│                                                              │
│  5. Build AgentReview                                       │
│     └── agent_name = "security"                             │
│     └── summary = response["summary"]                       │
│     └── confidence = response["confidence"]                 │
│     └── findings = [Finding, ...]                           │
│     └── agent_execution_time = elapsed                      │
│                                                              │
│  Output: AgentReview                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 15. How OpenRouter Interaction Works

OpenRouter is an API gateway that provides access to many LLM models through a single API.

### 15.1 Client Setup

**File:** `app/services/llm_service.py:23-46`

```python
class LLMService:
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4096,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key or os.environ["OPENROUTER_API_KEY"]
        self.model = model or os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4-20250514")
        self._client = httpx.AsyncClient(
            base_url="https://openrouter.ai/api/v1",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": os.environ.get("APP_URL", "http://localhost:8000"),
                "X-Title": "Multi-Agent PR Reviewer",
            },
            timeout=httpx.Timeout(self.timeout),
        )
```

Key details:
- **Base URL:** `https://openrouter.ai/api/v1`
- **Auth:** Bearer token from `OPENROUTER_API_KEY`
- **Model:** Defaults to `anthropic/claude-sonnet-4-20250514` (but `.env` overrides to `deepseek/deepseek-chat-v3-0324:free`)
- **Temperature:** 0.0 (deterministic — important for code review consistency)
- **Max tokens:** 4096 (max response length)
- **Timeout:** 120 seconds
- **HTTP-Referer and X-Title:** OpenRouter requires these for usage tracking

### 15.2 Request Format

**File:** `app/services/llm_service.py:62-74`

```python
payload = {
    "model": self.model,
    "messages": messages,
    "temperature": self.temperature,
    "max_tokens": self.max_tokens,
}
if response_format:
    payload["response_format"] = response_format

response = await self._client.post("/chat/completions", json=payload)
```

This sends a POST to `https://openrouter.ai/api/v1/chat/completions` with the standard OpenAI-compatible chat format.

### 15.3 Response Parsing

**File:** `app/services/llm_service.py:77-84`

```python
data = response.json()
content = data["choices"][0]["message"]["content"]
parsed = self._parse_json(content)
return parsed
```

The response structure from OpenRouter:

```json
{
  "choices": [
    {
      "message": {
        "content": "{\"summary\": \"...\", \"findings\": [...]}"
      }
    }
  ],
  "usage": {"prompt_tokens": 100, "completion_tokens": 200}
}
```

### 15.4 JSON Cleanup

**File:** `app/services/llm_service.py:86-99`

```python
@staticmethod
def _parse_json(content: str) -> dict[str, Any]:
    content = content.strip()
    if content.startswith("```json"):
        content = content.removeprefix("```json").removesuffix("```").strip()
    elif content.startswith("```"):
        content = content.removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise LLMServiceError(f"Failed to parse LLM response as JSON: {exc}") from exc
```

LLMs often wrap JSON in markdown code blocks (```json ... ```). This method strips those fences before parsing. If parsing fails, it raises `LLMServiceError` which triggers a retry.

### 15.5 Retry Configuration

**File:** `app/services/llm_service.py:51-56`

```python
@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
```

- Retries on HTTP errors (4xx/5xx), connection errors, and timeouts
- Max 3 attempts
- Waits 2s, 4s, 8s (exponential, capped at 10s)
- Re-raises if all retries fail

### 15.6 OpenRouter Request Flow

```
┌─────────────────────────────────────────────────────────────┐
│                    OPENROUTER INTERACTION                     │
│                                                              │
│  LLMService.chat_completion(messages)                        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  POST https://openrouter.ai/api/v1/chat/completions  │   │
│  │                                                      │   │
│  │  Headers:                                            │   │
│  │    Authorization: Bearer sk-or-v1-...               │   │
│  │    Content-Type: application/json                    │   │
│  │    HTTP-Referer: http://localhost:8000              │   │
│  │    X-Title: Multi-Agent PR Reviewer                  │   │
│  │                                                      │   │
│  │  Body:                                               │   │
│  │    {                                                 │   │
│  │      "model": "deepseek/deepseek-chat-v3-0324:free",│   │
│  │      "messages": [                                   │   │
│  │        {"role": "system", "content": "..."},        │   │
│  │        {"role": "user", "content": "..."}           │   │
│  │      ],                                              │   │
│  │      "temperature": 0.0,                             │   │
│  │      "max_tokens": 4096                              │   │
│  │    }                                                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Response:                                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  {                                                   │   │
│  │    "choices": [{"message": {"content": "{...}"}}],  │   │
│  │    "usage": {"prompt_tokens": N, "completion_tokens": M} │
│  │  }                                                   │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  → _parse_json() → strip markdown → json.loads() → dict     │
└─────────────────────────────────────────────────────────────┘
```

---

## 16. How GitHub Data Retrieval Works

### 16.1 URL Parsing

**File:** `app/github/client.py:13-15, 44-48`

```python
PR_URL_PATTERN = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)"
)

def parse_pr_url(self, pr_url: str) -> tuple[str, str, int]:
    match = PR_URL_PATTERN.match(pr_url)
    if not match:
        raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
    return match.group("owner"), match.group("repo"), int(match.group("number"))
```

The regex uses **named groups** (`?P<name>`) to extract parts:

```
Input:  "https://github.com/facebook/react/pull/27890"
Output: ("facebook", "react", 27890)
```

### 16.2 PyGithub Client

**File:** `app/github/client.py:39-42`

```python
class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ["GITHUB_TOKEN"]
        self._gh = Github(self._token)
```

PyGithub is a Python wrapper around the GitHub REST API. It handles authentication and provides Pythonic objects.

### 16.3 Data Fetching Methods

**`get_repository(owner, repo)`** — `client.py:50-56`

Calls `GET /repos/{owner}/{repo}`. Returns a PyGithub `Repository` object.

**`fetch_pr_metadata(owner, repo, pr_number)`** — `client.py:58-75`

```python
repo_obj = self.get_repository(owner, repo)
pr = repo_obj.get_pull(pr_number)  # GET /repos/{owner}/{repo}/pulls/{number}
return PRMetadata(
    number=pr.number,
    title=pr.title,
    body=pr.body or "",
    state=pr.state,
    base_branch=pr.base.ref,
    head_branch=pr.head.ref,
    head_sha=pr.head.sha,
    url=pr.html_url,
)
```

**`fetch_changed_files(owner, repo, pr_number)`** — `client.py:77-94`

```python
repo_obj = self.get_repository(owner, repo)
pr = repo_obj.get_pull(pr_number)
return [
    ChangedFile(
        filename=f.filename,
        status=f.status,       # "added", "modified", "removed", "renamed"
        additions=f.additions,
        deletions=f.deletions,
        patch=f.patch,         # unified diff text
    )
    for f in pr.get_files()    # GET /repos/{owner}/{repo}/pulls/{number}/files
]
```

**`fetch_pr_diffs(owner, repo, pr_number)`** — `client.py:96-103`

```python
changed_files = self.fetch_changed_files(owner, repo, pr_number)
return {
    f.filename: f.patch or ""
    for f in changed_files
    if f.patch
}
```

Converts the list of `ChangedFile` into a dict: `{"src/file.py": "@@ -1,3 +1,5 @@\n..."}`.

**`fetch_pr_data(pr_url)`** — `client.py:105-111`

```python
owner, repo, pr_number = self.parse_pr_url(pr_url)
metadata = self.fetch_pr_metadata(owner, repo, pr_number)
changed_files = self.fetch_changed_files(owner, repo, pr_number)
diffs = {f.filename: f.patch or "" for f in changed_files if f.patch}
return metadata, changed_files, diffs
```

This is the **convenience method** that `routes.py` calls. It does everything in one call.

### 16.4 GitHub API Call Sequence

```
┌─────────────────────────────────────────────────────────────┐
│                   GITHUB DATA RETRIEVAL                      │
│                                                              │
│  routes.py: github_client.fetch_pr_data(pr_url)              │
│                                                              │
│  1. parse_pr_url(pr_url)                                     │
│     └── Regex extract: owner, repo, pr_number               │
│                                                              │
│  2. get_repository(owner, repo)                              │
│     └── GET /repos/{owner}/{repo}                           │
│     └── Returns Repository object                           │
│                                                              │
│  3. fetch_pr_metadata(owner, repo, pr_number)                │
│     └── repo.get_pull(pr_number)                            │
│     └── GET /repos/{owner}/{repo}/pulls/{number}            │
│     └── Returns PRMetadata (title, body, branches, SHA)     │
│                                                              │
│  4. fetch_changed_files(owner, repo, pr_number)              │
│     └── pr.get_files()                                      │
│     └── GET /repos/{owner}/{repo}/pulls/{number}/files      │
│     └── Returns list[ChangedFile]                           │
│                                                              │
│  5. Build diffs dict from ChangedFile[].patch                │
│                                                              │
│  Return: (PRMetadata, list[ChangedFile], dict[str, str])     │
└─────────────────────────────────────────────────────────────┘
```

**Note:** `get_repository` is called twice (once in `fetch_pr_metadata`, once in `fetch_changed_files`). This is a minor inefficiency — it could be cached.

---

## 17. How Structured Outputs Are Validated

This system uses **two layers** of validation:

### Layer 1: Pydantic Model Validation

**File:** `app/schemas/review.py`

Every data structure is a Pydantic `BaseModel`. When you create an instance, Pydantic validates all fields:

```python
Finding(
    title="XSS vulnerability",           # str — required
    description="...",                   # str — required
    severity=Severity("critical"),       # enum — must be valid value
    category=FindingCategory.security,   # enum — must be valid value
    file_path="src/handler.py",          # str | None — optional
    line_number=42,                      # int | None — optional
    code_snippet="...",                  # str | None — optional
    suggested_fix="...",                 # str | None — optional
)
```

If `severity` is `"super-critical"` (not in the enum), Pydantic raises `ValidationError`.

**Confidence validation:**

```python
class AgentReview(BaseModel):
    confidence: float = Field(ge=0.0, le=1.0)
```

If the LLM returns `confidence: 1.5`, Pydantic rejects it.

**Finding sort validation:**

```python
class AggregatedReview(BaseModel):
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
```

Every time an `AggregatedReview` is created, findings are automatically sorted by severity (critical first).

### Layer 2: LLM Response JSON Parsing

**File:** `app/services/llm_service.py:86-99`

The LLM returns a string. `_parse_json()` tries to parse it as JSON. If it fails:

1. `json.JSONDecodeError` is caught
2. `LLMServiceError` is raised
3. Tenacity retry decorator catches it and retries (up to 2 times for the agent, 3 times for the service)

### Validation Flow

```
┌─────────────────────────────────────────────────────────────┐
│                   VALIDATION PIPELINE                         │
│                                                              │
│  LLM Response (string)                                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ "```json\n{\"summary\": \"...\", \"findings\": [...]}\n```" │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  _parse_json()                                                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 1. Strip ```json / ``` fences                        │   │
│  │ 2. json.loads() → dict                               │   │
│  │ 3. If fails → LLMServiceError → retry                │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  security_agent.py parsing                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Finding(title=f["title"], ...)                       │   │
│  │ Severity(f["severity"])  ← enum validation           │   │
│  │ AgentReview(confidence=response["confidence"])       │   │
│  │   ← Field(ge=0.0, le=1.0) validation                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  aggregation_node                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ AggregatedReview(...)                                │   │
│  │   ← field_validator: sort_findings_by_severity       │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  routes.py response                                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ PRReviewResponse(review=aggregated, ...)             │   │
│  │   ← FastAPI serializes to JSON for HTTP response     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 18. Failure Handling and Retries

There are **three levels** of failure handling:

### Level 1: LLMService Retries (HTTP layer)

**File:** `app/services/llm_service.py:51-56`

```python
@retry(
    retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.TimeoutException)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
```

Retries on:
- `httpx.HTTPStatusError` — HTTP 4xx/5xx responses
- `httpx.ConnectError` — cannot connect to OpenRouter
- `httpx.TimeoutException` — request took > 120 seconds

Wait pattern: 2s → 4s → 8s (exponential, capped at 10s)

### Level 2: Agent Retries (LLM parsing layer)

**File:** `app/agents/security_agent.py:63-68`

```python
@retry(
    retry=retry_if_exception_type(LLMServiceError),
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=5),
    reraise=True,
)
```

Retries on:
- `LLMServiceError` — JSON parse failure (LLM returned invalid JSON)

Wait pattern: 1s → 2s (exponential, capped at 5s)

**Combined effect:** If the LLM returns invalid JSON, the agent retries up to 2 times. Each retry triggers the LLMService retry logic too (up to 3 times per attempt). So worst case: 2 × 3 = 6 HTTP attempts.

### Level 3: Workflow Node Graceful Degradation

**File:** `app/graph/workflow.py:19-34`

```python
async def security_review_node(state: WorkflowState) -> dict:
    llm = _build_llm_service()
    try:
        review = await run_security_review(...)
        return {"security_review": review}
    except Exception as exc:
        logger.error("workflow_security_failed", error=str(exc))
        return {"failed_agents": state.failed_agents + ["security"]}
    finally:
        await llm.close()
```

**This is critical:** If the security agent fails completely (all retries exhausted), the node does NOT crash the workflow. Instead, it returns `{"failed_agents": ["security"]}` and the workflow continues to the aggregation node.

The aggregation node handles this:

```python
# workflow.py:68-70
warnings = []
if state.failed_agents:
    warnings.append(f"Failed agents: {', '.join(state.failed_agents)}")
```

The final response includes a warning about the failed agent.

### Level 4: API-Level Error Handling

**File:** `app/api/routes.py:45-53, 71-78`

```python
# GitHub fetch failure → 400 Bad Request
try:
    owner, repo, pr_number = github_client.parse_pr_url(request.pr_url)
    metadata, changed_files, diffs = github_client.fetch_pr_data(request.pr_url)
except Exception as exc:
    raise HTTPException(status_code=400, detail=f"Failed to fetch PR data: {exc}")

# Workflow execution failure → 500 Internal Server Error
try:
    final_state = await workflow.ainvoke(state.model_dump())
except Exception as exc:
    raise HTTPException(status_code=500, detail=f"Workflow execution failed: {exc}")
```

### Failure Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    FAILURE HANDLING                          │
│                                                              │
│  LLM returns invalid JSON                                    │
│  └── LLMServiceError raised                                  │
│      └── tenacity retries (up to 2x for agent)               │
│          └── each retry: tenacity retries HTTP (up to 3x)    │
│              └── if all fail: exception propagates           │
│                  └── security_review_node catches it         │
│                      └── returns {"failed_agents": ["security"]} │
│                          └── aggregation_node continues      │
│                              └── warning added to response   │
│                                  └── 200 OK with warning     │
│                                                              │
│  GitHub API fails                                            │
│  └── GithubException raised                                  │
│      └── routes.py catches it                                │
│          └── HTTP 400 Bad Request                            │
│                                                              │
│  Workflow crashes (unexpected error)                         │
│  └── Exception raised                                        │
│      └── routes.py catches it                                │
│          └── HTTP 500 Internal Server Error                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 19. Why Pydantic Is Important Here

Pydantic is used **everywhere** in this system. It's not just for validation — it's the backbone of the entire data flow.

### 19.1 Request/Response Validation

```python
class PRReviewRequest(BaseModel):
    pr_url: str = Field(..., description="GitHub pull request URL")
```

FastAPI uses this to automatically:
- Parse the JSON body
- Validate that `pr_url` exists and is a string
- Return a 422 error if validation fails
- Generate OpenAPI documentation

### 19.2 State Serialization for LangGraph

```python
state = WorkflowState(...)
final_state = await workflow.ainvoke(state.model_dump())
```

LangGraph works with plain dicts, not Pydantic models. `model_dump()` converts the model to a dict. When LangGraph returns the final state, it's a dict that gets converted back to model-like access via `.get()`.

### 19.3 Data Integrity

Without Pydantic, the LLM could return:
- `confidence: "high"` instead of `0.85` → Pydantic rejects it (must be float)
- `severity: "extreme"` instead of `"critical"` → Pydantic rejects it (must be enum)
- Missing `title` field → Pydantic rejects it (required field)

This prevents garbage data from flowing through the system.

### 19.4 Automatic Sorting

```python
@field_validator("findings")
def sort_findings_by_severity(cls, v): ...
```

Pydantic validators run automatically when the model is created. No manual sorting needed.

### 19.5 Type Safety

```python
class AgentReview(BaseModel):
    agent_name: str
    confidence: float = Field(ge=0.0, le=1.0)
    findings: list[Finding] = Field(default_factory=list)
```

IDE autocomplete works. Type checkers (mypy) can verify correctness. The `Field` constraints enforce business rules.

---

## 20. Current MVP Limitations

This is an MVP (Minimum Viable Product). Here's what's **not** implemented yet:

### 20.1 Only One Agent

The architecture supports multiple agents, but only `security_agent` exists. The `WorkflowState` has slots for `architecture_review` and `quality_review`, but no agents populate them.

### 20.2 No Parallel Execution

Currently: START → security → aggregate → END (sequential).

In a multi-agent setup, security/architecture/quality could run **in parallel**. LangGraph supports this, but the current graph is linear.

### 20.3 No Checkpointing

LangGraph supports saving state between nodes (checkpointing). This is not configured. If the server crashes mid-workflow, the review is lost.

### 20.4 No Streaming

The API waits for the entire workflow to complete before responding. For large PRs, this could take 30+ seconds. Streaming partial results would improve UX.

### 20.5 No PR Comment Posting

The system returns a JSON response but does **not** post comments on the actual GitHub PR. A fully integrated system would post review comments inline on the PR.

### 20.6 No Webhook Integration

Currently, you must manually POST to the API. A production system would listen to GitHub webhooks and auto-review PRs when they're opened.

### 20.7 Prompts Are Inline

System prompts are hardcoded strings in Python files (`security_agent.py:16`). They should be in the `app/prompts/` directory (which exists but is empty) for easier iteration.

### 20.8 No Tests

The `tests/` directory is empty. No unit tests, no integration tests.

### 20.9 No Docker Setup

`docker-compose.yml` is empty. No Dockerfile exists. Deployment is manual.

### 20.10 No Streamlit UI

The `streamlit_ui/` directory is empty. The dependency is installed but unused.

### 20.11 No API Key Rotation

The `GITHUB_TOKEN` and `OPENROUTER_API_KEY` are read once at startup. No rotation, no multi-key support.

### 20.12 No Rate Limiting

No rate limiting on the API endpoint. Anyone with the URL can spam requests.

---

## 21. Future Roadmap

These are logical next steps based on the current architecture:

### Phase 1: Complete Single-Agent Flow
- [ ] Move prompts to `app/prompts/` directory
- [ ] Add unit tests for security agent
- [ ] Add integration tests for GitHub client
- [ ] Dockerize the application
- [ ] Add API rate limiting

### Phase 2: Add More Agents
- [ ] Implement architecture review agent
- [ ] Implement code quality review agent
- [ ] Make agents run in parallel (LangGraph parallel nodes)
- [ ] Add agent-specific retry policies

### Phase 3: GitHub Integration
- [ ] Add GitHub webhook listener
- [ ] Post review comments on PRs
- [ ] Post inline comments on specific lines
- [ ] Support PR approval/rejection via GitHub API

### Phase 4: Production Readiness
- [ ] Add checkpointing for workflow state recovery
- [ ] Add streaming responses
- [ ] Add authentication to the API
- [ ] Add monitoring and alerting
- [ ] Add Streamlit UI for dashboard

### Phase 5: Advanced Features
- [ ] Learn from human reviewer feedback
- [ ] Configurable review rules per repository
- [ ] Support GitLab, Bitbucket
- [ ] Add code fix suggestions that can be applied as PRs

---

## 22. Glossary of Important Agentic AI Concepts

### Agent

A software component that perceives its environment, makes decisions, and takes actions. In this system, each agent is a specialized AI reviewer (security, architecture, quality) that analyzes PR diffs and returns structured findings.

**Example:** `security_agent.py` is an agent. It receives PR data, calls an LLM with a security-focused prompt, and returns security findings.

### Multi-Agent System

A system where multiple specialized agents work together to solve a problem. Each agent has its own expertise, prompts, and output format.

**In this project:** The architecture is designed for security + architecture + quality agents to collaborate via the aggregation node.

### Agent Workflow / Graph

A directed graph where nodes are agents (or processing steps) and edges define the execution order. LangGraph implements this.

**In this project:** `START → security_review → aggregate → END`

### State

The data structure that flows through the workflow, carrying information between nodes. Each node reads from state and writes updates to it.

**In this project:** `WorkflowState` (Pydantic model in `app/graph/state.py`)

### Node

A single step in the workflow graph. A node is a function that takes the current state and returns a dict of updates.

**In this project:** `security_review_node()` and `aggregation_node()` are nodes.

### Edge

A connection between nodes that defines execution order. Edges can be unconditional (always go from A to B) or conditional (go from A to B if state.x is true).

**In this project:** All edges are unconditional. `START → security_review → aggregate → END`

### Prompt

The text sent to an LLM to instruct it what to do. Usually consists of a system prompt (role/persona) and user prompt (task/data).

**In this project:** `SYSTEM_PROMPT` in `security_agent.py:16` + `build_user_prompt()` output.

### Tool / Tool Use

When an agent can call external functions (APIs, databases, etc.) during its reasoning. Not used in this project yet, but agents could use tools to fetch additional context.

### Structured Output

Forcing the LLM to return data in a specific format (JSON schema) rather than free text. This makes the output machine-processable.

**In this project:** The system prompt specifies an exact JSON schema. `_parse_json()` validates it.

### Temperature

An LLM parameter controlling randomness. 0.0 = deterministic (same input → same output). 1.0 = creative/varied. Code review uses 0.0 for consistency.

**In this project:** `temperature=0.0` in `LLMService.__init__()`.

### Retry / Backoff

Automatically retrying a failed operation, with increasing delays between attempts. Prevents transient failures from breaking the system.

**In this project:** Tenacity decorators on `LLMService.chat_completion()` and `run_security_review()`.

### Graceful Degradation

When a component fails but the system continues with reduced functionality rather than crashing entirely.

**In this project:** If the security agent fails, the workflow continues. The aggregation node adds a warning to the response instead of failing.

### Checkpointing

Saving workflow state to persistent storage between nodes. Allows resuming a workflow after a crash.

**In this project:** Not implemented yet. LangGraph supports it.

### LLM Gateway / Router

A service that provides access to multiple LLM models through a single API. Lets you switch models without changing code.

**In this project:** OpenRouter is the LLM gateway. The model is configurable via `OPENROUTER_MODEL` env var.

### Context Window

The maximum amount of text an LLM can process in a single request. If PR diffs exceed this, the review will fail or truncate.

**In this project:** Not explicitly handled. Large PRs could exceed the context window of the chosen model.

### Orchestration

The process of coordinating multiple agents, managing their execution order, passing data between them, and combining their results.

**In this project:** LangGraph is the orchestrator. `build_workflow()` defines the orchestration logic.

### Agent Review

The output of a single agent: a structured assessment with findings, confidence score, and summary.

**In this project:** `AgentReview` Pydantic model.

### Aggregated Review

The combined output of all agents: overall confidence, overall severity, all findings sorted by severity, and per-agent breakdowns.

**In this project:** `AggregatedReview` Pydantic model, built in `aggregation_node()`.

---

## Appendix: Complete File Dependency Map

```
┌─────────────────────────────────────────────────────────────┐
│                    FILE DEPENDENCY GRAPH                     │
│                                                              │
│  app/main.py                                                 │
│  └── imports app.api.routes.router                           │
│                                                              │
│  app/api/routes.py                                           │
│  ├── imports app.github.client.GitHubClient                  │
│  ├── imports app.graph.state.WorkflowState                   │
│  ├── imports app.graph.workflow.build_workflow               │
│  └── imports app.schemas.review.AggregatedReview             │
│                                                              │
│  app/graph/workflow.py                                       │
│  ├── imports app.agents.security_agent.run_security_review   │
│  ├── imports app.graph.state.WorkflowState, WorkflowStatus   │
│  ├── imports app.schemas.review.AgentReview, AggregatedReview│
│  └── imports app.services.llm_service.LLMService             │
│                                                              │
│  app/graph/state.py                                          │
│  ├── imports app.schemas.review.AgentReview, AggregatedReview│
│  └── (no other local imports)                                │
│                                                              │
│  app/agents/security_agent.py                                │
│  ├── imports app.schemas.review.*                            │
│  └── imports app.services.llm_service.LLMService, LLMServiceError │
│                                                              │
│  app/services/llm_service.py                                 │
│  └── (no local imports — only stdlib + httpx + structlog + tenacity) │
│                                                              │
│  app/github/client.py                                        │
│  └── (no local imports — only stdlib + structlog + PyGithub) │
│                                                              │
│  app/schemas/review.py                                       │
│  └── (no local imports — only stdlib + pydantic)             │
│                                                              │
│  DEPENDENCY DIRECTION (no circular deps):                    │
│                                                              │
│  main.py → routes.py → workflow.py → security_agent.py      │
│                  → state.py    → llm_service.py              │
│                  → client.py   → schemas/review.py           │
│                                                              │
│  All dependencies flow DOWN. No circular imports.            │
└─────────────────────────────────────────────────────────────┘
```

---

## Appendix: How to Run This System

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables (or create .env file)
export GITHUB_TOKEN="your-github-token"
export OPENROUTER_API_KEY="your-openrouter-key"
export MODEL_NAME="deepseek/deepseek-chat-v3-0324:free"

# 3. Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. Send a review request
curl -X POST http://localhost:8000/api/v1/review \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/42"}'
```

---

*This document was written to help you understand the internals of an agentic AI system. Read it alongside the source code, trace through the execution with a debugger, and modify things to see what breaks. That's how you learn.*
