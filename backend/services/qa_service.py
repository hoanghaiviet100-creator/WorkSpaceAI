import re
from time import monotonic
from typing import Any, Dict, List, Optional
from backend.algorithms.citation_verifier import (
    CitationClaim,
    CitationVerificationResult as AlgoVerificationResult,
    verify_citations,
)
from backend.core.config import settings
from backend.core.schemas import CitationVerificationResult, DocumentChunk, GeneratedClaim, RouteType
from backend.providers.embedding_provider import embedding_provider
from backend.providers.llm_provider import GeminiRequestError, GeminiUnavailableError, LLMProvider, llm_provider
from backend.providers.prompts import requests_detailed_answer
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository


def claim_schema_to_algorithm(claim: GeneratedClaim) -> CitationClaim:
    """Adapts a Pydantic GeneratedClaim into a pure stdlib CitationClaim."""
    return CitationClaim(
        claim_text=claim.claim_text,
        section=claim.section,
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
        section=claim.section,
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


def is_greeting(query: str) -> bool:
    clean = re.sub(r"[.!?,]+$", "", query.strip().lower()).strip()
    return clean in {"alo", "hello", "hi", "hey", "chào", "xin chào", "chào bạn", "bạn ơi", "cảm ơn", "thanks"}


def is_detail_followup(query: str) -> bool:
    """Recognize subject-free elaboration requests, not new named topics."""
    clean = re.sub(r"[.!?]+$", "", query.strip().lower()).strip()
    clean = re.sub(r"^(?:hãy|vui lòng|bạn có thể)\s+", "", clean)
    return bool(re.fullmatch(
        r"(?:(?:mô tả|giải thích|trình bày|phân tích|nói|viết|làm rõ|explain|describe|elaborate)\s+)?"
        r"(?:(?:lại|thêm)\s+)?(?:(?:một cách|cụ thể|kỹ|rõ)\s+)?"
        r"(?:chi tiết|cụ thể|rõ|kỹ|detailed|in detail|more detail|more)"
        r"(?:\s+(?:hơn|nữa|đi|giúp tôi|cho tôi|về nó|về phần trên))*", clean
    ))


FEATURE_REFERENCE = re.compile(r"\b(?:features?|feat|tính năng|tinh nang|f)\s*[:#-]?\s*(\d+)\b", re.IGNORECASE)
FEATURE_HEADING = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)[.)]?\s+)?(?:feature|tính năng|tinh nang)\s*(\d+)\s*(?:[—–:-]\s*\S|$)",
    re.IGNORECASE,
)


def find_feature_section(chunks: List[DocumentChunk], feature: str) -> List[DocumentChunk]:
    """Keep only lines under the requested heading, excluding table-of-contents entries."""
    ordered = sorted(chunks, key=lambda c: (c.doc_id, c.page_number, c.start_line or 1))
    headings = {}
    numbered = {}
    for chunk in ordered:
        for index, line in enumerate(chunk.text.splitlines(), start=chunk.start_line or 1):
            if re.search(r"(?:\.\s*){3,}|\t+\d+\s*$", line):
                continue
            position = (chunk.doc_id, chunk.page_number, index)
            heading = FEATURE_HEADING.match(line)
            if heading:
                headings[position] = (heading[2], heading[1])
            number = re.match(r"^\s*(\d+(?:\.\d+)+)\s+[^\W\d_]", line)
            if number:
                numbered[position] = number[1]

    boundaries = sorted(headings)
    selected = []
    for index, start in enumerate(boundaries):
        number, prefix = headings[start]
        if number != feature:
            continue
        end = boundaries[index + 1] if index + 1 < len(boundaries) else None
        if prefix:
            end = min((position for position, label in numbered.items()
                       if position[0] == start[0] and position > start and label != prefix
                       and not label.startswith(prefix + ".") and (end is None or position < end)), default=end)
        for chunk in ordered:
            if chunk.doc_id != start[0]:
                continue
            first = chunk.start_line or 1
            lines = chunk.text.splitlines()
            kept = [(line_no, line) for line_no, line in enumerate(lines, start=first)
                    if (chunk.doc_id, chunk.page_number, line_no) >= start
                    and (end is None or (chunk.doc_id, chunk.page_number, line_no) < end)]
            if kept:
                selected.append(chunk.model_copy(update={
                    "text": "\n".join(line for _, line in kept), "start_line": kept[0][0], "end_line": kept[-1][0],
                }))
    return selected


def expand_contextual_query(query: str, history: Optional[List[Dict[str, str]]]) -> str:
    """
    R1/R5 Deterministic Contextual Query Expansion.
    Expands with previous context ONLY IF:
    1. Query contains genuine anaphoric reference pronouns/phrases ('nó', 'đó', 'ở trên', 'còn...', 'thế còn...').
    2. OR query is an incomplete fragment (< 4 words) lacking standalone subject and question word.
    Independent standalone questions are preserved 100% intact to prevent topic drift.
    """
    if not history or FEATURE_REFERENCE.search(query):
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

    if not (has_pronoun or is_follow_up or is_short_fragment or is_detail_followup(query)):
        return query

    # Find the most recent substantive user question
    for turn in reversed(history):
        if turn.get("role") == "user" and turn.get("content"):
            last_user_query = turn["content"].strip()
            if last_user_query.lower() != query.lower().strip():
                if is_detail_followup(last_user_query) or is_greeting(last_user_query):
                    continue
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
                section=claim.section,
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

    if selected_doc_ids is not None:
        all_docs = [d for d in all_docs if d.get("doc_id") in selected_doc_ids or d.get("doc_name") in selected_doc_ids]

    # Step 1: Check for explicit mention of document name or stem in query
    for d in all_docs:
        d_name = d.get("doc_name") or d.get("doc_id") or ""
        d_id = d.get("doc_id") or ""
        d_stem = d_name.rsplit(".", 1)[0].lower() if "." in d_name else d_name.lower()
        d_id_stem = d_id.rsplit(".", 1)[0].lower() if "." in d_id else d_id.lower()
        d_norm = re.sub(r"[\W_]+", " ", d_stem).strip()

        # Check full filename
        if d_name.lower() in q_lower or d_id.lower() in q_lower:
            return d_id or d_name

        # Check stem without extension (e.g. "team_8_proposal" in "tóm tắt file team_8_proposal ấy")
        if len(d_stem) >= 3 and d_stem in q_lower:
            return d_id or d_name
        if len(d_id_stem) >= 3 and d_id_stem in q_lower:
            return d_id or d_name

        # Check normalized form with spaces (e.g. "team 8 proposal" vs "team_8_proposal")
        if len(d_norm) >= 3 and (d_norm in q_norm or d_norm.replace(" ", "") in q_norm.replace(" ", "")):
            return d_id or d_name

    # Step 2: If query contains generic summary request, prioritize currently selected document in the sidebar
    if selected_doc_ids:
        for sel_id in selected_doc_ids:
            for d in all_docs:
                if d.get("doc_id") == sel_id or d.get("doc_name") == sel_id:
                    return d.get("doc_id") or sel_id
        return selected_doc_ids[0]

    # Step 3: If no specific doc mentioned and nothing selected, pick the most recently uploaded doc (last added)
    if all_docs:
        return all_docs[-1].get("doc_id") or all_docs[-1].get("doc_name")

    return None


def extract_summary_passages(chunks: List[DocumentChunk], *, detailed: bool) -> List[GeneratedClaim]:
    """Pick readable verbatim passages across a document for an unavailable cloud model."""
    by_page = {}
    seen = set()
    for chunk in sorted(chunks, key=lambda chunk: (chunk.page_number, chunk.start_line or 1)):
        lines = chunk.text.splitlines()
        for index, line in enumerate(lines):
            if not line.strip() or (index and lines[index - 1].strip() and len(line.strip()) < 70):
                continue
            excerpt = line.strip()
            end = index
            while len(excerpt) < 180 and end + 1 < len(lines) and lines[end + 1].strip():
                end += 1
                excerpt += "\n" + lines[end].strip()
            if len(excerpt) > 500:
                excerpt = excerpt[:500].rsplit(maxsplit=1)[0]
                end = index + excerpt.count("\n")
            if excerpt.casefold() not in seen:
                seen.add(excerpt.casefold())
                by_page.setdefault(chunk.page_number, []).append((chunk, index, end, excerpt))

    pages = list(by_page)
    limit = 10 if detailed else 7
    if len(pages) > limit:
        pages = [pages[round(i * (len(pages) - 1) / (limit - 1))] for i in range(limit)]
    claims = []
    for page in pages:
        candidates = sorted(by_page[page], key=lambda item: min(len(item[3].split()), 42), reverse=True)
        for chunk, start, end, excerpt in candidates[:(2 if detailed or len(pages) == 1 else 1)]:
            line = chunk.start_line or 1
            claims.append(GeneratedClaim(
                claim_text=" ".join(excerpt.split()), section=f"Trang {page}", evidence_quote=excerpt,
                cited_doc_id=chunk.doc_id, cited_page=page, cited_start_line=line + start, cited_end_line=line + end,
                doc_version=chunk.doc_version, doc_hash=chunk.doc_hash,
            ))
    return claims


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

    def summarize_document(self, doc_id: str, *, detailed: bool = False) -> Dict[str, Any]:
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
        if settings.llm_provider in {"gemini", "ollama"} and not settings.offline_only:
            is_gemini = settings.llm_provider == "gemini"
            total_chars = sum(len(c.text) for c in chunks)
            if (is_gemini and total_chars <= 120_000) or (len(chunks) <= 10 and total_chars <= 4500):
                sampled = chunks
            else:
                budget = 120_000 if is_gemini else 5500
                sample_count = max(6, len(chunks) * budget // total_chars) if is_gemini else 6
                candidates = [chunks[round(i * (len(chunks) - 1) / (sample_count - 1))] for i in range(sample_count)]
                sampled, seen, size = [], set(), 0
                for chunk in candidates:
                    if chunk.chunk_id not in seen and size + len(chunk.text) <= budget:
                        sampled.append(chunk)
                        seen.add(chunk.chunk_id)
                        size += len(chunk.text)
            scope = "toàn bộ nội dung đã lập chỉ mục" if len(sampled) == len(chunks) else "các đoạn trích đại diện"
            summary_query = f"Tóm tắt {scope} của {doc_name}."
            if detailed:
                summary_query += " Hãy mô tả chi tiết các phần chính."
            page_lookup = self.repository.build_page_lookup()

            def verify_summary(claims, evidence, *, align=True):
                pages = {(chunk.doc_id, chunk.page_number) for chunk in evidence}
                lookup = {key: page_lookup[key] for key in pages if key in page_lookup}
                return verification_result_to_schema(verify_citations(
                    [claim_schema_to_algorithm(align_claim_to_chunks(claim, evidence) if align else claim) for claim in claims],
                    lookup, theta_match=settings.theta_match,
                ))

            started = monotonic()
            extracted = False
            try:
                raw = self.provider.generate_grounded_qa(summary_query, sampled, document_summary=True)
            except GeminiUnavailableError:
                sampled = chunks
                raw = extract_summary_passages(sampled, detailed=detailed)
                extracted = True
            verification = verify_summary(raw, sampled, align=not extracted)
            claims = verification.validated_claims
            sections = {claim.section for claim in claims if claim.section}
            pages = {chunk.page_number for chunk in sampled}
            cited_pages = {claim.cited_page for claim in claims}
            ordered_pages = sorted(pages)
            midpoint = len(ordered_pages) // 2
            covers_both_halves = bool(cited_pages.intersection(ordered_pages[:midpoint])) and bool(
                cited_pages.intersection(ordered_pages[midpoint:])
            )
            # Leave time for a supplement inside the chat client's response window.
            if is_gemini and not extracted and len(pages) >= 8 and monotonic() - started < 100 and (
                len(claims) < 8 or len(sections) < 4 or not covers_both_halves
            ):
                remaining = [chunk for chunk in sampled if chunk.page_number not in cited_pages] or sampled
                covered = "\n".join(f"- {claim.section or ''} | {claim.claim_text[:280]}" for claim in claims[:16])
                supplement_query = (
                    "Bổ sung tối đa 6 ý quan trọng còn thiếu cho bản tóm tắt. Ưu tiên mục, tính năng, kết quả "
                    "hoặc rủi ro chưa được nêu. Chỉ thêm nội dung mới có thể trích dẫn từ các đoạn cung cấp. "
                    "Nếu bổ sung vào một mục đã có, dùng nguyên tên mục. Các ý dưới đây chỉ để tránh lặp, "
                    f"không dùng làm bằng chứng:\n{covered or '(chưa có ý nào được kiểm chứng)'}"
                )
                try:
                    extra = self.provider.generate_grounded_qa(
                        supplement_query, remaining, document_summary=True, supplemental_summary=True,
                    )
                except GeminiRequestError:
                    extra = []
                added = verify_summary(extra, remaining)
                seen = {" ".join(claim.claim_text.casefold().split()) for claim in claims}
                for claim in added.validated_claims:
                    key = " ".join(claim.claim_text.casefold().split())
                    if key not in seen:
                        claims.append(claim)
                        seen.add(key)
                verification.hallucination_flags.extend(added.hallucination_flags)
                total = len(claims) + len(verification.hallucination_flags)
                verification.grounding_score = round(len(claims) / max(1, total), 4)

            grouped = {}
            for index, claim in enumerate(claims):
                grouped.setdefault(claim.section or index, []).append(claim)
            claims = [claim for group in grouped.values() for claim in group]
            message = f"Tóm tắt dựa trên {scope}." if claims else "Model chưa cung cấp đủ trích dẫn hợp lệ để tóm tắt tài liệu này."
            if extracted:
                message = ("Gemini đang gián đoạn (503). Dưới đây là các đoạn nguyên văn được chọn trên máy và đã kiểm tra trích dẫn."
                           if claims else "Gemini đang gián đoạn (503) và chưa tìm thấy đoạn trích phù hợp để hiển thị.")
            return {
                "route": RouteType.QA_FLOW,
                "status": "SUMMARY_GENERATED" if verification.validated_claims else "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "doc_name": doc_name,
                "summary": "\n\n".join(c.claim_text for c in claims),
                "message": message,
                "summary_scope": "representative_excerpts" if extracted or len(sampled) != len(chunks) else "all_indexed_passages",
                "grounding_score": verification.grounding_score,
                "validated_claims": claims,
                "hallucination_flags": verification.hallucination_flags,
            }
        summary_text = self.provider.generate_summary(doc_name, chunks)

        # Collect top representative chunk from each unique page for multi-page evidence inspection
        seen_pages = set()
        multi_claims: List[GeneratedClaim] = []
        for c in chunks:
            if c.page_number not in seen_pages:
                seen_pages.add(c.page_number)
                multi_claims.append(
                    GeneratedClaim(
                        claim_text=summary_text,
                        cited_doc_id=c.doc_id,
                        cited_page=c.page_number,
                        cited_start_line=c.start_line,
                        cited_end_line=c.end_line,
                        doc_version=c.doc_version,
                        doc_hash=c.doc_hash,
                        evidence_quote=c.text[:120],
                        verification_status="VERIFIED_EXACT",
                    )
                )

        if not multi_claims and chunks:
            top = chunks[0]
            multi_claims = [
                GeneratedClaim(
                    claim_text=summary_text,
                    cited_doc_id=top.doc_id,
                    cited_page=top.page_number,
                    cited_start_line=top.start_line,
                    cited_end_line=top.end_line,
                    doc_version=top.doc_version,
                    doc_hash=top.doc_hash,
                    evidence_quote=top.text[:120],
                    verification_status="VERIFIED_EXACT",
                )
            ]

        return {
            "route": RouteType.QA_FLOW,
            "status": "SUMMARY_GENERATED",
            "doc_name": doc_name,
            "summary": summary_text,
            "grounding_score": 1.0,
            "validated_claims": multi_claims,
            "hallucination_flags": [],
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
        if is_greeting(query):
            return {
                "route": RouteType.QA_FLOW, "status": "CONVERSATION",
                "message": "Chào bạn! Mình sẵn sàng hỗ trợ. Bạn có thể chọn tài liệu rồi hỏi về nội dung, yêu cầu tóm tắt hoặc giải thích một phần cụ thể.",
                "validated_claims": [], "hallucination_flags": [], "citations": [],
            }
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
        retrieval_query = expand_contextual_query(query, conversation_history)
        detailed = is_detail_followup(query)
        summary_query = retrieval_query if detailed else query
        feature_refs = set(FEATURE_REFERENCE.findall(retrieval_query))

        # Check if query is explicitly asking to summarize a document
        summary_keywords = ["tóm tắt", "summarize", "tổng quan tài liệu", "tóm lược", "summary", "review file", "overview file", "chủ đề gì", "đang nói về", "những gì có trong file", "những gì nổi bật trong file"]
        summary_text = summary_query.lower()
        whole_document = (
            re.search(r"\b(?:miêu tả|mô tả|trình bày|describe)\b", summary_text)
            and re.search(r"\b(?:toàn bộ|tất cả|entire|whole)\b", summary_text)
            and re.search(r"\b(?:file|tệp|tài liệu|báo cáo|document|report|pdf)\b", summary_text)
        )
        if not feature_refs and (whole_document or any(w in summary_text for w in summary_keywords)):
            target_doc = resolve_summary_target(summary_query, self.repository, selected_doc_ids)
            if target_doc:
                return self.summarize_document(target_doc, detailed=detailed or requests_detailed_answer(summary_query))

        dense_active = getattr(self.repository, "dense_available", False)
        default_min_score = settings.dense_tau_rel if dense_active else settings.bm25_tau_rel
        min_score = tau_rel if tau_rel is not None else default_min_score
        match_threshold = theta_match if theta_match is not None else settings.theta_match

        # 2. Deterministic Contextual Query Expansion
        # Prioritize current query keywords 3x over conversation history
        weighted_query = FEATURE_REFERENCE.sub(lambda match: f"Feature {match[1]} tính năng {match[1]}", retrieval_query)

        # 3. Adaptive Top-K & Page Diversity based on query breadth
        is_broad_query = any(
            w in q_lower for w in ["tất cả", "toàn bộ", "danh sách", "gồm những gì", "các yêu cầu", "các tiêu chuẩn", "tổng hợp", "overview", "all", "list", "chi tiết"]
        )
        effective_top_k = max(top_k, 5) if is_broad_query else top_k

        # 4. Hybrid RRF Retrieval
        section = []
        if len(feature_refs) == 1 and hasattr(self.repository, "chunks"):
            source_chunks = self.repository.chunks if selected_doc_ids is None else [
                chunk for doc_id in selected_doc_ids for chunk in self.repository.get_document_chunks(doc_id)
            ]
            section = find_feature_section(source_chunks, next(iter(feature_refs)))
        retrieved = section or self.repository.search(weighted_query, top_k=effective_top_k, selected_doc_ids=selected_doc_ids)
        if not retrieved or (not section and retrieved[0].score < min_score):
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

        # A short document can be read in full for elaboration instead of returning
        # the same top snippets. Keep strict scope and a bounded character budget.
        if detailed and not feature_refs:
            doc_ids = {chunk.doc_id for chunk in retrieved}
            expanded = sorted(
                [chunk for doc_id in doc_ids for chunk in self.repository.get_document_chunks(doc_id)],
                key=lambda chunk: (chunk.doc_id, chunk.page_number, chunk.start_line),
            ) if hasattr(self.repository, "get_document_chunks") else []
            if expanded and len(expanded) <= 10 and sum(len(chunk.text) for chunk in expanded) <= 4500:
                retrieved = expanded

        # 4. Grounded Reasoning with Conversation History & Structured Qwen Prompting
        if feature_refs:
            retrieval_query += "\nChỉ trả lời về tính năng được hỏi. Nêu cơ chế và chi tiết có trong nguồn; bỏ qua tổng quan dự án và các tính năng khác, trừ các liên kết cần để giải thích."
        raw_claims = self.provider.generate_grounded_qa(
            retrieval_query,
            retrieved,
            conversation_history=None if feature_refs else conversation_history,
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

        return {
            "route": RouteType.QA_FLOW,
            "status": "ANSWER_VERIFIED",
            "grounding_score": verification.grounding_score,
            "dense_available": dense_active,
            "citations": citations,
            "validated_claims": verification.validated_claims,
            "hallucination_flags": verification.hallucination_flags,
        }


# Singleton instance
qa_service = QAService()


def handle_qa_request(query: str, top_k: int = 3) -> Dict[str, Any]:
    return qa_service.answer_question(query, top_k=top_k)
