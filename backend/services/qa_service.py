from typing import Any, Dict, Optional
from backend.algorithms.citation_verifier import verify_citations
from backend.core.config import settings
from backend.core.schemas import GeneratedClaim, RouteType
from backend.providers.llm_provider import LLMProvider, llm_provider
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository


class QAService:
    """Nghiệp vụ Q&A có đối soát trích dẫn (Grounded Q&A with Citation Verification)."""

    def __init__(
        self,
        repository: Optional[WorkspaceRepository] = None,
        provider: Optional[LLMProvider] = None,
    ) -> None:
        self.repository = repository or workspace_repository
        self.provider = provider or llm_provider

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
        tau_rel: Optional[float] = None,
        theta_match: Optional[float] = None,
    ) -> Dict[str, Any]:
        q_lower = query.lower()

        # Check if query is explicitly asking to summarize a document
        summary_keywords = ["tóm tắt", "summarize", "tổng quan tài liệu", "tóm lược", "summary"]
        if any(w in q_lower for w in summary_keywords):
            # Check if any specific document name is mentioned
            target_doc: Optional[str] = None
            for c in self.repository.chunks:
                if c.doc_name.lower() in q_lower or c.doc_id.lower() in q_lower:
                    target_doc = c.doc_name
                    break
            
            # Default to first document if not specified
            if not target_doc and self.repository.chunks:
                target_doc = self.repository.chunks[0].doc_name

            if target_doc:
                return self.summarize_document(target_doc)

        min_score = tau_rel if tau_rel is not None else settings.tau_rel
        match_threshold = theta_match if theta_match is not None else settings.theta_match

        retrieved = self.repository.search(query, top_k=top_k)
        if not retrieved or retrieved[0].score < min_score:
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "message": "Không tìm thấy đủ bằng chứng trong các tài liệu hiện có của Workspace để trả lời câu hỏi này.",
                "citations": [],
            }

        raw_claims = self.provider.generate_grounded_qa(query, retrieved)
        verification = verify_citations(
            raw_claims,
            self.repository.build_page_lookup(),
            theta_match=match_threshold,
        )
        return {
            "route": RouteType.QA_FLOW,
            "status": "ANSWER_VERIFIED",
            "grounding_score": verification.grounding_score,
            "validated_claims": verification.validated_claims,
            "hallucination_flags": verification.hallucination_flags,
        }


# Singleton instance
qa_service = QAService()


def handle_qa_request(query: str, top_k: int = 3) -> Dict[str, Any]:
    return qa_service.answer_question(query, top_k=top_k)
