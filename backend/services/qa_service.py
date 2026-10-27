from typing import Any, Dict, Optional
from backend.algorithms.citation_verifier import verify_citations
from backend.core.config import settings
from backend.core.schemas import RouteType
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

    def answer_question(
        self,
        query: str,
        top_k: int = 3,
        tau_rel: Optional[float] = None,
        theta_match: Optional[float] = None,
    ) -> Dict[str, Any]:
        min_score = tau_rel if tau_rel is not None else settings.tau_rel
        match_threshold = theta_match if theta_match is not None else settings.theta_match

        retrieved = self.repository.search(query, top_k=top_k)
        if not retrieved or retrieved[0].score < min_score:
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "message": "Insufficient evidence in your workspace documents to answer this question.",
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
