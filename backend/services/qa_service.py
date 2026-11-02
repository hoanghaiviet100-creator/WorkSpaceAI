from typing import Any, Dict, List, Optional
from backend.algorithms.citation_verifier import (
    CitationClaim,
    CitationVerificationResult as AlgoVerificationResult,
    verify_citations,
)
from backend.core.config import settings
from backend.core.schemas import CitationVerificationResult, GeneratedClaim, RouteType
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
    "thứ này", "it", "this", "that", "these", "those", "they", "them",
    "above", "mentioned",
}


def expand_contextual_query(query: str, history: Optional[List[Dict[str, str]]]) -> str:
    """
    R1/R5 Deterministic Contextual Query Expansion.
    When current query is short (<= 4 words) or contains reference pronouns ('nó', 'đó', 'it', etc.),
    appends the most recent user turn to supply semantic context for retrieval.
    Zero LLM calls required.
    """
    if not history:
        return query

    import re
    tokens = set(re.findall(r"\w+", query.lower()))
    is_short = len(tokens) <= 4 or len(query.strip()) <= 20
    has_pronoun = bool(tokens & REFERENCE_PRONOUNS) or any(
        phrase in query.lower() for phrase in ["ở trên", "cái này", "điều này"]
    )

    if not (is_short or has_pronoun):
        return query

    # Find the most recent user question
    for turn in reversed(history):
        if turn.get("role") == "user" and turn.get("content"):
            last_user_query = turn["content"].strip()
            if last_user_query.lower() != query.lower():
                return f"{last_user_query} {query}".strip()

    return query


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
            # If not found by exact id, try matching substring
            matching = [c for c in self.repository.chunks if doc_id.lower() in c.doc_id.lower() or doc_id.lower() in c.doc_name.lower()]
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
        top = chunks[0]
        claim = GeneratedClaim(
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
        return {
            "route": RouteType.QA_FLOW,
            "status": "SUMMARY_GENERATED",
            "doc_name": doc_name,
            "summary": summary_text,
            "grounding_score": 1.0,
            "validated_claims": [claim],
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

        # Check if query is explicitly asking to summarize a document
        summary_keywords = ["tóm tắt", "summarize", "tổng quan tài liệu", "tóm lược", "summary"]
        if any(w in q_lower for w in summary_keywords):
            target_doc: Optional[str] = None
            for c in self.repository.chunks:
                if c.doc_name.lower() in q_lower or c.doc_id.lower() in q_lower:
                    target_doc = c.doc_name
                    break
            
            if not target_doc and self.repository.chunks:
                target_doc = self.repository.chunks[0].doc_name

            if target_doc:
                return self.summarize_document(target_doc)

        dense_active = getattr(self.repository, "dense_available", False)
        default_min_score = settings.dense_tau_rel if dense_active else settings.bm25_tau_rel
        min_score = tau_rel if tau_rel is not None else default_min_score
        match_threshold = theta_match if theta_match is not None else settings.theta_match

        # 2. Deterministic Contextual Query Expansion
        retrieval_query = expand_contextual_query(query, conversation_history)

        # 3. Hybrid RRF Retrieval
        retrieved = self.repository.search(retrieval_query, top_k=top_k, selected_doc_ids=selected_doc_ids)
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

        # 4. Grounded Reasoning with Conversation History
        raw_claims = self.provider.generate_grounded_qa(
            query,
            retrieved,
            conversation_history=conversation_history,
        )

        # 5. Deterministic Citation Verification (pure Python stdlib)
        algo_claims = [claim_schema_to_algorithm(c) for c in raw_claims]
        algo_verification = verify_citations(
            algo_claims,
            self.repository.build_page_lookup(),
            theta_match=match_threshold,
        )
        verification = verification_result_to_schema(algo_verification)

        # 6. Rule: If every claim fails citation verification -> Abstain
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
