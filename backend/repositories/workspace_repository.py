import csv
from datetime import datetime
import hashlib
import io
import re
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from rank_bm25 import BM25Okapi
from backend.core.schemas import DocumentChunk, DocumentMetadata


def tokenize_vietnamese_english(text: str) -> List[str]:
    """
    Enhanced tokenizer for Vietnamese and English technical text.
    Extracts unigrams and adjacent bigrams (e.g. 'hạn nộp' -> 'hạn_nộp', 'báo cáo' -> 'báo_cáo')
    to greatly improve BM25 lexical retrieval accuracy for multi-word technical terminology.
    """
    words = re.findall(r"\w+", text.lower())
    if not words:
        return []
    tokens = list(words)
    # Extract adjacent bi-grams
    for i in range(len(words) - 1):
        tokens.append(f"{words[i]}_{words[i+1]}")
    return tokens


class WorkspaceRepository:
    """
    R3 Data / Retrieval Capability:
    Supports unstructured (PDF/TXT) and structured (CSV) ingestion with
    metadata provenance (doc_id, page_number, start_line, end_line, doc_version, doc_hash)
    and selected_doc_ids filtering.
    """

    def __init__(
        self,
        embed_fn: Optional[Callable[[List[str]], Any]] = None,
    ) -> None:
        self.chunks: List[DocumentChunk] = []
        self.documents: Dict[str, DocumentMetadata] = {}
        self._bm25: Optional[BM25Okapi] = None
        self._embed_fn: Optional[Callable[[List[str]], Any]] = embed_fn
        self.dense_available: bool = embed_fn is not None

    def set_embed_fn(self, embed_fn: Optional[Callable[[List[str]], Any]]) -> None:
        """Sets or updates the dense embedding function and updates dense availability status."""
        self._embed_fn = embed_fn
        self.dense_available = embed_fn is not None

    def add_document(self, metadata: DocumentMetadata, chunks: List[DocumentChunk]) -> int:
        """Stores a new document and its chunks in the repository, then rebuilds the index."""
        self.documents[metadata.doc_id] = metadata
        self.chunks.extend(chunks)
        self._rebuild_index()
        return len(chunks)

    def delete_document(self, doc_id: str) -> bool:
        """
        Removes a document and all its chunks from the repository.
        Returns True if removed, False if doc_id was not found.
        """
        target_id = None
        for d_id, doc in self.documents.items():
            if d_id == doc_id or doc.doc_name == doc_id or d_id.lower() == doc_id.lower():
                target_id = d_id
                break

        if target_id is None:
            # Check if any chunks match doc_id directly
            has_chunks = any(c.doc_id == doc_id or c.doc_name == doc_id for c in self.chunks)
            if not has_chunks:
                return False
            target_id = doc_id

        if target_id in self.documents:
            del self.documents[target_id]

        self.chunks = [
            c for c in self.chunks
            if c.doc_id != target_id and c.doc_name != target_id
        ]
        self._rebuild_index()
        return True

    def get_document_by_hash(self, file_hash: str) -> Optional[DocumentMetadata]:
        """Finds an existing document with the identical content hash."""
        for doc in self.documents.values():
            if doc.file_hash == file_hash:
                return doc
        return None

    def get_next_version_id(self, doc_name: str) -> str:
        """Computes the next version identifier (e.g. 'v1', 'v2') for a document name."""
        clean_name = doc_name.lower().strip()
        count = sum(1 for d in self.documents.values() if d.doc_name.lower().strip() == clean_name)
        return f"v{count + 1}"

    def set_selected_documents(self, doc_ids: List[str]) -> None:
        """Updates the selection state across all documents in the library."""
        selected_set = {d.strip().lower() for d in doc_ids}
        for d_id, doc in self.documents.items():
            doc.is_selected = (
                d_id.lower() in selected_set or doc.doc_name.lower() in selected_set
            )

    def get_selected_doc_ids(self) -> List[str]:
        """Returns the list of document IDs currently selected."""
        return [d_id for d_id, doc in self.documents.items() if doc.is_selected]

    def list_documents(self) -> List[Dict[str, Any]]:
        """Returns metadata for all documents ingested in the workspace."""
        if self.documents:
            return [doc.model_dump() for doc in self.documents.values()]

        # Fallback if chunks were ingested via legacy methods without explicit DocumentMetadata
        doc_map: Dict[str, Dict[str, Any]] = {}
        for c in self.chunks:
            d_id = c.doc_id
            if d_id not in doc_map:
                doc_map[d_id] = {
                    "doc_id": c.doc_id,
                    "doc_name": c.doc_name,
                    "file_type": "pdf" if c.doc_name.lower().endswith(".pdf") else "txt",
                    "chunk_count": 0,
                    "pages": set(),
                    "total_lines": 0,
                    "file_hash": c.doc_hash,
                    "version_id": c.doc_version,
                    "uploaded_at": "",
                    "is_selected": True,
                }
            doc_map[d_id]["chunk_count"] += 1
            doc_map[d_id]["pages"].add(c.page_number)
            doc_map[d_id]["total_lines"] = max(doc_map[d_id]["total_lines"], c.end_line)

        result: List[Dict[str, Any]] = []
        for d in doc_map.values():
            result.append({
                "doc_id": d["doc_id"],
                "doc_name": d["doc_name"],
                "file_type": d["file_type"],
                "chunk_count": d["chunk_count"],
                "page_count": len(d["pages"]),
                "total_lines": d["total_lines"],
                "file_hash": d["file_hash"],
                "version_id": d["version_id"],
                "uploaded_at": d["uploaded_at"],
                "is_selected": d["is_selected"],
            })
        return result

    def get_document_chunks(self, doc_id: str) -> List[DocumentChunk]:
        """Returns all chunks belonging to a document by doc_id or doc_name."""
        target = doc_id.lower().strip()
        return [
            c for c in self.chunks
            if c.doc_id.lower().strip() == target or c.doc_name.lower().strip() == target
        ]

    def ingest_text_document(
        self,
        doc_id: str,
        doc_name: str,
        pages: List[Tuple[int, str]],
        doc_version: str = "v1",
        doc_hash: str = "",
    ) -> int:
        """
        Ingests multi-page text documents (PDF/TXT) broken down into sliding window chunks
        with start_line and end_line tracking and 2-line overlap.
        """
        if not doc_hash:
            raw_text = "\n\n".join(text for _, text in pages)
            doc_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        added_chunks: List[DocumentChunk] = []
        total_lines_doc = 0

        for page_num, page_text in pages:
            lines = page_text.splitlines()
            page_total_lines = len(lines) if lines else 1
            total_lines_doc += page_total_lines

            # If page is compact, create a single chunk
            total_chars = sum(len(l) for l in lines)
            if total_chars <= 900 and len(lines) <= 16:
                chunk_text = "\n".join(lines).strip()
                if chunk_text:
                    added_chunks.append(
                        DocumentChunk(
                            chunk_id=f"{doc_id}_p{page_num}_c0",
                            doc_id=doc_id,
                            doc_name=doc_name,
                            page_number=page_num,
                            start_line=1,
                            end_line=page_total_lines,
                            section_header=f"Page {page_num}, Lines 1-{page_total_lines}",
                            text=chunk_text,
                            doc_version=doc_version,
                            doc_hash=doc_hash,
                        )
                    )
            else:
                # Sliding window with overlap
                curr_idx = 0
                chunk_idx = 0
                n_lines = len(lines)
                while curr_idx < n_lines:
                    while curr_idx < n_lines and not lines[curr_idx].strip():
                        curr_idx += 1
                    if curr_idx >= n_lines:
                        break

                    start_l = curr_idx + 1
                    window = []
                    char_count = 0
                    end_idx = curr_idx

                    while end_idx < n_lines:
                        l_str = lines[end_idx]
                        window.append(l_str)
                        char_count += len(l_str) + 1
                        end_idx += 1
                        if char_count >= 400 and ((not l_str.strip()) or (len(window) >= 8 and l_str.strip().endswith("."))):
                            break
                        if char_count >= 950 or len(window) >= 18:
                            break

                    while window and not window[-1].strip():
                        window.pop()
                        end_idx -= 1

                    if window:
                        end_l = start_l + len(window) - 1
                        c_text = "\n".join(window).strip()
                        if c_text:
                            added_chunks.append(
                                DocumentChunk(
                                    chunk_id=f"{doc_id}_p{page_num}_c{chunk_idx}",
                                    doc_id=doc_id,
                                    doc_name=doc_name,
                                    page_number=page_num,
                                    start_line=start_l,
                                    end_line=end_l,
                                    section_header=f"Page {page_num}, Lines {start_l}-{end_l}",
                                    text=c_text,
                                    doc_version=doc_version,
                                    doc_hash=doc_hash,
                                )
                            )
                            chunk_idx += 1

                    next_idx = max(curr_idx + 1, end_idx - 2)
                    if next_idx <= curr_idx:
                        next_idx = curr_idx + 1
                    curr_idx = next_idx

        metadata = DocumentMetadata(
            doc_id=doc_id,
            doc_name=doc_name,
            file_type="pdf" if doc_name.lower().endswith(".pdf") else "txt",
            page_count=len(pages),
            chunk_count=len(added_chunks),
            total_lines=total_lines_doc,
            file_hash=doc_hash,
            version_id=doc_version,
            uploaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            is_selected=True,
        )

        self.documents[doc_id] = metadata
        self.chunks.extend(added_chunks)
        self._rebuild_index()
        return len(added_chunks)

    def ingest_csv_tasks(self, doc_id: str, doc_name: str, csv_content: str) -> int:
        """Ingests structured CSV task records with row-level provenance and line locators."""
        doc_hash = hashlib.sha256(csv_content.encode("utf-8")).hexdigest()
        reader = csv.DictReader(io.StringIO(csv_content))
        added_chunks: List[DocumentChunk] = []

        for row_idx, row in enumerate(reader, start=1):
            row_str = " | ".join(f"{k}: {v}" for k, v in row.items() if v is not None)
            chunk = DocumentChunk(
                chunk_id=f"{doc_id}_row{row_idx}",
                doc_id=doc_id,
                doc_name=doc_name,
                page_number=row_idx,
                start_line=row_idx,
                end_line=row_idx,
                section_header=f"CSV Row {row_idx}",
                text=row_str,
                doc_version="v1",
                doc_hash=doc_hash,
            )
            added_chunks.append(chunk)

        metadata = DocumentMetadata(
            doc_id=doc_id,
            doc_name=doc_name,
            file_type="csv",
            page_count=len(added_chunks),
            chunk_count=len(added_chunks),
            total_lines=len(added_chunks),
            file_hash=doc_hash,
            version_id="v1",
            uploaded_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            is_selected=True,
        )

        self.documents[doc_id] = metadata
        self.chunks.extend(added_chunks)
        self._rebuild_index()
        return len(added_chunks)

    def _rebuild_index(self) -> None:
        """Rebuilds the BM25 lexical index over all indexed chunks with Vietnamese-English tokenizer."""
        if not self.chunks:
            self._bm25 = None
            return
        tokenized = [tokenize_vietnamese_english(c.text) for c in self.chunks]
        self._bm25 = BM25Okapi(tokenized)

    def search(
        self,
        query: str,
        top_k: int = 5,
        selected_doc_ids: Optional[List[str]] = None,
    ) -> List[DocumentChunk]:
        """
        Performs retrieval constrained by selected_doc_ids.
        - If selected_doc_ids is an empty list ([]): Returns [] (0 documents selected).
        - If selected_doc_ids is provided: Searches strictly within those documents.
        - If selected_doc_ids is None: Searches documents marked as is_selected in repository.
        """
        if not self.chunks:
            return []

        # 1. Filter eligible candidate chunks based on selected_doc_ids
        if selected_doc_ids is not None:
            if len(selected_doc_ids) == 0:
                # Rule: Empty selection must return empty, do NOT search everything
                return []
            target_ids = {d.strip().lower() for d in selected_doc_ids}
            eligible = [
                c for c in self.chunks
                if c.doc_id.lower() in target_ids or c.doc_name.lower() in target_ids
            ]
        else:
            selected_in_repo = {
                d_id.lower() for d_id, doc in self.documents.items() if doc.is_selected
            }
            if selected_in_repo:
                eligible = [
                    c for c in self.chunks
                    if c.doc_id.lower() in selected_in_repo or c.doc_name.lower() in selected_in_repo
                ]
            else:
                eligible = self.chunks

        if not eligible:
            return []

        # 2. Tokenize with enhanced Vietnamese-English tokenizer
        q_tokens = tokenize_vietnamese_english(query)
        if not q_tokens:
            return []

        # If eligible is all chunks, use cached _bm25; otherwise create ad-hoc BM25 over eligible
        if len(eligible) == len(self.chunks) and self._bm25:
            bm25_model = self._bm25
        else:
            tokenized_eligible = [tokenize_vietnamese_english(c.text) for c in eligible]
            bm25_model = BM25Okapi(tokenized_eligible)

        bm25_scores = list(bm25_model.get_scores(q_tokens))
        max_bm25 = max(bm25_scores) if len(bm25_scores) > 0 and max(bm25_scores) > 0 else 1.0

        q_set = set(q_tokens)

        # Lexical ranking (BM25 with token-overlap tie-breaker)
        STOP_WORDS = {
            "và", "hoặc", "của", "cho", "là", "ở", "tại", "có", "các", "những", "một", "trong",
            "được", "với", "này", "đó", "nào", "mấy", "gồm", "như", "gì", "thế_nào", "sao",
            "thì", "đã", "sẽ", "đang", "bởi", "ra", "vào", "lại",
            "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "what", "which", "how", "it", "this", "that",
        }
        content_q_set = {t for t in q_set if t not in STOP_WORDS}
        effective_q_set = content_q_set if content_q_set else q_set

        overlap_map = {}
        for i, c in enumerate(eligible):
            c_toks = set(tokenize_vietnamese_english(c.text))
            overlap_map[c.chunk_id] = len(effective_q_set & c_toks) / max(1, len(effective_q_set))

        lexical_scores = [
            0.6 * (float(bm25_scores[i]) / float(max_bm25)) + 0.4 * overlap_map[eligible[i].chunk_id]
            for i in range(len(eligible))
        ]

        # Downweight Table of Contents / List of Figures when user seeks substantive content/explanation
        query_asks_content = any(
            w in query.lower()
            for w in ["giải thích", "chi tiết", "nội dung", "như thế nào", "là gì", "yêu cầu", "tính năng", "feature", "explain", "describe", "detail", "how", "what"]
        ) and not any(w in query.lower() for w in ["mục lục", "table of contents", "danh mục"])

        for i, c in enumerate(eligible):
            c_text_lower = c.text.lower()
            is_toc = bool(
                re.search(r"(\.\s*){4,}\s*\d+", c.text)
                or "list of figures" in c_text_lower
                or "table of contents" in c_text_lower
                or ("mục lục" in c_text_lower and re.search(r"\d+$", c.text.strip()))
            )
            if is_toc and query_asks_content:
                bm25_scores[i] *= 0.15
                lexical_scores[i] *= 0.15

        bm25_sorted_indices = sorted(
            range(len(eligible)),
            key=lambda i: (float(bm25_scores[i]), lexical_scores[i]),
            reverse=True,
        )
        rank_bm25 = {eligible[idx].chunk_id: r for r, idx in enumerate(bm25_sorted_indices, start=1)}
        norm_bm25_map = {eligible[i].chunk_id: float(bm25_scores[i]) / float(max_bm25) for i in range(len(eligible))}

        # 3. Dense Vector Search (if embed_fn is available)
        dense_scores_map: Dict[str, float] = {}
        rank_dense: Dict[str, int] = {}

        if self.dense_available and callable(self._embed_fn):
            try:
                q_vec = self._embed_fn([query])
                if q_vec is not None and len(q_vec) > 0:
                    c_texts = [c.text for c in eligible]
                    c_vecs = self._embed_fn(c_texts)
                    if c_vecs is not None and len(c_vecs) == len(eligible):
                        import numpy as np
                        q_arr = np.asarray(q_vec[0], dtype=np.float32)
                        c_arr = np.asarray(c_vecs, dtype=np.float32)
                        q_norm = np.linalg.norm(q_arr)
                        c_norms = np.linalg.norm(c_arr, axis=1)
                        denom = np.maximum(c_norms * q_norm, 1e-9)
                        sims = np.dot(c_arr, q_arr) / denom
                        dense_scores_map = {eligible[i].chunk_id: float(sims[i]) for i in range(len(eligible))}
                        dense_sorted_indices = sorted(range(len(eligible)), key=lambda i: sims[i], reverse=True)
                        rank_dense = {eligible[idx].chunk_id: r for r, idx in enumerate(dense_sorted_indices, start=1)}
            except Exception:
                dense_scores_map = {}
                rank_dense = {}

        # 4. Reciprocal Rank Fusion (RRF) & Absolute Relevance Score Calibration
        scored_chunks: List[DocumentChunk] = []

        for chunk in eligible:
            cid = chunk.chunk_id
            r_bm25 = rank_bm25[cid]
            b_norm = norm_bm25_map[cid]
            overlap = overlap_map[cid]
            lex_score = 0.6 * b_norm + 0.4 * overlap

            c_copy = chunk.model_copy()
            c_copy.bm25_score = round(b_norm, 4)

            if cid in rank_dense:
                r_d = rank_dense[cid]
                d_sim = dense_scores_map[cid]
                c_copy.dense_score = round(d_sim, 4)
                # Standard RRF formula
                rrf = 1.0 / (60.0 + r_bm25) + 1.0 / (60.0 + r_d)
                # Calibrated absolute score in [0.0, 1.0]
                calibrated_score = max(d_sim, lex_score)
                c_copy.score = round(min(1.0, max(0.0, calibrated_score)), 4)
            else:
                c_copy.dense_score = 0.0
                rrf = 1.0 / (60.0 + r_bm25)
                c_copy.score = round(min(1.0, max(0.0, lex_score)), 4)

            c_copy.rrf_score = round(rrf, 6)
            scored_chunks.append(c_copy)

        # 5. Pinpoint Reranker: Detect specific entities, numbers, dates, or exact phrases
        q_lower = query.lower()
        is_temporal_q = any(w in q_lower for w in ["khi nào", "hạn chót", "hạn nộp", "thời hạn", "deadline", "ngày", "tuần", "tháng", "when", "due"])
        is_numeric_q = any(w in q_lower for w in ["bao nhiêu", "mấy", "tỷ lệ", "phần trăm", "điểm", "trang", "pages", "how many", "count"])
        clean_q_phrase = re.sub(r"[^\w\s]", "", q_lower).strip()

        for c_copy in scored_chunks:
            c_text_lower = c_copy.text.lower()
            pinpoint_bonus = 0.0

            # Signal A: Exact query phrase substring match (clean without punctuation)
            if len(clean_q_phrase) >= 6 and clean_q_phrase in c_text_lower:
                pinpoint_bonus += 0.15

            # Signal B: Temporal entities (explicit dates like DD/MM/YYYY or 'ngày X')
            if is_temporal_q:
                has_date = bool(re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|ngày\s*\d{1,2}|tháng\s*\d{1,2})\b", c_copy.text))
                has_deadline_kw = any(w in c_text_lower for w in ["deadline", "hạn nộp", "thời hạn", "hạn chót", "submission", "due"])
                if has_date or has_deadline_kw:
                    pinpoint_bonus += 0.12

            # Signal C: Numeric / Page entities (ranges like '12-18 trang', percentages '%')
            if is_numeric_q:
                has_number_unit = bool(re.search(r"\b\d+([–-]\d+)?\s*(trang|pages|%|điểm|ngày|days|tuần)\b", c_copy.text))
                has_number = bool(re.search(r"\b\d+([–-]\d+)?\b", c_copy.text))
                if has_number_unit:
                    pinpoint_bonus += 0.15
                elif has_number:
                    pinpoint_bonus += 0.08

            c_copy.pinpoint_score = round(pinpoint_bonus, 4)
            c_copy.score = round(min(1.0, c_copy.score + pinpoint_bonus), 4)

        # Sort by Pinpoint bonus first, then by pure RRF score descending
        scored_chunks.sort(key=lambda x: (x.pinpoint_score, x.rrf_score), reverse=True)
        return scored_chunks[:top_k]

    def build_page_lookup(self) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """
        Constructs page-level concatenated text map with line locators,
        hash, and version metadata for deterministic citation verification.
        """
        lookup: Dict[Tuple[str, int], Dict[str, Any]] = {}
        for c in self.chunks:
            key = (c.doc_id, c.page_number)
            if key not in lookup:
                lookup[key] = {
                    "text": c.text,
                    "full_page_text": c.text,
                    "total_lines": c.end_line,
                    "doc_version": c.doc_version,
                    "version_id": c.doc_version,
                    "doc_hash": c.doc_hash,
                    "lines": (c.start_line, c.end_line),
                }
            else:
                lookup[key]["text"] = (lookup[key]["text"] + "\n" + c.text).strip()
                lookup[key]["full_page_text"] = lookup[key]["text"]
                lookup[key]["total_lines"] = max(lookup[key]["total_lines"], c.end_line)
        return lookup

    def seed_demo_workspace(self) -> None:
        """Seeds default CSC10014 project brief and workspace data with line locators."""
        self.ingest_text_document(
            doc_id="Project_Brief.pdf",
            doc_name="Project_Brief.pdf",
            pages=[
                (
                    3,
                    "Minimum System Requirements: R1 Problem boundary, R2 Deterministic capability, "
                    "R3 Data retrieval capability, R4 AI-enabled capability, R5 Routing orchestration.\n"
                    "All R2 algorithms must be 100% pure Python standard library without external dependencies.",
                ),
                (
                    6,
                    "Submission Package: 01 Engineering Report (12-18 pages recommended), "
                    "02 Source Repository and Demo, 03 Architecture Pack, 04 Evaluation Pack.\n"
                    "Late submissions without prior approval will be subject to deduction.",
                ),
            ],
            doc_version="v1",
        )


# Backward compatibility aliases
HybridWorkspaceIndex = WorkspaceRepository
workspace_repository = WorkspaceRepository()

__all__ = [
    "HybridWorkspaceIndex",
    "WorkspaceRepository",
    "workspace_repository",
    "tokenize_vietnamese_english",
]
