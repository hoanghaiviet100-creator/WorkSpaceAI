from datetime import datetime
import hashlib
import io
import re
from typing import Any, Dict, List, Optional, Tuple
import pypdf

from backend.core.schemas import DocumentChunk, DocumentMetadata
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository


def format_chunk_with_lines(chunk: DocumentChunk) -> str:
    """
    Renders chunk text with explicit [Dòng <line_num>] labels on each physical line.
    Helps local LLMs (e.g. qwen2.5:7b) ground citations to exact physical line coordinates.
    """
    lines = chunk.text.splitlines()
    if not lines:
        return ""
    start = chunk.start_line if chunk.start_line is not None else 1
    labeled_lines = []
    for idx, line in enumerate(lines):
        line_num = start + idx
        labeled_lines.append(f"[Dòng {line_num}] {line}")
    return "\n".join(labeled_lines)


class DocumentService:
    """
    R1/R3 Document Ingestion & Provenance Management Service.
    
    Responsibilities:
    - Text extraction from text-based PDF, TXT, MD, CSV.
    - Explicit rejection of scanned PDFs lacking extractable text layers.
    - Sliding Window / Semantic Paragraph Chunking with 2-line overlap,
      strictly bounded within single pages, annotated with exact (page_number, start_line, end_line).
    - SHA-256 content hashing & version management:
      * Identical hash -> Skip re-ingestion, return existing record.
      * Identical name, different hash -> Increment version (v1 -> v2) and ingest.
    """

    def __init__(self, repository: Optional[WorkspaceRepository] = None) -> None:
        self.repository = repository or workspace_repository

    def compute_hash(self, content_bytes: bytes) -> str:
        """Computes SHA-256 checksum over raw file bytes."""
        return hashlib.sha256(content_bytes).hexdigest()

    def _clean_page_lines(self, raw_text: str) -> str:
        """
        Cleans extraneous trailing whitespaces and unifies line breaks
        while preserving physical line boundaries, table alignments,
        and deadline/metric indicator lines.
        """
        raw_lines = raw_text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
        cleaned_lines = []
        for line in raw_lines:
            # Preserve markdown/ASCII table rows
            if "|" in line:
                cleaned = " | ".join(part.strip() for part in line.split("|"))
            # Preserve multi-column spacing
            elif re.search(r"(\b\w+\b\s{3,}\b\w+\b)", line):
                cleaned = re.sub(r"[ \t]{3,}", "  |  ", line).strip()
            else:
                cleaned = re.sub(r"[ \t]+", " ", line).strip()
            cleaned_lines.append(cleaned)
        return "\n".join(cleaned_lines)

    def parse_pdf_pages(self, filename: str, content_bytes: bytes) -> List[Tuple[int, str]]:
        """
        Extracts extractable text layer from a PDF file.
        Rejects scanned image-only PDFs with an explicit ValueError.
        """
        reader = pypdf.PdfReader(io.BytesIO(content_bytes))
        pages: List[Tuple[int, str]] = []
        has_any_text = False

        for page_idx, page in enumerate(reader.pages, start=1):
            extracted = page.extract_text() or ""
            cleaned = self._clean_page_lines(extracted)
            if cleaned.strip():
                has_any_text = True
                pages.append((page_idx, cleaned))

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
            clean = self._clean_page_lines(p)
            if clean.strip():
                pages.append((idx, clean))

        if not pages:
            clean_all = self._clean_page_lines(decoded)
            pages = [(1, clean_all.strip())]

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
        Splits a single page into sliding window / semantic paragraph chunks with 2-line overlap.
        Guarantees:
        - Every chunk belongs strictly to exactly one page.
        - Chunks aim for 600-1000 characters (or 8-18 lines).
        - Consecutive chunks on the same page have 2 lines of overlap at boundaries.
        - Exact 1-based start_line and end_line coordinates.
        """
        lines = page_text.splitlines()
        if not lines:
            return []

        # Find line units (preserving 1-based line numbering)
        # If total page content is compact (<= 900 chars and <= 16 lines), keep as a single chunk
        total_chars = sum(len(l) for l in lines)
        if total_chars <= 900 and len(lines) <= 16:
            # Trim blank lines at start and end for tight bounds
            s_idx = 0
            while s_idx < len(lines) and not lines[s_idx].strip():
                s_idx += 1
            e_idx = len(lines) - 1
            while e_idx >= 0 and not lines[e_idx].strip():
                e_idx -= 1

            if s_idx > e_idx:
                return []

            chunk_text = "\n".join(lines[s_idx : e_idx + 1])
            start_l = s_idx + 1
            end_l = e_idx + 1
            return [
                DocumentChunk(
                    chunk_id=f"{doc_id}_p{page_num}_c0",
                    doc_id=doc_id,
                    doc_name=doc_name,
                    page_number=page_num,
                    start_line=start_l,
                    end_line=end_l,
                    section_header=f"Page {page_num}, Lines {start_l}-{end_l}",
                    text=chunk_text,
                    doc_version=doc_version,
                    doc_hash=doc_hash,
                )
            ]

        # Sliding window chunking with 2-line overlap
        chunks: List[DocumentChunk] = []
        chunk_idx = 0
        n_lines = len(lines)
        curr_idx = 0

        # Target parameters
        target_max_chars = 950
        min_chars = 400
        overlap_lines = 2

        while curr_idx < n_lines:
            # Skip empty leading lines
            while curr_idx < n_lines and not lines[curr_idx].strip():
                curr_idx += 1
            if curr_idx >= n_lines:
                break

            start_line_1based = curr_idx + 1
            window_lines: List[str] = []
            char_count = 0
            end_idx = curr_idx

            while end_idx < n_lines:
                line_str = lines[end_idx]
                window_lines.append(line_str)
                char_count += len(line_str) + 1
                end_idx += 1

                # If reached minimum characters and hit a paragraph break (empty line or line ending with period)
                # or exceeded target max characters (or 18 lines)
                line_count = len(window_lines)
                is_break = (not line_str.strip()) or (line_count >= 8 and line_str.strip().endswith("."))
                if char_count >= min_chars and is_break:
                    break
                if char_count >= target_max_chars or line_count >= 18:
                    break

            # Trim trailing blank lines in window
            while window_lines and not window_lines[-1].strip():
                window_lines.pop()
                end_idx -= 1

            if window_lines:
                end_line_1based = start_line_1based + len(window_lines) - 1
                chunk_text = "\n".join(window_lines).strip()
                if chunk_text:
                    chunks.append(
                        DocumentChunk(
                            chunk_id=f"{doc_id}_p{page_num}_c{chunk_idx}",
                            doc_id=doc_id,
                            doc_name=doc_name,
                            page_number=page_num,
                            start_line=start_line_1based,
                            end_line=end_line_1based,
                            section_header=f"Page {page_num}, Lines {start_line_1based}-{end_line_1based}",
                            text=chunk_text,
                            doc_version=doc_version,
                            doc_hash=doc_hash,
                        )
                    )
                    chunk_idx += 1

            # Advance with overlap: next start is end_idx - overlap_lines
            next_idx = max(curr_idx + 1, end_idx - overlap_lines)
            if next_idx <= curr_idx:
                next_idx = curr_idx + 1
            curr_idx = next_idx

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

        # Build chunks with line locators and overlap
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
