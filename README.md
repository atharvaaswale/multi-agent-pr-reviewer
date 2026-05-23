# 🤖 Multi-Agent PR Reviewer

> **AI-powered multi-agent GitHub Pull Request reviewer** — three specialized AI agents
> review a pull request in parallel, then their findings are aggregated and
> de-duplicated into a single, clean, structured report.

<p align="left">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white">
  <img alt="LangGraph" src="https://img.shields.io/badge/LangGraph-Workflow-1C3C3C">
  <img alt="Streamlit" src="https://img.shields.io/badge/Streamlit-UI-FF4B4B?logo=streamlit&logoColor=white">
  <img alt="Pydantic" src="https://img.shields.io/badge/Pydantic-Validation-E92063?logo=pydantic&logoColor=white">
</p>

---

## ✨ What it does

Paste a GitHub pull request URL and the system:

1. **Fetches** the PR diff and metadata from the GitHub API.
2. **Reviews** the diff with three specialized agents running **in parallel**:
   - 🔐 **Security** — vulnerabilities, exposed secrets, unsafe code
   - 🏛️ **Architecture** — coupling, modularity, scalability, system design
   - ✨ **Quality** — readability, naming, comments, maintainability
3. **Aggregates** every finding, **de-duplicates** semantically equivalent ones,
   and scores overall severity and confidence.
4. **Gates** high-risk reviews behind a human-approval step before posting back to GitHub.

The result is delivered both as a **REST API response** and through **Web (Streamlit) dashboard**.

---
<!--
## 🖼️ Screenshots

> _Add screenshots of the running Streamlit UI here._

| Dashboard | Findings | Agent Breakdown |
|-----------|----------|-----------------|
| _`docs/screenshots/dashboard.png`_ | _`docs/screenshots/findings.png`_ | _`docs/screenshots/agents.png`_ |

Architecture and design diagrams are available in [`images/`](images/).-->

---

## 🏗️ Architecture

<!--```
        GitHub PR URL
              |
              v
      Fetch PR (GitHub API)
              |
   +----------+----------+
   v          v          v
 Security  Architecture Quality
  Agent      Agent       Agent      <- run in parallel (LangGraph)
   +----------+----------+
              v
   Aggregate + Deduplicate          <- semantic de-duplication
              |
              v
      Human Approval Gate           <- high-risk reviews require sign-off
              |
              v
       Post Review to PR
```-->
<img src="images/Multi-Agent Pull Request Reviewer.png">

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| API | **FastAPI** | `POST /api/v1/review` orchestration endpoint |
| Workflow | **LangGraph** | Stateful, parallel multi-agent graph |
| Agents | **LangChain + NVIDIA NIM** | Security / Architecture / Quality reviewers |
| Schemas | **Pydantic** | Strict validation of agent + API payloads |
| Frontend | **Streamlit** | Decoupled dashboard consuming the REST API |
| Logging | **structlog** | Structured JSON logs |

---

## 🚀 Getting Started

### Prerequisites

- Python **3.12+**
- An **NVIDIA NIM API key** (or any OpenAI-compatible provider, e.g. OpenRouter)
- A **GitHub token** with read access to the repositories you want to review

### 1. Clone & configure

```bash
git clone multi-agent-pr-reviewer
cd multi-agent-pr-reviewer
```

Create a `.env` file in the project root:

```env
NVIDIA_API_KEY=your_nvidia_api_key
NVIDIA_MODEL=meta/llama-3.1-8b-instruct
GITHUB_TOKEN=your_github_token
```

### 2. Install dependencies

```bash
# Backend (and everything) — using uv
uv sync

# ...or with pip
pip install -r requirements.txt
```

---

## ▶️ Running the App

The project has **two processes**: the FastAPI backend and the Streamlit frontend.

### Start the backend (terminal 1)

```bash
uvicorn app.main:app --reload
```

The API is now available at **http://localhost:8000** — interactive docs at
**http://localhost:8000/docs**.

### Start the Streamlit frontend (terminal 2)

```bash
# Frontend-only dependencies (lightweight, decoupled from the backend)
pip install -r requirements-streamlit.txt

streamlit run streamlit_app.py
```

The UI opens at **http://localhost:8501**.

> The frontend is fully decoupled — it imports no backend code and only calls
> `POST /api/v1/review` over HTTP. Point it at any backend with the `BACKEND_URL`
> environment variable.

### Using the Streamlit UI

1. Confirm the **Backend** status badge shows 🟢 _Online_.
2. Paste a public GitHub PR URL, e.g. `https://github.com/owner/repo/pull/123`.
3. Click **🚀 Analyze PR** and watch the live agent progress.
4. Explore the results dashboard:
   - **Metrics** — overall severity, approval status, confidence, finding count, runtime
   - **Findings** — expandable, severity-color-coded cards with code snippets and fixes
   - **Agent Breakdown** — per-agent summary, confidence and findings in tabs

---

## 🔌 API Usage

```bash
curl -X POST http://localhost:8000/api/v1/review \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

Response (abridged):

```json
{
  "review": {
    "overall_severity": "high",
    "overall_confidence": 0.83,
    "findings": [
      {
        "title": "Hardcoded secret",
        "severity": "critical",
        "category": "security",
        "file_path": "app/config.py",
        "line_number": 12,
        "suggested_fix": "Load the key from an environment variable."
      }
    ],
    "agent_reviews": [ ... ],
    "requires_approval": true
  },
  "execution_time_seconds": 6.4,
  "failed_agents": []
}
```

---

## 🧪 Testing

```bash
uv run pytest
```

---

## 📂 Project Structure

```
multi-agent-pr-reviewer/
├── app/                      # FastAPI backend
│   ├── agents/               # Security / Architecture / Quality agents
│   ├── graph/                # LangGraph workflow + state
│   ├── github/               # GitHub API client
│   ├── schemas/              # Pydantic models
│   ├── services/             # LLM service, review formatting
│   ├── utils/                # Logging, finding de-duplication
│   └── main.py               # App entrypoint
├── ui/                       # Streamlit frontend helpers
│   ├── api.py                # Backend HTTP client + config
│   ├── components.py         # Reusable UI components
│   └── styles.py             # Palette + custom CSS
├── streamlit_app.py          # Streamlit entrypoint
├── tests/                    # Pytest suite
├── requirements.txt          # Backend dependencies
└── requirements-streamlit.txt# Frontend-only dependencies
```

---

## 🧰 Tech Stack

`Python 3.12` · `FastAPI` · `LangGraph` · `LangChain` · `Pydantic` ·
`Streamlit` · `structlog` · `PyGithub` · `NVIDIA NIM`

---

## 📜 License

Released for portfolio and educational use.
