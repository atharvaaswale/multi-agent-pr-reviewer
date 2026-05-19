import os

import structlog
from fastapi import FastAPI

from app.api.routes import router

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)

app = FastAPI(
    title="Multi-Agent PR Reviewer",
    description="AI-assisted engineering workflow automation for GitHub pull request reviews",
    version="0.1.0",
)

app.include_router(router)


@app.on_event("startup")
async def startup() -> None:
    logger = structlog.get_logger(__name__)

    nvidia_api_key = os.getenv("NVIDIA_API_KEY")
    if not nvidia_api_key:
        raise RuntimeError("NVIDIA_API_KEY environment variable is not set")

    model = os.environ.get("NVIDIA_MODEL", "stepfun-ai/step-3.5-flash")

    logger.info(
        "application_started",
        provider="nvidia",
        model=model,
    )


@app.on_event("shutdown")
async def shutdown() -> None:
    structlog.get_logger(__name__).info("application_shutdown")
