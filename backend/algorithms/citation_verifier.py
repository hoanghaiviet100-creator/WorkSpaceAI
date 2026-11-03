"""
backend/algorithms/citation_verifier.py
R2 Deterministic Citation & Evidence Span Verifier (Standard Library Only).

Strict Architecture Rules:
- 100% Python standard library only.
- NO FastAPI imports.
- NO Pydantic imports.
- NO SQLAlchemy imports.
- NO network, file, or database I/O.
- Deterministic outputs based solely on inputs.

Validation Pipeline:
1. Document existence check
2. Page existence check
3. Line range validity & boundary check
4. Document version & hash provenance check
5. Evidence text match:
   - Step A: Exact normalized substring match -> VERIFIED_EXACT
   - Step B: Token-LCS (Longest Common Subsequence) sliding window -> VERIFIED_FUZZY
   - Step C: Fallback token overlap ratio -> VERIFIED_FUZZY or UNGROUNDED_QUOTE
"""
from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union


@dataclass
class CitationClaim:
    """Pure stdlib representation of a generated claim to be verified."""
    claim_text: str
    cited_doc_id: str
    cited_page: int
    evidence_quote: str
    verification_status: str = "UNVERIFIED"
    cited_start_line: Optional[int] = None
    cited_end_line: Optional[int] = None
    doc_version: Optional[str] = None
    doc_hash: Optional[str] = None
    match_score: float = 0.0
    matched_span: Optional[str] = None


@dataclass
class CitationVerificationResult:
    """Pure stdlib result container for citation verification."""
    validated_claims: List[CitationClaim] = field(default_factory=list)
    hallucination_flags: List[CitationClaim] = field(default_factory=list)
    grounding_score: float = 0.0


def _normalize_text(s: str) -> str:
    """Normalizes whitespace and converts text to lowercase."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _tokenize(s: str) -> List[str]:
    """Extracts alphanumeric word tokens in lowercase."""
    return re.findall(r"\w+", s.lower())


def _token_lcs_ratio(q_tokens: List[str], s_tokens: List[str]) -> float:
    """
    Computes Longest Common Subsequence (LCS) ratio: len(LCS) / len(q_tokens).
    Optimized 2-row dynamic programming in O(len(s_tokens)) space.
    """
    if not q_tokens or not s_tokens:
        return 0.0

    m, n = len(q_tokens), len(s_tokens)
    dp = [0] * (n + 1)

    for i in range(1, m + 1):
        prev = 0
        q_tok = q_tokens[i - 1]
        for j in range(1, n + 1):
            temp = dp[j]
            if q_tok == s_tokens[j - 1]:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = temp

    return dp[n] / m


def _token_overlap_ratio(q_tokens: List[str], s_tokens: List[str]) -> float:
    """Computes set-based token overlap ratio: len(Q ∩ S) / len(Q)."""
    if not q_tokens:
        return 0.0
    s_set = set(s_tokens)
    matched = sum(1 for tok in q_tokens if tok in s_set)
    return matched / len(q_tokens)


def _to_claim_dataclass(item: Any) -> CitationClaim:
    """
    Internal adapter to safely convert external objects or dicts into CitationClaim
    without mutating external objects or relying on Pydantic methods.
    """
    if isinstance(item, CitationClaim):
        # Return a shallow copy so we do not mutate the caller's instance
        return CitationClaim(
            claim_text=item.claim_text,
            cited_doc_id=item.cited_doc_id,
            cited_page=item.cited_page,
            evidence_quote=item.evidence_quote,
            verification_status=item.verification_status,
            cited_start_line=item.cited_start_line,
            cited_end_line=item.cited_end_line,
            doc_version=item.doc_version,
            doc_hash=item.doc_hash,
            match_score=item.match_score,
            matched_span=item.matched_span,
        )

    if isinstance(item, dict):
        return CitationClaim(
            claim_text=str(item.get("claim_text", "")),
            cited_doc_id=str(item.get("cited_doc_id", "")),
            cited_page=int(item.get("cited_page", 1)),
            evidence_quote=str(item.get("evidence_quote", "")),
            verification_status=str(item.get("verification_status", "UNVERIFIED")),
            cited_start_line=item.get("cited_start_line"),
            cited_end_line=item.get("cited_end_line"),
            doc_version=item.get("doc_version"),
            doc_hash=item.get("doc_hash"),
            match_score=float(item.get("match_score", 0.0)),
            matched_span=item.get("matched_span"),
        )

    # Generic object attribute extraction (non-mutating)
    return CitationClaim(
        claim_text=str(getattr(item, "claim_text", "")),
        cited_doc_id=str(getattr(item, "cited_doc_id", "")),
        cited_page=int(getattr(item, "cited_page", 1)),
        evidence_quote=str(getattr(item, "evidence_quote", "")),
        verification_status=str(getattr(item, "verification_status", "UNVERIFIED")),
        cited_start_line=getattr(item, "cited_start_line", None),
        cited_end_line=getattr(item, "cited_end_line", None),
        doc_version=getattr(item, "doc_version", None),
        doc_hash=getattr(item, "doc_hash", None),
        match_score=float(getattr(item, "match_score", 0.0)),
        matched_span=getattr(item, "matched_span", None),
    )


def verify_citations(
    claims: Sequence[Union[CitationClaim, Any]],
    chunk_lookup: Dict[Any, Any],
    theta_match: float = 0.75,
) -> CitationVerificationResult:
    """
    R2 Deterministic Capability #2:
    Pure standard-library citation verifier.

    Parameters:
    - claims: Sequence of CitationClaim or objects with citation attributes.
    - chunk_lookup: Mapping from (doc_id, page_number) to:
        * str: Page text content (standard format).
        * dict: Rich provenance dict with keys 'text', 'total_lines', 'doc_version', 'doc_hash'.
    - theta_match: Minimum threshold for Token-LCS / fuzzy overlap (default 0.75).

    Returns:
    - CitationVerificationResult containing validated_claims, hallucination_flags, and grounding_score.
    """
    validated: List[CitationClaim] = []
    flagged: List[CitationClaim] = []
    verified_count = 0

    # Index known docs for doc_id existence checks (supports case-insensitive & extension-tolerant matching)
    known_doc_ids = set()
    known_doc_ids_lower = {}
    for k in chunk_lookup.keys():
        if isinstance(k, tuple) and len(k) >= 1:
            doc_str = str(k[0])
            known_doc_ids.add(doc_str)
            known_doc_ids_lower[doc_str.lower()] = doc_str
        elif isinstance(k, str):
            known_doc_ids.add(k)
            known_doc_ids_lower[k.lower()] = k

    for raw_c in claims:
        c = _to_claim_dataclass(raw_c)

        # 1. Document Existence Check with flexible case & extension resolution
        resolved_doc_id = None
        if c.cited_doc_id in known_doc_ids:
            resolved_doc_id = c.cited_doc_id
        elif c.cited_doc_id.lower() in known_doc_ids_lower:
            resolved_doc_id = known_doc_ids_lower[c.cited_doc_id.lower()]
        elif (c.cited_doc_id.lower() + ".pdf") in known_doc_ids_lower:
            resolved_doc_id = known_doc_ids_lower[c.cited_doc_id.lower() + ".pdf"]
        elif "." in c.cited_doc_id and c.cited_doc_id.rsplit(".", 1)[0].lower() in known_doc_ids_lower:
            resolved_doc_id = known_doc_ids_lower[c.cited_doc_id.rsplit(".", 1)[0].lower()]

        if not resolved_doc_id:
            c.verification_status = "INVALID_DOC_ID"
            c.match_score = 0.0
            flagged.append(c)
            continue

        key = (c.cited_doc_id, c.cited_page)
        if key not in chunk_lookup:
            key = (resolved_doc_id, c.cited_page)
        if key not in chunk_lookup:
            key = (c.cited_doc_id.lower(), c.cited_page)

        # 2. Page Existence Check
        if key not in chunk_lookup:
            c.verification_status = "INVALID_SOURCE_PAGE"
            c.match_score = 0.0
            flagged.append(c)
            continue

        entry = chunk_lookup[key]
        if isinstance(entry, dict):
            source_text = entry.get("text") or entry.get("full_page_text", "")
            total_lines = entry.get("total_lines")
            entry_version = entry.get("doc_version") or entry.get("version_id")
            entry_hash = entry.get("doc_hash")
        else:
            source_text = str(entry)
            total_lines = None
            entry_version = None
            entry_hash = None

        # 3. Line Range Validity Check
        if c.cited_start_line is not None and c.cited_end_line is not None:
            if c.cited_start_line <= 0 or c.cited_end_line < c.cited_start_line:
                c.verification_status = "INVALID_LINE_RANGE"
                c.match_score = 0.0
                flagged.append(c)
                continue
            if total_lines is not None and c.cited_end_line > total_lines:
                c.verification_status = "LINE_OUT_OF_RANGE"
                c.match_score = 0.0
                flagged.append(c)
                continue

        # 4. Version & Hash Provenance Check
        if c.doc_version and entry_version and c.doc_version != entry_version:
            c.verification_status = "VERSION_MISMATCH"
            c.match_score = 0.0
            flagged.append(c)
            continue

        if c.doc_hash and entry_hash and c.doc_hash != entry_hash:
            c.verification_status = "HASH_MISMATCH"
            c.match_score = 0.0
            flagged.append(c)
            continue

        # 5. Evidence Quotation Match
        norm_source = _normalize_text(source_text)
        norm_quote = _normalize_text(c.evidence_quote)

        if not norm_quote:
            c.verification_status = "UNGROUNDED_QUOTE"
            c.match_score = 0.0
            flagged.append(c)
            continue

        # Step 5A: Exact normalized substring match
        if norm_quote in norm_source:
            c.verification_status = "VERIFIED_EXACT"
            c.match_score = 1.0
            c.matched_span = c.evidence_quote
            verified_count += 1
            validated.append(c)
            continue

        # Step 5B: Token-LCS match
        q_tokens = _tokenize(norm_quote)
        s_tokens = _tokenize(norm_source)
        lcs_ratio = _token_lcs_ratio(q_tokens, s_tokens)

        if lcs_ratio >= theta_match:
            c.verification_status = "VERIFIED_FUZZY"
            c.match_score = round(lcs_ratio, 4)
            c.matched_span = c.evidence_quote
            verified_count += 1
            validated.append(c)
            continue

        # Step 5C: Fallback Token Overlap
        overlap = _token_overlap_ratio(q_tokens, s_tokens)
        if overlap >= theta_match:
            c.verification_status = "VERIFIED_FUZZY"
            c.match_score = round(overlap, 4)
            c.matched_span = c.evidence_quote
            verified_count += 1
            validated.append(c)
        else:
            c.verification_status = "UNGROUNDED_QUOTE"
            c.match_score = round(max(lcs_ratio, overlap), 4)
            flagged.append(c)

    score = round(verified_count / max(1, len(claims)), 4)
    return CitationVerificationResult(
        validated_claims=validated,
        hallucination_flags=flagged,
        grounding_score=score,
    )
