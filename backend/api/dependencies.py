from typing import Optional
from fastapi import Header, HTTPException
from backend.services.workspace_context import WorkspaceServices, get_workspace_services


def workspace_services(x_workspace_id: Optional[str] = Header(None, alias="X-Workspace-ID")) -> WorkspaceServices:
    try:
        return get_workspace_services(x_workspace_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
