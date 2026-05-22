"""Streamlit frontend for the Multi-Agent PR Reviewer.

A thin, fully decoupled presentation layer over the existing FastAPI backend.
It imports no backend code -- it only calls ``POST /api/v1/review`` over HTTP.

Run with:  streamlit run streamlit_app.py
"""

import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests
import streamlit as st
from dotenv import load_dotenv

from ui import api, components
from ui.styles import inject_css

load_dotenv()

st.set_page_config(
    page_title="Multi-Agent PR Reviewer",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PR_URL_PATTERN = re.compile(
    r"^https?://github\.com/[^/\s]+/[^/\s]+/pull/\d+", re.IGNORECASE
)

# Ordered status messages shown while the backend works.
STAGES = [
    "Fetching pull request data from GitHub...",
    "Running Security agent...",
    "Running Architecture agent...",
    "Running Quality agent...",
    "Aggregating & de-duplicating findings...",
]


@st.cache_data(ttl=20, show_spinner=False)
def cached_health(base_url: str) -> bool:
    """Backend health, cached briefly so UI reruns don't re-ping every time."""
    return api.check_health(base_url)


def run_analysis(base_url: str, pr_url: str) -> dict:
    """Call the backend on a worker thread while animating staged progress.

    The ``/review`` endpoint is a single blocking call, so the staged
    messages are an honest approximation of the work happening server-side --
    they advance on a timer and settle on the final stage until the real
    response arrives.
    """
    progress = st.progress(0.0, text=STAGES[0])
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(api.review_pr, base_url, pr_url)
            elapsed = 0.0
            while not future.done():
                time.sleep(0.4)
                elapsed += 0.4
                stage = min(int(elapsed // 2.5), len(STAGES) - 1)
                progress.progress(
                    min(0.92, (stage + 1) / len(STAGES)), text=STAGES[stage]
                )
            result = future.result()  # re-raises backend/network errors
        progress.progress(1.0, text="Review complete.")
        time.sleep(0.3)
        return result
    finally:
        progress.empty()


def handle_submit(base_url: str, pr_url: str) -> None:
    """Validate input, run the analysis and store the outcome in session state."""
    st.session_state.pop("result", None)
    st.session_state.pop("error", None)

    cleaned = pr_url.strip()
    if not cleaned:
        st.session_state["error"] = "Please enter a GitHub pull request URL."
        return
    if not PR_URL_PATTERN.match(cleaned):
        st.session_state["error"] = (
            "That doesn't look like a GitHub PR URL. "
            "Expected format: https://github.com/owner/repo/pull/123"
        )
        return

    try:
        st.session_state["result"] = run_analysis(base_url, cleaned)
    except api.ApiError as exc:
        st.session_state["error"] = f"Backend error ({exc.status_code}): {exc.message}"
    except requests.exceptions.Timeout:
        st.session_state["error"] = (
            "The review timed out. Large pull requests can take a while — "
            "please try again."
        )
    except requests.exceptions.RequestException as exc:
        st.session_state["error"] = f"Could not reach the backend: {exc}"


def main() -> None:
    inject_css()

    provider = api.get_provider()
    model = api.get_model()
    base_url = api.get_backend_url()
    online = cached_health(base_url)

    components.render_sidebar(provider, model)
    components.render_navbar(provider, model, online)

    # ---- Input row ----
    st.markdown(
        "<div class='section-title'>Analyze a Pull Request</div>",
        unsafe_allow_html=True,
    )
    col_input, col_button = st.columns([5, 1], vertical_alignment="bottom")
    pr_url = col_input.text_input(
        "GitHub PR URL",
        placeholder="https://github.com/owner/repo/pull/123",
        label_visibility="collapsed",
    )
    clicked = col_button.button(
        "Analyze",
        type="primary",
        use_container_width=True,
        disabled=not online,
    )
    if not online:
        st.caption(
            "Backend offline — start it with "
            "`uvicorn app.main:app --reload`, then refresh this page."
        )

    if clicked:
        handle_submit(base_url, pr_url)

    # ---- Output ----
    error = st.session_state.get("error")
    result = st.session_state.get("result")

    st.write("")
    if error:
        st.error(error)
    if result:
        components.render_results(result)
    elif not error:
        components.render_empty_state()

    components.render_footer()


if __name__ == "__main__":
    main()