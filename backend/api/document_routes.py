from typing import Any, Dict, List
from fastapi import APIRouter, File, HTTPException, UploadFile
from backend.core.schemas import DocumentSelectRequest
from backend.services.document_service import document_service

router = APIRouter(prefix="/api/documents", tags=["Document Library"])


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]], include_in_schema=False)
def get_documents() -> List[Dict[str, Any]]:
    """
    GET /api/documents
    Retrieves the list of all documents with their metadata in the workspace.
    """
    return document_service.list_documents()


@router.post("/upload")
async def upload_document(file: UploadFile = File(...)) -> Dict[str, Any]:
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
        result = document_service.ingest_file(file.filename, content_bytes)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi khi xử lý tài liệu: {str(e)}")


@router.delete("/{doc_id}")
def delete_document(doc_id: str) -> Dict[str, Any]:
    """
    DELETE /api/documents/{doc_id}
    Deletes a document from the workspace repository and rebuilds search indices.
    """
    success = document_service.delete_document(doc_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài liệu '{doc_id}' để xóa.")

    return {
        "status": "DELETED",
        "doc_id": doc_id,
        "message": f"Tài liệu '{doc_id}' đã được xóa thành công khỏi thư viện.",
    }


@router.post("/select")
def select_documents(req: DocumentSelectRequest) -> Dict[str, Any]:
    """
    POST /api/documents/select
    Sets the active/selected documents for subsequent queries.
    """
    document_service.set_selected_documents(req.selected_doc_ids)
    return {
        "status": "SELECTION_UPDATED",
        "selected_doc_ids": req.selected_doc_ids,
        "active_count": len(req.selected_doc_ids),
    }
