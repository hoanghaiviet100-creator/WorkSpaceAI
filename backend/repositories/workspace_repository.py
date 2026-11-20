import base64
import binascii
import csv
from datetime import datetime
import hashlib
import io
import re
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
import numpy as np
from rank_bm25 import BM25Okapi
from backend.core.schemas import DocumentChunk, DocumentMetadata


STOP_WORDS = {
    "và", "hoặc", "của", "cho", "là", "ở", "tại", "có", "các", "những", "một", "trong",
    "được", "với", "này", "đó", "nào", "mấy", "gồm", "như", "gì", "thế", "sao",
    "thì", "đã", "sẽ", "đang", "bởi", "ra", "vào", "lại",
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "what", "which",
    "how", "who", "when", "where", "why", "it", "this", "that",
}


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
        self._embedding_index_id: str | None = None
        self._semantic_weight = 0.65
        self._vectors: dict[str, np.ndarray] = {}
        self._vector_lock = Lock()

    def set_embed_fn(
        self, embed_fn: Optional[Callable[[List[str]], Any]], *,
        index_id: str | None = None, semantic_weight: float = 0.65,
    ) -> None:
        with self._vector_lock:
            if embed_fn != self._embed_fn or index_id != self._embedding_index_id:
                self._vectors.clear()
            self._embed_fn = embed_fn
            self._embedding_index_id = index_id
            self._semantic_weight = semantic_weight
            self.dense_available = embed_fn is not None

    def add_document(self, metadata: DocumentMetadata, chunks: List[DocumentChunk]) -> int:
        """Stores a new document and its chunks in the repository, then rebuilds the index."""
        self.documents[metadata.doc_id] = metadata
        self.chunks.extend(chunks)
        self._rebuild_index(chunks)
        return len(chunks)

    def delete_document(self, doc_id: str) -> bool:
        """
        Removes a document and all its chunks from the repository.
        Returns True if removed, False if doc_id was not found.
        """
        resolved = self._resolve_document_ids([doc_id])
        if len(resolved) != 1:
            return False
        target_id = next(iter(resolved))

        if target_id in self.documents:
            del self.documents[target_id]

        self.chunks = [
            c for c in self.chunks
            if c.doc_id != target_id
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
        selected_set = self._resolve_document_ids(doc_ids)
        for d_id, doc in self.documents.items():
            doc.is_selected = (
                d_id in selected_set
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
        targets = self._resolve_document_ids([doc_id])
        return [
            c for c in self.chunks
            if c.doc_id in targets
        ]

    def _resolve_document_ids(self, values: List[str]):
        """Stable IDs win over renamed filenames; legacy names resolve only unambiguously."""
        records = {doc_id: document.doc_name for doc_id, document in self.documents.items()}
        for chunk in self.chunks:
            records.setdefault(chunk.doc_id, chunk.doc_name)
        resolved = set()
        for value in values:
            target = value.strip().lower()
            exact = [doc_id for doc_id in records if doc_id.lower() == target]
            matches = exact or [doc_id for doc_id, name in records.items() if name.strip().lower() == target]
            if len(matches) == 1:
                resolved.add(matches[0])
        return resolved

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
        self._rebuild_index(added_chunks)
        return len(added_chunks)

    def ingest_csv(self, doc_id: str, doc_name: str, csv_content: str) -> int:
        """Index CSV rows with their source positions."""
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
        self._rebuild_index(added_chunks)
        return len(added_chunks)

    def _rebuild_index(self, added: List[DocumentChunk] | None = None) -> None:
        """Rebuilds the BM25 lexical index over all indexed chunks with Vietnamese-English tokenizer."""
        if not self.chunks:
            self._bm25 = None
        else:
            tokenized = [tokenize_vietnamese_english(c.text) for c in self.chunks]
            self._bm25 = BM25Okapi(tokenized)
        with self._vector_lock:
            if added is None and self._vectors:
                retained = {self._vector_key(chunk.text) for chunk in self.chunks}
                self._vectors = {key: row for key, row in self._vectors.items() if key in retained}
            if added and self._embed_fn:
                self._index_vectors(added)

    @staticmethod
    def _vector_key(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _index_vectors(self, chunks: List[DocumentChunk], width: int | None = None) -> list[str] | None:
        """Populate missing vectors while the caller holds the index lock."""
        if self._embed_fn is None:
            return None
        keys = [self._vector_key(chunk.text) for chunk in chunks]
        missing = {
            key: chunk.text for key, chunk in zip(keys, chunks)
            if key not in self._vectors or (width is not None and self._vectors[key].size != width)
        }
        if missing:
            try:
                rows = np.asarray(self._embed_fn(list(missing.values())), dtype=np.float32)
            except Exception:
                return None
            if (rows.ndim != 2 or rows.shape[0] != len(missing) or not rows.shape[1]
                or (width is not None and rows.shape[1] != width) or not np.isfinite(rows).all()):
                return None
            self._vectors.update(zip(missing, rows))
        return keys

    def index_existing_passages(self) -> bool:
        """Backfill saved libraries and report whether the snapshot needs updating."""
        with self._vector_lock:
            if self._embedding_index_id is None:
                return False
            count = len(self._vectors)
            self._index_vectors(self.chunks)
            return len(self._vectors) > count

    def restore_embeddings(self, snapshot: object) -> None:
        with self._vector_lock:
            self._vectors.clear()
            if (
                self._embedding_index_id is None or not isinstance(snapshot, dict)
                or snapshot.get("encoder") != self._embedding_index_id
                or not isinstance(snapshot.get("vectors"), dict)
            ):
                return
            for key, encoded in snapshot["vectors"].items():
                try:
                    row = np.frombuffer(base64.b64decode(encoded, validate=True), dtype="<f4")
                except (binascii.Error, ValueError, TypeError):
                    continue
                if row.size and np.isfinite(row).all():
                    self._vectors[key] = row

    def snapshot_embeddings(self) -> dict | None:
        with self._vector_lock:
            if self._embedding_index_id is None or not self._vectors:
                return None
            keys = {self._vector_key(chunk.text) for chunk in self.chunks}
            return {
                "encoder": self._embedding_index_id,
                "vectors": {
                    key: base64.b64encode(self._vectors[key].astype("<f4", copy=False).tobytes()).decode("ascii")
                    for key in sorted(keys & self._vectors.keys())
                },
            }

    def _semantic_scores(self, chunks: List[DocumentChunk], query: str) -> tuple[np.ndarray, float] | None:
        with self._vector_lock:
            if self._embed_fn is None:
                return None
            try:
                vectors = np.asarray(self._embed_fn([query]), dtype=np.float32)
            except Exception:
                return None
            if vectors.ndim != 2 or vectors.shape[0] != 1 or not np.isfinite(vectors).all():
                return None
            query_vector = vectors[0]
            if not np.any(query_vector):
                return None
            keys = self._index_vectors(chunks, query_vector.size)
            if keys is None:
                return None
            rows = np.stack([self._vectors[key] for key in keys])
            weight = self._semantic_weight
        denominator = np.maximum(np.linalg.norm(rows, axis=1) * np.linalg.norm(query_vector), 1e-9)
        return np.clip((rows @ query_vector) / denominator, 0.0, 1.0), weight

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
            target_ids = self._resolve_document_ids(selected_doc_ids)
            eligible = [
                c for c in self.chunks
                if c.doc_id in target_ids
            ]
        else:
            selected_in_repo = {
                d_id for d_id, doc in self.documents.items() if doc.is_selected
            }
            if selected_in_repo:
                eligible = [
                    c for c in self.chunks
                    if c.doc_id in selected_in_repo
                ]
            else:
                eligible = self.chunks

        if not eligible:
            return []

        # 2. Tokenize with enhanced Vietnamese-English tokenizer
        q_tokens = [
            token for token in tokenize_vietnamese_english(query)
            if any(word not in STOP_WORDS for word in token.split("_"))
        ]
        if not q_tokens:
            return []

        # If eligible is all chunks, use cached _bm25; otherwise create ad-hoc BM25 over eligible
        if len(eligible) == len(self.chunks) and self._bm25:
            bm25_model = self._bm25
        else:
            tokenized_eligible = [tokenize_vietnamese_english(c.text) for c in eligible]
            bm25_model = BM25Okapi(tokenized_eligible)

        bm25_scores = list(bm25_model.get_scores(q_tokens))
        max_bm25 = max(bm25_scores)
        if max_bm25 <= 0:
            max_bm25 = 1.0
        q_terms = set(re.findall(r"\w+", query.lower())) - STOP_WORDS
        if not q_terms:
            return []

        # Downweight Table of Contents / List of Figures when user seeks substantive content/explanation
        query_asks_content = any(
            w in query.lower()
            for w in ["giải thích", "chi tiết", "nội dung", "như thế nào", "là gì", "yêu cầu", "tính năng", "feature", "explain", "describe", "detail", "how", "what"]
        ) and not any(w in query.lower() for w in ["mục lục", "table of contents", "danh mục"])

        lexical_scores = []
        penalties = []
        for i, chunk in enumerate(eligible):
            text = chunk.text.lower()
            is_toc = query_asks_content and (
                re.search(r"(\.\s*){4,}\s*\d+", text)
                or "list of figures" in text or "table of contents" in text
                or ("mục lục" in text and re.search(r"\d+$", text.rstrip()))
            )
            penalty = 0.15 if is_toc else 1.0
            penalties.append(penalty)
            bm25_scores[i] *= penalty
            lexical_scores.append(penalty * len(q_terms.intersection(re.findall(r"\w+", text))) / len(q_terms))

        keyword_order = sorted(
            range(len(eligible)),
            key=lambda i: (float(bm25_scores[i]), lexical_scores[i]),
            reverse=True,
        )
        keyword_rank = {index: rank for rank, index in enumerate(keyword_order, start=1)}
        semantic_result = self._semantic_scores(eligible, query)
        dense_scores = [0.0] * len(eligible)
        dense_rank = {}
        weight = 0.0
        if semantic_result is not None:
            similarities, weight = semantic_result
            dense_scores = [float(value) * penalty for value, penalty in zip(similarities, penalties)]
            dense_order = sorted(range(len(eligible)), key=dense_scores.__getitem__, reverse=True)
            dense_rank = {index: rank for rank, index in enumerate(dense_order, start=1)}

        # 5. Pinpoint Reranker: Detect specific entities, numbers, dates, or exact phrases
        q_lower = query.lower()
        is_temporal_q = any(w in q_lower for w in ["khi nào", "hạn chót", "hạn nộp", "thời hạn", "deadline", "ngày", "tuần", "tháng", "when", "due"])
        is_numeric_q = any(w in q_lower for w in ["bao nhiêu", "mấy", "tỷ lệ", "phần trăm", "điểm", "trang", "pages", "how many", "count"])
        clean_q_phrase = re.sub(r"[^\w\s]", "", q_lower).strip()

        ranked = []
        for i, chunk in enumerate(eligible):
            lexical = lexical_scores[i]
            semantic = dense_scores[i]
            if not lexical and not semantic:
                continue
            c_copy = chunk.model_copy()
            c_copy.bm25_score = round(float(bm25_scores[i]) / max_bm25, 4)
            c_copy.dense_score = round(semantic, 4)
            rrf = 1.0 / (60.0 + keyword_rank[i])
            if i in dense_rank:
                rrf += 1.0 / (60.0 + dense_rank[i])
            c_copy.rrf_score = round(rrf, 6)
            # Keep the relevance threshold on the strongest signal; both signals rank the candidates.
            strength = max(lexical, semantic)
            blended = weight * semantic + (1.0 - weight) * lexical
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

            # Relevance Gate: Pinpoint bonus applies strongly to relevant candidates,
            # while scaling down on completely ungrounded candidates (score < 0.10) to prevent noise takeover
            if strength < 0.10:
                pinpoint_bonus *= 0.2

            c_copy.pinpoint_score = round(pinpoint_bonus, 4)
            c_copy.score = round(min(1.0, strength + pinpoint_bonus), 4)
            ranked.append((blended + pinpoint_bonus, c_copy))

        ranked.sort(key=lambda item: (item[0], item[1].dense_score, item[1].rrf_score), reverse=True)
        return [chunk for _, chunk in ranked[:top_k]]

    def build_page_lookup(self) -> Dict[Tuple[str, int], Dict[str, Any]]:
        """
        Constructs page-level deduplicated text map with line locators,
        hash, and version metadata for deterministic citation verification.
        Eliminates duplicate boundary lines caused by 2-line sliding window overlap.
        Registers case-insensitive and extension-tolerant doc_id aliases.
        """
        # Step 1: Collect ordered lines per (doc_id, page_number)
        page_lines_map: Dict[Tuple[str, int], Dict[int, str]] = {}
        page_meta_map: Dict[Tuple[str, int], Dict[str, Any]] = {}

        for c in self.chunks:
            p_key = (c.doc_id, c.page_number)
            if p_key not in page_lines_map:
                page_lines_map[p_key] = {}
                page_meta_map[p_key] = {
                    "doc_version": c.doc_version,
                    "version_id": c.doc_version,
                    "doc_hash": c.doc_hash,
                    "doc_name": c.doc_name,
                    "doc_id": c.doc_id,
                }

            lines = c.text.splitlines()
            start_l = c.start_line if c.start_line is not None else 1
            for idx, line in enumerate(lines):
                line_no = start_l + idx
                # Store or update line content (deduplicating overlapping lines seamlessly)
                page_lines_map[p_key][line_no] = line

        # Step 2: Assemble clean, non-duplicated full page texts
        lookup: Dict[Tuple[str, int], Dict[str, Any]] = {}

        for (doc_id, page_num), lines_dict in page_lines_map.items():
            sorted_line_nos = sorted(lines_dict.keys())
            windows: list[tuple[int, list[str]]] = []
            for line_no in sorted_line_nos:
                if not windows or line_no != windows[-1][0] + len(windows[-1][1]):
                    windows.append((line_no, []))
                windows[-1][1].append(lines_dict[line_no])
            if sorted_line_nos:
                clean_page_text = "\n".join(lines_dict[ln] for ln in sorted_line_nos)
                min_line = sorted_line_nos[0]
                max_line = sorted_line_nos[-1]
            else:
                clean_page_text = ""
                min_line, max_line = 1, 1

            meta = page_meta_map.get((doc_id, page_num), {})
            entry = {
                "text": clean_page_text,
                "full_page_text": clean_page_text,
                "total_lines": max_line,
                "doc_version": meta.get("doc_version", "v1"),
                "version_id": meta.get("doc_version", "v1"),
                "doc_hash": meta.get("doc_hash", ""),
                "lines": (min_line, max_line),
                "windows": windows,
            }

            # Register standard key
            lookup[(doc_id, page_num)] = entry

            # Register alias keys: doc_name, case-insensitive, and without extension
            doc_name = meta.get("doc_name", doc_id)
            alias_keys = [
                (doc_name, page_num),
                (doc_id.lower(), page_num),
                (doc_name.lower(), page_num),
            ]
            if "." in doc_id:
                no_ext = doc_id.rsplit(".", 1)[0]
                alias_keys.extend([(no_ext, page_num), (no_ext.lower(), page_num)])
            if "." in doc_name:
                no_ext_name = doc_name.rsplit(".", 1)[0]
                alias_keys.extend([(no_ext_name, page_num), (no_ext_name.lower(), page_num)])

            for ak in alias_keys:
                if ak not in lookup:
                    lookup[ak] = entry

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
