"""Backend client + configuration for the Streamlit frontend.

This is the *only* place the frontend touches the outside world. It talks to
the existing FastAPI backend over HTTP (``POST /api/v1/review``) and never
imports backend code, keeping the UI a fully decoupled presentation layer.
"""

import os

import requests

# The backend runs three specialized agents in parallel.
AGENT_COUNT = 3

DEFAULT_BACKEND_URL = "http://localhost:8000"
DEFAULT_MODEL = os.environ.get("NVIDIA_MODEL")

# A full review fires several LLM calls, so allow a generous ceiling.
REVIEW_TIMEOUT_SECONDS = float(os.getenv("REVIEW_TIMEOUT", "600"))
HEALTH_TIMEOUT_SECONDS = 4.0


class ApiError(Exception):
    """Raised when the backend returns a non-200 response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def get_backend_url() -> str:
    """Base URL of the FastAPI backend (override with ``BACKEND_URL``)."""
    return os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL).rstrip("/")


def get_provider() -> str:
    """LLM provider label shown in the UI (override with ``LLM_PROVIDER``)."""
    return os.getenv("LLM_PROVIDER", "NVIDIA")


def get_model() -> str:
    """Active model name, read from the same env var the backend uses."""
    return os.getenv("NVIDIA_MODEL") or DEFAULT_MODEL


def check_health(base_url: str) -> bool:
    """Return ``True`` when the backend health endpoint responds healthy."""
    try:
        resp = requests.get(
            f"{base_url}/api/v1/health", timeout=HEALTH_TIMEOUT_SECONDS
        )
        return resp.status_code == 200 and resp.json().get("status") == "healthy"
    except (requests.RequestException, ValueError):
        return False


def review_pr(base_url: str, pr_url: str) -> dict:
    """Request a multi-agent review for ``pr_url`` and return the JSON payload.

    Raises :class:`ApiError` for backend error responses; network failures
    surface as the underlying ``requests`` exceptions for the caller to handle.
    """
    resp = requests.post(
        f"{base_url}/api/v1/review",
        json={"pr_url": pr_url},
        timeout=REVIEW_TIMEOUT_SECONDS,
    )

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except ValueError:
            detail = resp.text or "Unknown error"
        raise ApiError(str(detail), resp.status_code)

    return resp.json()
