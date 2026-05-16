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
    structlog.get_logger(__name__).info("application_started")


@app.on_event("shutdown")
async def shutdown() -> None:
    structlog.get_logger(__name__).info("application_shutdown")
