import re
from typing import Any, Dict, List, Optional
from backend.algorithms.citation_verifier import (
    CitationClaim,
    CitationVerificationResult as AlgoVerificationResult,
    verify_citations,
    build_f1_citation_lookup,
)
from backend.algorithms.f1_claim_support import parse_bound_proposition, source_assertions
from backend.services.f1_claim_support_service import F1SupportGate
from backend.core.config import settings
from backend.core.schemas import CitationVerificationResult, DocumentChunk, GeneratedClaim, RouteType
from backend.providers.embedding_provider import embedding_provider
from backend.providers.llm_provider import LLMProvider, llm_provider
from backend.repositories.workspace_repository import WorkspaceRepository, workspace_repository


def _covers_compound_request(query, claims):
    """Reject incomplete output for structurally declared bounded compounds.

    This only rejects incomplete output; it never grants citation or support.
    The existing closed grammar handles identity, polarity, values and units.
    """
    quoted = list(re.finditer(r'["“]([^"”]+)["”]', query, re.DOTALL))
    spans = [match.group(1) for match in quoted]
    spans.append(query.strip().rstrip("?.!"))
    required = []
    for left, right in zip(quoted, quoted[1:]):
        if re.fullmatch(r"\s+(?:and|và)\s+", query[left.end():right.start()], re.IGNORECASE):
            atoms = [parse_bound_proposition(match.group(1)) for match in (left, right)]
            if any(atom is not None for atom in atoms):
                if any(atom is None for atom in atoms):
                    return False
                required.extend(atoms)
    for span in spans:
        parts = re.split(r"\s+(?:and|và)\s+", span, flags=re.IGNORECASE)
        if len(parts) < 2:
            continue
        atoms = [parse_bound_proposition(part) for part in parts]
        # Titles and phrases without a recognized proposition do not create
        # an assertion. A partially recognized compound cannot grant coverage.
        if not any(atom is not None for atom in atoms):
            continue
        if any(atom is None for atom in atoms):
            return False
        required.extend(atoms)
    if not required:
        return True
    covered = set()
    for claim in claims:
        for part in re.split(r"\s+(?:and|và)\s+", claim.claim_text, flags=re.IGNORECASE):
            covered.update(p for text in source_assertions(part)
                           if (p := parse_bound_proposition(text)) is not None)
    return all(part in covered for part in required)


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
    """Preserve original evidence; strict verification owns same-document locator correction.

    Keep this observable pipeline stage without substituting source text for a
    rejected quote or changing identity based on retrieval order.
    """
    return claim.model_copy(deep=True)


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
    """Conservative extractive fallback: whole chunks preserve qualifications.

    Generated prose is never treated as correctness evidence. This helper emits
    unverified candidates; the shared citation/support gate owns every verdict.
    """
    return [GeneratedClaim(claim_text=c.text, cited_doc_id=c.doc_id,
        cited_page=c.page_number, cited_start_line=c.start_line, cited_end_line=c.end_line,
        doc_version=c.doc_version, doc_hash=c.doc_hash, evidence_quote=c.text)
        for c in chunks[:4] if c.text.strip()]


def generate_suggested_prompts(doc_name, claims=None, query=None):
    # Questions add no source-specific factual assertions.
    return ["Tài liệu nêu những yêu cầu nào?", "Những điều kiện nào cần lưu ý?",
            "Có thể trích dẫn nội dung liên quan không?"]


def _authorized_chunks(chunks, retrieved, selected):
    if selected is None:
        ids = {c.doc_id for c in retrieved}
    else:
        ids = set()
        canonical = {c.doc_id.casefold(): c.doc_id for c in chunks}
        for name in selected:
            if name.casefold() in canonical:
                ids.add(canonical[name.casefold()])
            else:
                aliases = {c.doc_id for c in chunks if c.doc_name.casefold() == name.casefold()}
                if len(aliases) == 1:
                    ids.update(aliases)
    return [c for c in chunks if c.doc_id in ids]


def _redacted_flags(claims):
    # Rejected factual text/explanations must not reappear in the API response.
    return [c.model_copy(update=dict(claim_text="", evidence_quote="", thinking=None,
        section=None, matched_span=None, evidence_span=None, cited_doc_id="", cited_page=0,
        cited_start_line=None, cited_end_line=None, doc_version=None, doc_hash=None,
        match_score=0.0)) for c in claims]


class QAService:
    """Nghiệp vụ Q&A có đối soát trích dẫn (Grounded Q&A with Citation Verification)."""

    def __init__(
        self,
        repository: Optional[WorkspaceRepository] = None,
        provider: Optional[LLMProvider] = None,
        embed_provider: Optional[Any] = None,
        support_gate: Optional[F1SupportGate] = None,
    ) -> None:
        self.support_gate = support_gate or F1SupportGate()
        self.repository = repository or workspace_repository
        self.provider = provider or llm_provider
        self.embed_provider = embed_provider or embedding_provider
        # Inject embed_fn into repository if repository does not already have an active embed_fn
        if getattr(self.repository, "_embed_fn", None) is None:
            embed_fn = self.embed_provider.get_embed_fn()
            if embed_fn is not None:
                self.repository.set_embed_fn(embed_fn)

    def _verify_output(self, candidates, source_chunks, match_threshold=None):
        citation_result = verify_citations([claim_schema_to_algorithm(c) for c in candidates],
            build_f1_citation_lookup(source_chunks), strict=True, allow_locator_correction=False,
            theta_match=match_threshold if match_threshold is not None else settings.theta_match)
        verified = verification_result_to_schema(citation_result)
        gate = getattr(self, 'support_gate', None) or F1SupportGate()
        supported, rejected, decisions = gate.verify_claims(verified.validated_claims, source_chunks)
        flags = _redacted_flags(verified.hallucination_flags + rejected)
        score = round(len(supported) / max(1, len(candidates)), 4)
        return supported, flags, score

    def summarize_document(self, doc_id: str, selected_doc_ids=None) -> Dict[str, Any]:
        # Resolve only exact authorized identities/names; no substring rescue.
        all_chunks = self.repository.chunks
        request_chunks = _authorized_chunks(all_chunks, [], selected_doc_ids if selected_doc_ids is not None else [doc_id])
        chunks = [c for c in request_chunks if doc_id.casefold() in (c.doc_id.casefold(), c.doc_name.casefold())]
        if not chunks or len({c.doc_id for c in chunks}) != 1:
            return dict(route=RouteType.QA_FLOW, status="ABSTAINED_INSUFFICIENT_EVIDENCE",
                summary="", grounding_score=0.0, validated_claims=[], hallucination_flags=[],
                citations=[], thinking=None)
        doc_name = chunks[0].doc_name
        # Keep the existing generation failure contract. Its output is only a
        # proposal; the served summary uses the bounded extractive fallback.
        proposal = self.provider.generate_summary(doc_name, chunks)
        candidates = parse_summary_into_section_claims(proposal, chunks)
        supported, flags, score = self._verify_output(candidates, request_chunks)
        if not supported:
            return dict(route=RouteType.QA_FLOW, status="ABSTAINED_INSUFFICIENT_EVIDENCE",
                doc_name=doc_name, summary="", grounding_score=0.0, validated_claims=[],
                hallucination_flags=flags, citations=[], thinking=None)
        return dict(route=RouteType.QA_FLOW, status="SUMMARY_GENERATED", doc_name=doc_name,
            summary="\n\n".join(c.claim_text for c in supported), grounding_score=score,
            validated_claims=supported, hallucination_flags=flags, thinking=None,
            citations=[f"{c.cited_doc_id} (Trang {c.cited_page}, Dòng {c.cited_start_line}-{c.cited_end_line})" for c in supported],
            suggested_questions=generate_suggested_prompts(doc_name, supported))

    def _answer_evidence_question(self, query, top_k, selected_doc_ids, conversation_history, tau_rel):
        from backend.services.f1_evidence_profile_service import F1EvidenceProfileService,generate_evidence_claims
        from backend.core.schemas import EvidenceProfileVerification
        gate=F1EvidenceProfileService(self.repository)
        chunks,identities=gate._scope(selected_doc_ids)
        if not chunks:
            return dict(route=RouteType.QA_FLOW,status='ABSTAINED_NO_SOURCE_SELECTED',
                message='Chưa chọn tài liệu nguồn nào.',citations=[],validated_claims=[],hallucination_flags=[])
        dense=bool(self.repository.dense_available)
        retrieval_query=expand_contextual_query(query,conversation_history)
        weighted=f'{query} {query} {query} {retrieval_query}' if retrieval_query!=query else query
        found=self.repository.search(weighted,top_k=top_k,selected_doc_ids=[d[0] for d in identities])
        minimum=tau_rel if tau_rel is not None else min(settings.dense_tau_rel if dense else settings.bm25_tau_rel,
                                                       .20 if dense else .25)
        if not found or found[0].score<minimum:
            return dict(route=RouteType.QA_FLOW,status='ABSTAINED_INSUFFICIENT_EVIDENCE',
                message='Không tìm thấy đủ bằng chứng trong các tài liệu đã chọn.',
                citations=[],validated_claims=[],hallucination_flags=[],dense_available=dense)
        # Existing request nonce map and exact excerpt binding stay authoritative.
        raw=generate_evidence_claims(self.provider,query,found,conversation_history)
        result=gate.verify_claims(raw,[d[0] for d in identities])
        if result['status']=='SOURCE_SUPPORTED' and not _covers_compound_request(query,raw):
            result.update(status='ABSTAINED_INSUFFICIENT_EVIDENCE',answer=None,citations=[])
            for claim in result['verification']['claims']:
                claim.update(disposition='INSUFFICIENT_EVIDENCE',reason='INCOMPLETE_COMPOUND_ANSWER')
        if any(c['disposition']=='CONFIRMED_CONFLICT' for c in result['verification']['claims']):
            result['status']='SOURCE_CONFLICT'
        for claim in result['verification']['claims']:
            for competing in claim['competing_evidence']:
                if competing['relation']=='AMBIGUOUS':competing['relation']='UNRESOLVED'
        result['verification']=EvidenceProfileVerification(**result['verification']).model_dump()
        result.pop('retrieval_log',None)  # Detailed search audit belongs in instrumentation.
        result.update(route=RouteType.QA_FLOW,dense_available=dense,hallucination_flags=[])
        if result['status']=='SOURCE_SUPPORTED':
            result['message']=result['verification']['limitations'][0]
            result['citations']=[f"{c['doc_id']} (Trang {c['page']}, Dòng {c['line_start']}-{c['line_end']})"
                for claim in result['verification']['claims'] for c in claim['citations']]
        elif result['status']=='SOURCE_CONFLICT':
            result['message']='Nguồn có thông tin mâu thuẫn về nhận định này.'
        elif any(c['disposition']=='INSUFFICIENT_CONFLICT_COVERAGE' for c in result['verification']['claims']):
            result['message']='Chưa đủ độ bao phủ để kết luận; có bằng chứng cần đối chiếu.'
        else:
            result['message']='Không đủ bằng chứng hỗ trợ toàn bộ câu trả lời.'
        return result

    def answer_question(
        self,
        query: str,
        top_k: int = 3,
        selected_doc_ids: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        tau_rel: Optional[float] = None,
        theta_match: Optional[float] = None,
        verification_profile: str = "strict",
    ) -> Dict[str, Any]:
        if verification_profile == "evidence_centric_v0":
            return self._answer_evidence_question(query,top_k,selected_doc_ids,conversation_history,tau_rel)
        if verification_profile != "strict":
            raise ValueError("UNKNOWN_VERIFICATION_PROFILE")
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
                return self.summarize_document(target_doc, selected_doc_ids)

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
        source_chunks = _authorized_chunks(self.repository.chunks, retrieved, selected_doc_ids)
        authorized_ids = {c.doc_id for c in source_chunks}
        retrieved = [c for c in retrieved if c.doc_id in authorized_ids]
        # Adaptive threshold: allow top-ranked chunks with score >= 0.20 when dense active, unless caller explicitly enforces tau_rel
        if tau_rel is not None:
            effective_min_score = tau_rel
        else:
            effective_min_score = min(min_score, 0.20 if dense_active else 0.25) if (retrieved and len(query.strip()) >= 4) else min_score

        if not retrieved or retrieved[0].score < effective_min_score:
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

        # 5. Preserve submitted claims/evidence through the observable alignment stage.
        aligned_claims = [align_claim_to_chunks(c, retrieved) for c in raw_claims]

        # Citation integrity -> deterministic/NLI support -> conflict -> output validation.
        supported, flags, score = self._verify_output(aligned_claims, source_chunks, match_threshold)
        verification = CitationVerificationResult(validated_claims=supported,
            hallucination_flags=flags, grounding_score=score)

        # R2 rejection is authoritative: no quote substitution or synthetic acceptance.
        coverage_ok = _covers_compound_request(query, verification.validated_claims)
        if not verification.validated_claims or not coverage_ok:
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "message": "Không tìm thấy đủ bằng chứng đã được kiểm chứng trích lục trong các tài liệu để trả lời câu hỏi này.",
                "citations": [],
                "dense_available": dense_active,
                "validated_claims": [],
                "hallucination_flags": verification.hallucination_flags,
                "grounding_score": verification.grounding_score if coverage_ok else 0.0,
            }

        citations = []
        thinking_text = None  # P1: no factual explanation inherits a claim verdict.
        for c in verification.validated_claims:
            line_str = f", Dòng {c.cited_start_line}-{c.cited_end_line}"
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
            "thinking": thinking_text,
        }


# Singleton instance
qa_service = QAService()


def handle_qa_request(query: str, top_k: int = 3) -> Dict[str, Any]:
    return qa_service.answer_question(query, top_k=top_k)
