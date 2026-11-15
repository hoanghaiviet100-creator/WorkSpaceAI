from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from backend.core.schemas import GeminiConfigRequest, ProviderSelectRequest
from backend.services.runtime_service import runtime_service

router = APIRouter(prefix="/api/runtime", tags=["Runtime Management"])


@router.get("", response_model=Dict[str, Any])
@router.get("/", response_model=Dict[str, Any], include_in_schema=False)
def get_runtime_status() -> Dict[str, Any]:
    """GET /api/runtime: Retrieves active AI runtime status and configured models."""
    return runtime_service.get_status()


@router.post("/provider", response_model=Dict[str, Any])
def select_provider(req: ProviderSelectRequest) -> Dict[str, Any]:
    """POST /api/runtime/provider: Switches between Ollama and Gemini runtime providers."""
    return runtime_service.select_provider(req.provider)


@router.post("/gemini", response_model=Dict[str, Any])
def configure_gemini(req: GeminiConfigRequest) -> Dict[str, Any]:
    """POST /api/runtime/gemini: Configures Gemini API key; rejects with 409 in offline-only mode."""
    try:
        return runtime_service.configure_gemini(req.api_key)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
