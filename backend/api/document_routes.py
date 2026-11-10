from typing import Any, Dict, List
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from backend.core.schemas import DocumentSelectRequest
from backend.services.document_service import document_service
from backend.services.workspace_context import WorkspaceServices, resolve_workspace_services
from backend.api.dependencies import workspace_services

router = APIRouter(prefix="/api/documents", tags=["Document Library"])

class SourceLinkRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    title: str = Field(default="", max_length=120)

class SourceRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=180)

@router.post("/import-url")
def import_source_link(req: SourceLinkRequest, scope: WorkspaceServices = Depends(workspace_services)):
    from backend.services.source_formats import fetch_public_source
    try:
        filename, content, url = fetch_public_source(req.url, req.title)
        workspace = resolve_workspace_services(scope)
        result = workspace.documents.ingest_file(filename, content)
        result["document"].source_url = url
        workspace.documents.save_library()
        return result
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

@router.patch("/{doc_id}")
def rename_document(doc_id: str, req: SourceRenameRequest, scope: WorkspaceServices = Depends(workspace_services)):
    try:
        return resolve_workspace_services(scope).documents.rename_document(doc_id, req.name)
    except KeyError:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu.") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None

@router.get("/{doc_id}/pages/{page_number}")
def get_document_page(doc_id: str, page_number: int, scope: WorkspaceServices = Depends(workspace_services)):
    try:
        return resolve_workspace_services(scope).documents.page_text(doc_id, page_number)
    except KeyError:
        raise HTTPException(status_code=404, detail="Không tìm thấy trang tài liệu.") from None
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from None


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]], include_in_schema=False)
def get_documents(scope: WorkspaceServices = Depends(workspace_services)) -> List[Dict[str, Any]]:
    """
    GET /api/documents
    Retrieves the list of all documents with their metadata in the workspace.
    """
    return resolve_workspace_services(scope).documents.list_documents()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...), scope: WorkspaceServices = Depends(workspace_services)) -> Dict[str, Any]:
    """
    POST /api/documents/upload
    Uploads a PDF (with text layer) or TXT/MD file. Extracts paragraphs with line locators,
    computes SHA-256 hash, and performs automatic deduplication/versioning.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Tên tệp không hợp lệ.")

    try:
        content_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Không thể đọc tệp tải lên: {str(e)}")

    if not content_bytes:
        raise HTTPException(status_code=400, detail="Tệp tải lên rỗng.")

    try:
        result = resolve_workspace_services(scope).documents.ingest_file(file.filename, content_bytes)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý tài liệu: {str(e)}")


@router.delete("/{doc_id}")
def delete_document(doc_id: str, scope: WorkspaceServices = Depends(workspace_services)) -> Dict[str, Any]:
    """
    DELETE /api/documents/{doc_id}
    Deletes a document from the workspace repository and rebuilds search indices.
    """
    success = resolve_workspace_services(scope).documents.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài liệu '{doc_id}' để xóa.")

    return {
        "status": "DELETED",
        "doc_id": doc_id,
        "message": f"Tài liệu '{doc_id}' đã được xóa thành công khỏi thư viện.",
    }


@router.post("/select")
def select_documents(req: DocumentSelectRequest, scope: WorkspaceServices = Depends(workspace_services)) -> Dict[str, Any]:
    """
    POST /api/documents/select
    Sets the active/selected documents for subsequent queries.
    """
    resolve_workspace_services(scope).documents.set_selected_documents(req.selected_doc_ids)
    return {
        "status": "SELECTION_UPDATED",
        "selected_doc_ids": req.selected_doc_ids,
        "active_count": len(req.selected_doc_ids),
    }
