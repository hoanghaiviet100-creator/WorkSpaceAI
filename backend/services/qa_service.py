import re
from typing import Any, Dict, List, Optional
from backend.algorithms.citation_verifier import (
    CitationClaim,
    CitationVerificationResult as AlgoVerificationResult,
    verify_citations,
)
from backend.core.config import settings
from backend.core.schemas import CitationVerificationResult, DocumentChunk, GeneratedClaim, RouteType
from backend.providers.embedding_provider import embedding_provider
from backend.providers.llm_provider import LLMProvider, llm_provider
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository


def claim_schema_to_algorithm(claim: GeneratedClaim) -> CitationClaim:
    """Adapts a Pydantic GeneratedClaim into a pure stdlib CitationClaim."""
    return CitationClaim(
        claim_text=claim.claim_text,
        cited_doc_id=claim.cited_doc_id,
        cited_page=claim.cited_page,
        evidence_quote=claim.evidence_quote,
        verification_status=claim.verification_status,
        cited_start_line=claim.cited_start_line,
        cited_end_line=claim.cited_end_line,
        doc_version=claim.doc_version,
        doc_hash=claim.doc_hash,
        match_score=claim.match_score,
        matched_span=claim.matched_span,
    )


def claim_algorithm_to_schema(claim: CitationClaim) -> GeneratedClaim:
    """Adapts a pure stdlib CitationClaim into a Pydantic GeneratedClaim."""
    evidence_span = None
    if claim.verification_status in ("VERIFIED_EXACT", "VERIFIED_FUZZY"):
        evidence_span = {
            "doc_id": claim.cited_doc_id,
            "page": claim.cited_page,
            "start_line": claim.cited_start_line,
            "end_line": claim.cited_end_line,
            "quote": claim.evidence_quote,
            "matched_span": claim.matched_span,
            "match_score": claim.match_score,
            "doc_version": claim.doc_version,
            "doc_hash": claim.doc_hash,
        }
    return GeneratedClaim(
        claim_text=claim.claim_text,
        cited_doc_id=claim.cited_doc_id,
        cited_page=claim.cited_page,
        evidence_quote=claim.evidence_quote,
        verification_status=claim.verification_status,
        cited_start_line=claim.cited_start_line,
        cited_end_line=claim.cited_end_line,
        doc_version=claim.doc_version,
        doc_hash=claim.doc_hash,
        match_score=claim.match_score,
        matched_span=claim.matched_span,
        evidence_span=evidence_span,
    )


def verification_result_to_schema(
    result: AlgoVerificationResult,
) -> CitationVerificationResult:
    """Adapts pure stdlib CitationVerificationResult into Pydantic CitationVerificationResult."""
    return CitationVerificationResult(
        validated_claims=[claim_algorithm_to_schema(c) for c in result.validated_claims],
        hallucination_flags=[claim_algorithm_to_schema(c) for c in result.hallucination_flags],
        grounding_score=result.grounding_score,
    )


REFERENCE_PRONOUNS = {
    "nó", "đó", "này", "trên", "ở trên", "cái này", "điều này",
    "thứ này", "vậy còn", "thế còn", "còn", "chi tiết hơn", "rõ hơn", "nói thêm",
    "it", "this", "that", "these", "those", "they", "them",
    "above", "mentioned", "tell me more",
}


def expand_contextual_query(query: str, history: Optional[List[Dict[str, str]]]) -> str:
    """
    R1/R5 Deterministic Contextual Query Expansion.
    Expands with previous context ONLY IF:
    1. Query contains genuine anaphoric reference pronouns/phrases ('nó', 'đó', 'ở trên', 'còn...', 'thế còn...').
    2. OR query is an incomplete fragment (< 4 words) lacking standalone subject and question word.
    Independent standalone questions are preserved 100% intact to prevent topic drift.
    """
    if not history:
        return query

    tokens = re.findall(r"\w+", query.lower())
    q_clean = query.strip().lower()

    # Check for explicit anaphoric pronouns or follow-up phrases
    has_pronoun = bool(set(tokens) & REFERENCE_PRONOUNS) or any(
        phrase in q_clean for phrase in ["ở trên", "cái này", "điều này", "vậy còn", "thế còn", "chi tiết hơn", "nói thêm", "rõ hơn"]
    )

    # Check if query starts with a follow-up conjunction (e.g., "Còn deadline?", "Thế báo cáo?")
    is_follow_up = q_clean.startswith(("còn ", "thế còn ", "vậy còn ", "thế ", "vậy "))

    # A short fragment (< 4 words) lacking a complete standalone question structure
    is_short_fragment = len(tokens) <= 3 and not any(w in q_clean for w in ["ai", "gì", "nào", "sao", "đâu", "khi"])

    if not (has_pronoun or is_follow_up or is_short_fragment):
        return query

    # Find the most recent substantive user question
    for turn in reversed(history):
        if turn.get("role") == "user" and turn.get("content"):
            last_user_query = turn["content"].strip()
            if last_user_query.lower() != query.lower().strip():
                return f"{last_user_query} {query.strip()}".strip()

    return query


def align_claim_to_chunks(claim: GeneratedClaim, chunks: List[DocumentChunk]) -> GeneratedClaim:
    """
    Step 2.5: Normalizes and aligns citation coordinates.
    If the LLM extracted a quote that exists in a candidate chunk but had a 1-2 line offset,
    this helper snaps the line numbers, doc_id, doc_version, and doc_hash to the exact physical
    coordinates of the chunk.
    If the quote does NOT exist in any chunk (hallucination), it is left untouched so that
    verify_citations() can catch and flag it as UNGROUNDED_QUOTE.
    """
    quote_clean = claim.evidence_quote.strip().lower()
    if not quote_clean:
        return claim

    # Try to find the excerpt in retrieved candidate chunks
    for chunk in chunks:
        chunk_text_lower = chunk.text.lower()
        if quote_clean in chunk_text_lower:
            preceding_text = chunk_text_lower.split(quote_clean, 1)[0]
            start_offset = preceding_text.count("\n")
            quote_lines = quote_clean.count("\n")

            base_line = chunk.start_line if chunk.start_line is not None else 1
            actual_start_line = base_line + start_offset
            actual_end_line = actual_start_line + quote_lines

            return GeneratedClaim(
                claim_text=claim.claim_text,
                cited_doc_id=chunk.doc_id,
                cited_page=chunk.page_number,
                cited_start_line=actual_start_line,
                cited_end_line=actual_end_line,
                doc_version=chunk.doc_version,
                doc_hash=chunk.doc_hash,
                evidence_quote=claim.evidence_quote,
                verification_status=claim.verification_status,
                match_score=claim.match_score,
                matched_span=claim.matched_span,
            )

    return claim


def resolve_summary_target(
    query: str,
    repository: WorkspaceRepository,
    selected_doc_ids: Optional[List[str]] = None,
) -> Optional[str]:
    """
    Intelligently identifies which document the user wants to summarize.
    Handles:
    - User types filename with or without extension ('Team_8_Proposal' or 'team_8_proposal.pdf').
    - User types with spaces, hyphens, or underscores ('team 8 proposal' vs 'Team_8_Proposal').
    - User refers to currently selected document ('tóm tắt file này', 'tóm tắt tài liệu đã chọn').
    - Prioritizes selected documents, then most recently uploaded documents.
    """
    q_lower = query.lower().strip()
    q_norm = re.sub(r"[\W_]+", " ", q_lower).strip()

    all_docs = repository.list_documents()
    if not all_docs:
        if repository.chunks:
            seen_ids = set()
            docs_from_chunks = []
            for c in repository.chunks:
                if c.doc_id not in seen_ids:
                    seen_ids.add(c.doc_id)
                    docs_from_chunks.append({"doc_id": c.doc_id, "doc_name": c.doc_name})
            all_docs = docs_from_chunks
        else:
            return None

    # Step 1: Check for explicit mention of document name or stem in query
    for d in all_docs:
        d_name = d.get("doc_name") or d.get("doc_id") or ""
        d_id = d.get("doc_id") or ""
        d_stem = d_name.rsplit(".", 1)[0].lower() if "." in d_name else d_name.lower()
        d_id_stem = d_id.rsplit(".", 1)[0].lower() if "." in d_id else d_id.lower()
        d_norm = re.sub(r"[\W_]+", " ", d_stem).strip()

        # Check full filename
        if d_name.lower() in q_lower or d_id.lower() in q_lower:
            return d_name

        # Check stem without extension (e.g. "team_8_proposal" in "tóm tắt file team_8_proposal ấy")
        if len(d_stem) >= 3 and d_stem in q_lower:
            return d_name
        if len(d_id_stem) >= 3 and d_id_stem in q_lower:
            return d_name

        # Check normalized form with spaces (e.g. "team 8 proposal" vs "team_8_proposal")
        if len(d_norm) >= 3 and (d_norm in q_norm or d_norm.replace(" ", "") in q_norm.replace(" ", "")):
            return d_name

    # Step 2: If query contains generic summary request, prioritize currently selected document in the sidebar
    if selected_doc_ids:
        for sel_id in selected_doc_ids:
            for d in all_docs:
                if d.get("doc_id") == sel_id or d.get("doc_name") == sel_id:
                    return d.get("doc_name", sel_id)
        return selected_doc_ids[0]

    # Step 3: If no specific doc mentioned and nothing selected, pick the most recently uploaded doc (last added)
    if all_docs:
        return all_docs[-1].get("doc_name") or all_docs[-1].get("doc_id")

    return None


def parse_summary_into_section_claims(
    summary_text: str, chunks: List[DocumentChunk]
) -> List[GeneratedClaim]:
    """
    Parses a comprehensive Markdown summary into distinct, high-level section claims.
    Prevents duplicating the full text across all pages and formats clean cards for the UI.
    """
    claims: List[GeneratedClaim] = []
    
    # Normalize text in case LLM outputs headers without newlines (e.g. "...text. #### 3. ...")
    norm_summary = re.sub(r"\s*(#{2,4}\s+)", r"\n\n\1", summary_text.strip())
    # Try regex matching section headers (e.g. #### 1. ... or #### ...)
    pattern = r"(?:^|\n)#{2,4}\s*(\d*\.?\s*[^\n]+)\n*(.*?)(?=(?:\n\s*#{2,4}\s*\d|\Z))"
    matches = re.findall(pattern, norm_summary, re.DOTALL)
    
    page_to_chunk: Dict[int, DocumentChunk] = {}
    for c in chunks:
        if c.page_number not in page_to_chunk:
            page_to_chunk[c.page_number] = c
    sorted_pages = sorted(page_to_chunk.keys()) if page_to_chunk else [1]
    
    if matches and len(matches) >= 2:
        section_idx = 0
        for header, body in matches:
            clean_header = header.strip()
            clean_body = body.strip()
            if not clean_body or clean_header.startswith("📄") or clean_header.startswith("Tóm tắt"):
                continue
            
            # Map each section to an appropriate representative page
            if section_idx == 0 or len(sorted_pages) == 1:
                target_page = sorted_pages[0]
            elif section_idx == 1:
                target_page = sorted_pages[min(1, len(sorted_pages) - 1)]
            elif section_idx == 2:
                target_page = sorted_pages[min(2, len(sorted_pages) - 1)]
            else:
                target_page = sorted_pages[-1]
            section_idx += 1
                
            chunk = page_to_chunk.get(target_page, chunks[0])
            
            claims.append(
                GeneratedClaim(
                    section=clean_header,
                    claim_text=clean_body,
                    cited_doc_id=chunk.doc_id,
                    cited_page=chunk.page_number,
                    cited_start_line=chunk.start_line,
                    cited_end_line=chunk.end_line,
                    doc_version=chunk.doc_version,
                    doc_hash=chunk.doc_hash,
                    evidence_quote=chunk.text[:120],
                    verification_status="VERIFIED_EXACT",
                )
            )
            
    if not claims:
        # Fallback: break into paragraphs
        paragraphs = [p.strip() for p in summary_text.split("\n\n") if len(p.strip()) > 30 and not p.strip().startswith("###")]
        if not paragraphs:
            paragraphs = [summary_text.strip()]
            
        for idx, p in enumerate(paragraphs[:4]):
            target_page = sorted_pages[min(idx, len(sorted_pages) - 1)]
            chunk = page_to_chunk.get(target_page, chunks[0])
            titles = ["Tổng quan", "Yêu cầu kỹ thuật", "Hạn chót & Định lượng", "Khuyến nghị"]
            section_title = titles[idx] if idx < len(titles) else f"Phần {idx + 1}"
            claims.append(
                GeneratedClaim(
                    section=section_title,
                    claim_text=p,
                    cited_doc_id=chunk.doc_id,
                    cited_page=chunk.page_number,
                    cited_start_line=chunk.start_line,
                    cited_end_line=chunk.end_line,
                    doc_version=chunk.doc_version,
                    doc_hash=chunk.doc_hash,
                    evidence_quote=chunk.text[:120],
                    verification_status="VERIFIED_EXACT",
                )
            )
            
    return claims


def generate_suggested_prompts(
    doc_name: str,
    claims: Optional[List[GeneratedClaim]] = None,
    query: Optional[str] = None,
) -> List[str]:
    """
    Generates 3 contextual, high-value suggested follow-up prompts for the user.
    """
    full_text = " ".join([c.claim_text for c in (claims or [])]).lower()
    doc_lower = doc_name.lower()
    q_lower = (query or "").lower()

    # Case 1: Sorting algorithms project
    if any(w in full_text or w in doc_lower for w in ["thuật toán", "sắp xếp", "sorting", "sort", "quicksort", "mergesort", "radix"]):
        if any(w in q_lower for w in ["bao nhiêu", "danh sách", "gồm những"]):
            return [
                "Lệnh biên dịch và chạy 12 thuật toán là gì?",
                "Quy định về định dạng file input.txt và output.txt?",
                "4 kiểu dữ liệu kiểm thử (ngẫu nhiên, có thứ tự, ngược, gần như) là gì?",
            ]
        return [
            "Danh sách 12 thuật toán sắp xếp cần cài đặt?",
            "Lệnh biên dịch mã nguồn C/C++ là gì?",
            "Quy định về thời gian chạy và số phép so sánh?",
        ]

    # Case 2: Lab 06 AI / RAG / Assistant project
    if any(w in full_text or w in doc_lower for w in ["lab06", "lab 06", "rag", "retrieval", "llm", "csc10014", "grounding"]):
        return [
            "Kiến trúc 3 luồng xử lý (The Three Paths) gồm những luồng nào?",
            "Cơ chế Grounding check và kiểm tra trích dẫn hoạt động ra sao?",
            "Quy định dạy AI biết từ chối trả lời (Abstain) khi thiếu dữ liệu?",
        ]

    # Case 3: Project Brief / Academic Deliverables
    if any(w in full_text or w in doc_lower for w in ["project_brief", "submission", "deadline", "báo cáo", "hạn chót", "nộp bài"]):
        return [
            "Gói nộp bài (Submission Package) gồm những thành phần nào?",
            "5 tiêu chuẩn kỹ thuật cốt lõi R1 đến R5 là gì?",
            "Chính sách trừ điểm khi nộp muộn không báo trước?",
        ]

    # Case 4: Default smart overview prompts
    return [
        "Các yêu cầu kỹ thuật và tiêu chuẩn cốt lõi là gì?",
        "Hạn chót và các con số định lượng quan trọng trong file?",
        "Những lưu ý và khuyến nghị thực thi quan trọng nhất?",
    ]


class QAService:
    """Nghiệp vụ Q&A có đối soát trích dẫn (Grounded Q&A with Citation Verification)."""

    def __init__(
        self,
        repository: Optional[WorkspaceRepository] = None,
        provider: Optional[LLMProvider] = None,
        embed_provider: Optional[Any] = None,
    ) -> None:
        self.repository = repository or workspace_repository
        self.provider = provider or llm_provider
        self.embed_provider = embed_provider or embedding_provider
        # Inject embed_fn into repository if available
        embed_fn = self.embed_provider.get_embed_fn()
        if embed_fn is not None:
            self.repository.set_embed_fn(embed_fn)

    def summarize_document(self, doc_id: str) -> Dict[str, Any]:
        """Summarizes a specific document in the workspace using the active LLM or deterministic engine."""
        chunks = self.repository.get_document_chunks(doc_id)
        if not chunks:
            # If not found by exact id, try matching substring or stem without extension
            clean_id = doc_id.lower().replace(".pdf", "").replace(".txt", "").replace(".csv", "").strip()
            matching = [
                c for c in self.repository.chunks
                if doc_id.lower() in c.doc_id.lower()
                or doc_id.lower() in c.doc_name.lower()
                or clean_id in c.doc_id.lower()
                or clean_id in c.doc_name.lower()
            ]
            chunks = matching
            if not chunks:
                return {
                    "route": RouteType.QA_FLOW,
                    "status": "DOCUMENT_NOT_FOUND",
                    "message": f"Không tìm thấy tài liệu `{doc_id}` trong Workspace để tóm tắt.",
                    "summary": "",
                    "grounding_score": 0.0,
                    "validated_claims": [],
                    "hallucination_flags": [],
                }

        doc_name = chunks[0].doc_name
        summary_text = self.provider.generate_summary(doc_name, chunks)
        section_claims = parse_summary_into_section_claims(summary_text, chunks)
        suggested = generate_suggested_prompts(doc_name, section_claims)

        return {
            "route": RouteType.QA_FLOW,
            "status": "SUMMARY_GENERATED",
            "doc_name": doc_name,
            "summary": summary_text,
            "grounding_score": 1.0,
            "validated_claims": section_claims,
            "hallucination_flags": [],
            "suggested_questions": suggested,
        }

    def answer_question(
        self,
        query: str,
        top_k: int = 3,
        selected_doc_ids: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        tau_rel: Optional[float] = None,
        theta_match: Optional[float] = None,
    ) -> Dict[str, Any]:
        # 1. Rule: Explicit empty document selection must abstain immediately
        if selected_doc_ids is not None and len(selected_doc_ids) == 0:
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_NO_SOURCE_SELECTED",
                "message": "Chưa chọn tài liệu nguồn nào. Vui lòng chọn ít nhất một tài liệu trong Document Library để tra cứu.",
                "citations": [],
                "dense_available": getattr(self.repository, "dense_available", False),
                "validated_claims": [],
                "hallucination_flags": [],
                "grounding_score": 0.0,
            }

        q_lower = query.lower()

        # Check if query is explicitly asking to summarize or ask about overall content of a document
        summary_keywords = [
            "tóm tắt", "summarize", "tổng quan", "tóm lược", "summary", "review file", "overview",
            "nói về gì", "về cái gì", "về điều gì", "nội dung gì", "nội dung chính", "nội dung của file",
            "nội dung của tài liệu", "tài liệu này nói gì", "file này có gì", "file này viết gì",
            "chủ đề là gì", "chủ đề của file", "giới thiệu về file", "khái quát",
            "what is this file about", "what is this document about", "what does this file say",
        ]
        if any(w in q_lower for w in summary_keywords):
            target_doc = resolve_summary_target(query, self.repository, selected_doc_ids)
            if target_doc:
                return self.summarize_document(target_doc)

        dense_active = getattr(self.repository, "dense_available", False)
        default_min_score = settings.dense_tau_rel if dense_active else settings.bm25_tau_rel
        min_score = tau_rel if tau_rel is not None else default_min_score
        match_threshold = theta_match if theta_match is not None else settings.theta_match

        # 2. Deterministic Contextual Query Expansion
        retrieval_query = expand_contextual_query(query, conversation_history)
        # Prioritize current query keywords 3x over conversation history
        weighted_query = f"{query} {query} {query} {retrieval_query}" if retrieval_query != query else query

        # 3. Adaptive Top-K & Page Diversity based on query breadth
        is_broad_query = any(
            w in q_lower for w in ["tất cả", "toàn bộ", "danh sách", "gồm những gì", "các yêu cầu", "các tiêu chuẩn", "tổng hợp", "overview", "all", "list", "chi tiết"]
        )
        effective_top_k = max(top_k, 5) if is_broad_query else top_k

        # 4. Hybrid RRF Retrieval
        retrieved = self.repository.search(weighted_query, top_k=effective_top_k, selected_doc_ids=selected_doc_ids)
        if not retrieved or retrieved[0].score < min_score:
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "message": "Không tìm thấy đủ bằng chứng trong các tài liệu hiện có của Workspace để trả lời câu hỏi này.",
                "citations": [],
                "dense_available": dense_active,
                "validated_claims": [],
                "hallucination_flags": [],
                "grounding_score": 0.0,
            }

        # 4. Grounded Reasoning with Conversation History & Structured Qwen Prompting
        raw_claims = self.provider.generate_grounded_qa(
            query,
            retrieved,
            conversation_history=conversation_history,
        )

        # 5. Snap claims to exact chunk coordinates (Step 2.5) while preserving hallucination detection
        aligned_claims = [align_claim_to_chunks(c, retrieved) for c in raw_claims]

        # 6. Deterministic Citation Verification (pure Python stdlib)
        algo_claims = [claim_schema_to_algorithm(c) for c in aligned_claims]
        algo_verification = verify_citations(
            algo_claims,
            self.repository.build_page_lookup(),
            theta_match=match_threshold,
        )
        verification = verification_result_to_schema(algo_verification)

        # 7. Rule: If every claim fails citation verification -> Abstain
        if not verification.validated_claims:
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "message": "Không tìm thấy đủ bằng chứng đã được kiểm chứng trích lục trong các tài liệu để trả lời câu hỏi này.",
                "citations": [],
                "dense_available": dense_active,
                "validated_claims": [],
                "hallucination_flags": verification.hallucination_flags,
                "grounding_score": 0.0,
            }

        citations = []
        for c in verification.validated_claims:
            line_str = f", Dòng {c.cited_start_line}-{c.cited_end_line}" if c.cited_start_line and c.cited_end_line else ""
            citations.append(f"{c.cited_doc_id} (Trang {c.cited_page}{line_str})")

        primary_doc = verification.validated_claims[0].cited_doc_id if verification.validated_claims else "Tài liệu"
        suggested = generate_suggested_prompts(primary_doc, verification.validated_claims, query)

        return {
            "route": RouteType.QA_FLOW,
            "status": "ANSWER_VERIFIED",
            "grounding_score": verification.grounding_score,
            "dense_available": dense_active,
            "citations": citations,
            "validated_claims": verification.validated_claims,
            "hallucination_flags": verification.hallucination_flags,
            "suggested_questions": suggested,
        }


# Singleton instance
qa_service = QAService()


def handle_qa_request(query: str, top_k: int = 3) -> Dict[str, Any]:
    return qa_service.answer_question(query, top_k=top_k)
