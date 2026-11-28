from contextlib import asynccontextmanager
import logging
import os
import asyncio
from pathlib import Path
import sys

# Ensure project root directory is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.api.chat_routes import handle_user_request, router as chat_router
from backend.api.document_routes import router as document_router
from backend.api.email_routes import approve_email, router as email_router
from backend.api.runtime_routes import router as runtime_router
from backend.core.schemas import RouteType, UserRequest
from backend.repositories.workspace_repository import workspace_repository
from backend.providers.embedding_provider import EmbeddingError
from backend.providers.llm_provider import GenerationError
from backend.services.router_service import route_user_request


logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Embedding seed failure degrades F1 without aborting unrelated APIs."""
    app.state.f1_embedding_ready = False
    app.state.f1_embedding_error = None
    try:
        if os.getenv("F1_SESSION_B", "false").lower() == "true":
            from backend.services.f1_session_store import load
            load(workspace_repository)
        else:
            workspace_repository.seed_demo_workspace()
    except EmbeddingError as exc:
        app.state.f1_embedding_error = exc
        logger.warning("F1 embedding startup failed; semantic endpoints are unavailable")
    else:
        app.state.f1_embedding_ready = True
    app.state.f1_nli_ready = False
    if os.getenv("F1_NLI_WARMUP", "false").lower() == "true":
        from backend.providers.f1_claim_support_provider import get_f1_semantic_verifier
        try:
            await asyncio.to_thread(get_f1_semantic_verifier().warmup)
        except Exception:
            logger.warning("F1 NLI startup failed; semantic support remains fail-closed")
        else:
            app.state.f1_nli_ready = True
    from backend.services.generation_readiness import readiness, enabled as preload_enabled
    if preload_enabled(): readiness.start()
    try:
        yield
    finally:
        if preload_enabled(): readiness.close()
        if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu':
            from backend.providers.embedding_provider import embedding_provider
            embedding_provider.close()


app = FastAPI(
    title="WorkspaceAI — CSC10014 Virtual Assistant Backend",
    lifespan=lifespan,
)

@app.exception_handler(EmbeddingError)
async def handle_embedding_failure(request: Request, exc: EmbeddingError) -> JSONResponse:
    """Return a stable error code without exposing provider URLs or exception details."""
    code = str(exc).partition(":")[0]
    if code not in {
        "EMBEDDING_TIMEOUT", "EMBEDDING_PROVIDER_FAILURE", "EMBEDDING_MODEL_MISSING", "EMBEDDING_NOT_READY",
        "EMBEDDING_MODEL_CHANGED", "EMBEDDING_DIMENSION_MISMATCH", "EMBEDDING_INVALID_CONFIG",
        "EMBEDDING_INVALID_INPUT", "EMBEDDING_INVALID_RESPONSE", "EMBEDDING_INVALID_VECTOR",
    }:
        code = "EMBEDDING_PROVIDER_FAILURE"
    return JSONResponse(status_code=503, content={"detail": f"{code}: Semantic embedding is unavailable."})


@app.exception_handler(GenerationError)
async def handle_generation_failure(request: Request, exc: GenerationError) -> JSONResponse:
    """Expose stable F1 errors without provider URLs, prompts or exception details."""
    code = str(exc)
    if code not in {
        "GENERATION_MODEL_MISSING", "GENERATION_UNAVAILABLE", "GENERATION_TIMEOUT",
        "GENERATION_PROVIDER_FAILURE", "GENERATION_INVALID_RESPONSE", "GENERATION_INVALID_CONFIG",
    }:
        code = "GENERATION_PROVIDER_FAILURE"
    return JSONResponse(status_code=503, content={"detail": f"{code}: Configured generation is unavailable."})


def require_startup_embeddings(request: Request) -> None:
    """Fail closed after a failed seed, including when no chunks were published."""
    if getattr(request.app.state, "f1_embedding_error", None) is not None:
        raise EmbeddingError("EMBEDDING_NOT_READY: semantic embedding startup did not complete")


def require_chat_startup_embeddings(request: Request, req: UserRequest) -> None:
    if getattr(request.app.state, "f1_embedding_error", None) is not None:
        # Preserve routing safeguards, independent flows and no-source abstention.
        route, _ = route_user_request(req.model_copy(deep=True))
        if route == RouteType.QA_FLOW and req.selected_doc_ids != []:
            require_startup_embeddings(request)


def require_document_startup_embeddings(request: Request) -> None:
    if request.method == "POST" and request.url.path.rstrip("/") in {
        "/api/documents/upload", "/api/documents/import-url",
    }:
        require_startup_embeddings(request)


# Enable CORS for Frontend development and local clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(chat_router, dependencies=[Depends(require_chat_startup_embeddings)])
app.include_router(email_router)
app.include_router(document_router, dependencies=[Depends(require_document_startup_embeddings)])
app.include_router(runtime_router)


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


# The local service serves one isolated library. A first workspace binding is persisted;
# a different frontend workspace is rejected instead of silently sharing data.
if os.getenv('F1_SESSION_B','false').lower() == 'true':
    from fastapi.staticfiles import StaticFiles
    from tools.resources import AdmissionDenied
    from backend.services.f1_session_runtime import runtime_lock
    from backend.services.f1_session_store import save
    import re
    @app.exception_handler(AdmissionDenied)
    async def admission_error(request, exc):
        from backend.services.f1_session_runtime import admission_message
        return JSONResponse(status_code=503,content={'detail':admission_message(exc)})
    @app.middleware('http')
    async def isolated_workspace(request, call_next):
        scoped=request.url.path.startswith(('/api/documents','/api/chat'))
        mutating=request.method in ('POST','PATCH','DELETE') and request.url.path.startswith('/api/documents')
        if scoped:
            workspace=request.headers.get('X-Workspace-ID','')
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',workspace):
                return JSONResponse(status_code=400,content={'detail':'A valid X-Workspace-ID is required.'})
            binding=Path(os.getenv('F1_RUNTIME_DIR','runtime'))/'workspace-id.txt'
            binding.parent.mkdir(parents=True,exist_ok=True)
            # Exclusive creation also handles simultaneous first requests.
            try:
                with binding.open('x',encoding='utf-8') as out: out.write(workspace)
            except FileExistsError:
                pass
            if binding.read_text(encoding='utf-8') != workspace:
                return JSONResponse(status_code=409,content={'detail':'This server is bound to one workspace. Reopen the original workspace.'})
        acquired=False
        if mutating:
            acquired=runtime_lock.acquire(blocking=False)
            if not acquired:
                return JSONResponse(status_code=409,content={'detail':'BUSY: another upload or question is running.'})
        try:
            response=await call_next(request)
            if mutating and response.status_code<300:
                save(workspace_repository)
            return response
        finally:
            if acquired: runtime_lock.release()
    frontend_dist=PROJECT_ROOT/'frontend'/'dist'
    if frontend_dist.exists():
        app.mount('/',StaticFiles(directory=frontend_dist,html=True),name='document-frontend')
