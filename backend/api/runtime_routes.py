from urllib.parse import urlsplit
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, SecretStr, ConfigDict
from typing import Literal, Optional

from backend.services.runtime_service import configure_gemini, runtime_status, use_offline, select_provider

router = APIRouter(prefix="/api/runtime", tags=["Local AI configuration"])


class GeminiConfigurationRequest(BaseModel):
    api_key: Optional[SecretStr] = None
    save_locally: bool = True
    model: Optional[Literal["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.1-flash-lite", "gemini-3.5-flash"]] = None
    enable_feature1: bool = False


class OfflineConfigurationRequest(BaseModel):
    save_locally: bool = True


def require_local_settings(request: Request) -> None:
    if not request.client or request.client.host not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(status_code=403, detail="AI settings can only be changed on this device.")
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=403, detail="AI settings must be opened from the local application.")


@router.get("")
def get_runtime_status():
    return runtime_status()


@router.post("/gemini")
def update_gemini_configuration(payload: GeminiConfigurationRequest, request: Request):
    # This local setup screen is not a public credential-management API.
    require_local_settings(request)
    try:
        return configure_gemini(payload.api_key.get_secret_value() if payload.api_key else None, payload.save_locally, payload.model, payload.enable_feature1)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/offline")
def switch_to_offline(payload: OfflineConfigurationRequest, request: Request):
    require_local_settings(request)
    try:
        return use_offline(payload.save_locally)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


class ProviderSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["ollama", "gemini"]


@router.post("/provider")
def switch_provider(payload: ProviderSelectionRequest, request: Request):
    # Selecting a prepared engine is a user action, unlike editing dev credentials.
    # Accept local UI origins behind the Docker proxy; retain the stricter admin gate above.
    origin = request.headers.get("origin")
    if origin and urlsplit(origin).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(status_code=403, detail="Open model selection from the local application.")
    try:
        return select_provider(payload.provider)
    except (ValueError, PermissionError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
