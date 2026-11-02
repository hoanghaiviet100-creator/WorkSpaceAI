from datetime import datetime
import hashlib
import io
from typing import Any, Dict, List, Optional, Tuple
import pypdf

from backend.core.schemas import DocumentChunk, DocumentMetadata
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository


class DocumentService:
    """
    R1/R3 Document Ingestion & Provenance Management Service.
    
    Responsibilities:
    - Text extraction from text-based PDF, TXT, MD, CSV.
    - Explicit rejection of scanned PDFs lacking extractable text layers.
    - Exact paragraph chunking bounded strictly within single pages,
      annotated with (page_number, start_line, end_line).
    - SHA-256 content hashing & version management:
      * Identical hash -> Skip re-ingestion, return existing record.
      * Identical name, different hash -> Increment version (v1 -> v2) and ingest.
    """

    def __init__(self, repository: Optional[WorkspaceRepository] = None) -> None:
        self.repository = repository or workspace_repository

    def compute_hash(self, content_bytes: bytes) -> str:
        """Computes SHA-256 checksum over raw file bytes."""
        return hashlib.sha256(content_bytes).hexdigest()

    def parse_pdf_pages(self, filename: str, content_bytes: bytes) -> List[Tuple[int, str]]:
        """
        Extracts extractable text layer from a PDF file.
        Rejects scanned image-only PDFs with an explicit ValueError.
        """
        reader = pypdf.PdfReader(io.BytesIO(content_bytes))
        pages: List[Tuple[int, str]] = []
        has_any_text = False

        for page_idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                has_any_text = True
                pages.append((page_idx, text))

        if not has_any_text:
            raise ValueError(
                f"Tài liệu '{filename}' là PDF dạng ảnh quét (scanned) không có lớp văn bản (text layer). "
                "Hệ thống không hỗ trợ OCR cho tệp này."
            )

        return pages

    def parse_text_pages(self, content_bytes: bytes) -> List[Tuple[int, str]]:
        """Parses plain text / markdown file bytes into pages (handles form-feed pagination)."""
        decoded = content_bytes.decode("utf-8-sig", errors="ignore")
        raw_pages = decoded.split("\x0c")  # form-feed split
        pages: List[Tuple[int, str]] = []

        for idx, p in enumerate(raw_pages, start=1):
            clean = p.strip()
            if clean:
                pages.append((idx, clean))

        if not pages:
            pages = [(1, decoded.strip())]

        return pages

    def build_page_chunks(
        self,
        doc_id: str,
        doc_name: str,
        page_num: int,
        page_text: str,
        doc_version: str,
        doc_hash: str,
    ) -> List[DocumentChunk]:
        """
        Splits a single page into paragraph-level chunks with exact 1-based start_line and end_line.
        Guarantee: Every chunk belongs strictly to exactly one page.
        """
        lines = page_text.splitlines()
        chunks: List[DocumentChunk] = []
        para_lines: List[str] = []
        start_line = 1
        line_idx = 1
        chunk_idx = 0

        for line in lines:
            if not line.strip():
                if para_lines:
                    chunk_text = "\n".join(para_lines).strip()
                    if chunk_text:
                        chunks.append(
                            DocumentChunk(
                                chunk_id=f"{doc_id}_p{page_num}_c{chunk_idx}",
                                doc_id=doc_id,
                                doc_name=doc_name,
                                page_number=page_num,
                                start_line=start_line,
                                end_line=line_idx - 1,
                                section_header=f"Page {page_num}, Lines {start_line}-{line_idx - 1}",
                                text=chunk_text,
                                doc_version=doc_version,
                                doc_hash=doc_hash,
                            )
                        )
                        chunk_idx += 1
                    para_lines = []
                start_line = line_idx + 1
            else:
                if not para_lines:
                    start_line = line_idx
                para_lines.append(line)
            line_idx += 1

        if para_lines:
            chunk_text = "\n".join(para_lines).strip()
            if chunk_text:
                chunks.append(
                    DocumentChunk(
                        chunk_id=f"{doc_id}_p{page_num}_c{chunk_idx}",
                        doc_id=doc_id,
                        doc_name=doc_name,
                        page_number=page_num,
                        start_line=start_line,
                        end_line=line_idx - 1,
                        section_header=f"Page {page_num}, Lines {start_line}-{line_idx - 1}",
                        text=chunk_text,
                        doc_version=doc_version,
                        doc_hash=doc_hash,
                    )
                )

        return chunks

    def ingest_file(self, filename: str, content_bytes: bytes) -> Dict[str, Any]:
        """
        Ingests a user file into the workspace.
        Enforces deduplication by SHA-256 hash and automatic version increment.
        """
        lower = filename.lower()
        if not (lower.endswith(".pdf") or lower.endswith((".txt", ".md")) or lower.endswith(".csv")):
            raise ValueError(
                f"Định dạng tệp '{filename}' không được hỗ trợ. Vui lòng tải PDF (text layer), TXT, MD hoặc CSV."
            )

        file_hash = self.compute_hash(content_bytes)

        # Check deduplication: same content hash -> skip re-ingestion
        existing_doc = self.repository.get_document_by_hash(file_hash)
        if existing_doc:
            return {
                "status": "ALREADY_EXISTS",
                "message": f"Tài liệu '{filename}' với nội dung này đã tồn tại trong workspace (phiên bản {existing_doc.version_id}).",
                "document": existing_doc,
                "chunks_count": existing_doc.chunk_count,
            }

        # Check versioning: same name different hash -> new version
        clean_name = filename.strip()
        version_id = self.repository.get_next_version_id(clean_name)
        doc_id = clean_name if version_id == "v1" else f"{clean_name}_{version_id}"

        # Extract pages
        if lower.endswith(".pdf"):
            pages = self.parse_pdf_pages(clean_name, content_bytes)
            file_type = "pdf"
        elif lower.endswith(".csv"):
            csv_text = content_bytes.decode("utf-8-sig", errors="ignore")
            added_count = self.repository.ingest_csv_tasks(
                doc_id=doc_id,
                doc_name=clean_name,
                csv_content=csv_text,
            )
            metadata = self.repository.documents[doc_id]
            metadata.version_id = version_id
            metadata.file_hash = file_hash
            return {
                "status": "INGESTED",
                "message": f"Đã nạp thành công '{clean_name}' (phiên bản {version_id}, {added_count} dòng công việc).",
                "document": metadata,
                "chunks_count": added_count,
            }
        else:
            pages = self.parse_text_pages(content_bytes)
            file_type = "txt"

        # Build chunks with line locators
        all_chunks: List[DocumentChunk] = []
        total_lines_doc = 0

        for page_num, page_text in pages:
            lines = page_text.splitlines()
            total_lines_doc += len(lines) if lines else 1
            page_chunks = self.build_page_chunks(
                doc_id=doc_id,
                doc_name=clean_name,
                page_num=page_num,
                page_text=page_text,
                doc_version=version_id,
                doc_hash=file_hash,
            )
            all_chunks.extend(page_chunks)

        metadata = DocumentMetadata(
            doc_id=doc_id,
            doc_name=clean_name,
            file_type=file_type,
            page_count=len(pages),
            chunk_count=len(all_chunks),
            total_lines=total_lines_doc,
            file_hash=file_hash,
            version_id=version_id,
            uploaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            is_selected=True,
        )

        self.repository.add_document(metadata, all_chunks)

        return {
            "status": "INGESTED",
            "message": f"Đã nạp thành công '{clean_name}' (phiên bản {version_id}, {len(all_chunks)} đoạn, {len(pages)} trang).",
            "document": metadata,
            "chunks_count": len(all_chunks),
        }

    def delete_document(self, doc_id: str) -> bool:
        """Deletes a document from the workspace repository."""
        return self.repository.delete_document(doc_id)

    def list_documents(self) -> List[Dict[str, Any]]:
        """Lists all documents currently in the workspace library."""
        return self.repository.list_documents()

    def set_selected_documents(self, doc_ids: List[str]) -> None:
        """Updates the list of active/selected document IDs."""
        self.repository.set_selected_documents(doc_ids)

    def get_selected_doc_ids(self) -> List[str]:
        """Gets all currently selected document IDs."""
        return self.repository.get_selected_doc_ids()


# Singleton instance
document_service = DocumentService()
