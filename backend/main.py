from contextlib import asynccontextmanager
from pathlib import Path
import sys

# Ensure project root directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import FastAPI
from backend.api.chat_routes import handle_user_request, router as chat_router
from backend.api.email_routes import approve_email, router as email_router
from backend.repositories.workspace_repository import workspace_repository


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager: seeds workspace data at application startup."""
    workspace_repository.seed_demo_workspace()
    yield


app = FastAPI(
    title="WorkspaceAI — CSC10014 Virtual Assistant Backend",
    lifespan=lifespan,
)

# Include API Routers
app.include_router(chat_router)
app.include_router(email_router)


def seed_demo_workspace() -> None:
    """Manual trigger to seed demo workspace data."""
    workspace_repository.seed_demo_workspace()


# Backward-compatible symbols for frontend or test scripts importing directly from backend.main
__all__ = [
    "app",
    "lifespan",
    "seed_demo_workspace",
    "handle_user_request",
    "approve_email",
]
