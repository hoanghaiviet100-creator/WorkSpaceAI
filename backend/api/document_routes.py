import os
from typing import Any, Dict, List
from fastapi import APIRouter, File, HTTPException, UploadFile
from pypdf.errors import PdfReadError
from backend.core.schemas import DocumentImportUrlRequest, DocumentRenameRequest, DocumentSelectRequest
from backend.providers.embedding_provider import EmbeddingError
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
        content_bytes = await file.read(25 * 1024 * 1024 + 1)
        if len(content_bytes) > 25 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Document is larger than the 25 MiB upload limit.")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Không thể đọc tệp tải lên.") from None

    if not content_bytes:
        raise HTTPException(status_code=400, detail="Tệp tải lên rỗng.")

    try:
        if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu':
            from backend.services.f1_session_store import retain_original
            retain_original(content_bytes)
        import asyncio
        result = await asyncio.to_thread(document_service.ingest_file, file.filename, content_bytes)
        return result
    except EmbeddingError:
        raise
    except PdfReadError:
        raise HTTPException(status_code=400, detail="The PDF is invalid or unreadable. Upload a valid text-based PDF.") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Lỗi khi xử lý tài liệu.") from None


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


@router.patch("/{doc_id}")
def rename_document(doc_id: str, req: DocumentRenameRequest) -> Dict[str, Any]:
    """
    PATCH /api/documents/{doc_id}
    Renames an existing document in the workspace library.
    """
    updated = document_service.rename_document(doc_id, req.name)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy tài liệu '{doc_id}' để đổi tên.")
    return updated


@router.post("/import-url")
def import_document_url(req: DocumentImportUrlRequest) -> Dict[str, Any]:
    """
    POST /api/documents/import-url
    Imports web reference link as a document in the library.
    """
    if os.getenv("F1_SESSION_B", "false").lower() == "true":
        raise HTTPException(status_code=400, detail="Use uploaded documents. URL import is disabled.")
    return document_service.import_url(req.url, req.title)


@router.get("/{doc_id}/pages/{page}")
def get_document_page(doc_id: str, page: int) -> Dict[str, Any]:
    """
    GET /api/documents/{doc_id}/pages/{page}
    Retrieves full raw text and line count of a specific document page for citation highlighting.
    """
    page_data = document_service.get_document_page(doc_id, page)
    if not page_data:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy trang {page} của tài liệu '{doc_id}'.")
    return page_data
