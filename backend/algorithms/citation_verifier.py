import re
from typing import Dict, List, Tuple
from backend.core.schemas import CitationVerificationResult, GeneratedClaim


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _token_overlap_ratio(quote: str, source: str) -> float:
    q_tokens = re.findall(r"\w+", quote)
    s_tokens = set(re.findall(r"\w+", source))
    if not q_tokens:
        return 0.0
    matched = sum(1 for tok in q_tokens if tok in s_tokens)
    return matched / len(q_tokens)


def verify_citations(
    claims: List[GeneratedClaim],
    chunk_lookup: Dict[Tuple[str, int], str],
    theta_match: float = 0.75,
) -> CitationVerificationResult:
    """
    R2 Deterministic Capability #2:
    Verifies whether each generated claim's cited (doc_id, page) exists and
    whether the quoted evidence span appears verbatim or above token overlap threshold (theta_match).
    """
    validated: List[GeneratedClaim] = []
    flagged: List[GeneratedClaim] = []
    verified_count = 0

    for c in claims:
        key = (c.cited_doc_id, c.cited_page)
        if key not in chunk_lookup:
            c.verification_status = "INVALID_SOURCE_PAGE"
            flagged.append(c)
            continue

        norm_source = _normalize_text(chunk_lookup[key])
        norm_quote = _normalize_text(c.evidence_quote)

        if norm_quote and norm_quote in norm_source:
            c.verification_status = "VERIFIED_EXACT"
            verified_count += 1
            validated.append(c)
        else:
            overlap = _token_overlap_ratio(norm_quote, norm_source)
            if overlap >= theta_match:
                c.verification_status = "VERIFIED_FUZZY"
                verified_count += 1
                validated.append(c)
            else:
                c.verification_status = "UNGROUNDED_QUOTE"
                flagged.append(c)

    score = round(verified_count / max(1, len(claims)), 4)
    return CitationVerificationResult(
        validated_claims=validated,
        hallucination_flags=flagged,
        grounding_score=score,
    )
