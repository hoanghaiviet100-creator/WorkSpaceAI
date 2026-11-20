"""Review generated claims against the excerpts that passed citation matching."""

import re

from backend.core.config import settings
from backend.core.schemas import CitationVerificationResult, GeneratedClaim
from backend.providers.llm_provider import LLMProvider


UNCONDITIONAL_DOMAIN = re.compile(
    r"(?:miền|tập)\s+xác định\s+(?:luôn\s+)?(?:là|bằng)\s+(?:toàn bộ|cả)\s+(?:mặt phẳng|không gian|trục số)"
    r"|\bdomain\s+(?:is|equals)\s+(?:the\s+)?(?:entire|whole)\s+(?:plane|space|real line)",
    re.I,
)
DEFINED_POINTS = re.compile(r"có nghĩa|where (?:it|the expression) is defined", re.I)
EXPLICIT_DOMAIN = re.compile(r"\bD\s*=\s*(?:\\mathbb\{R\}|ℝ|R)(?:\s*(?:\^\{?[23]\}?|[²³23]))?(?![\w^])")


def support_review_enabled() -> bool:
    return (
        settings.feature1_semantic_verify
        and not settings.offline_only
        and settings.llm_provider in {"ollama", "gemini"}
    )


def review_claims(
    provider: LLMProvider, claims: list[GeneratedClaim],
) -> tuple[list[GeneratedClaim], list[GeneratedClaim]]:
    """Keep supported claims and fail closed on missing or invalid verdicts."""
    if not support_review_enabled():
        return claims, []
    accepted, rejected = [], []
    batch: dict[str, dict[str, str]] = {}
    candidates: dict[str, GeneratedClaim] = {}
    size = 0

    def flush() -> None:
        if not batch:
            return
        verdicts = provider.judge_claim_support(batch)
        for key in batch:
            verdict = verdicts.get(key, "UNAVAILABLE")
            claim = candidates[key].model_copy(update={"semantic_status": verdict})
            if verdict == "SUPPORTED":
                accepted.append(claim)
            else:
                rejected.append(claim.model_copy(update={"verification_status": f"SEMANTIC_{verdict}"}))
        batch.clear()

    for index, claim in enumerate(claims):
        evidence = claim.matched_span or claim.evidence_quote
        if (
            UNCONDITIONAL_DOMAIN.search(claim.claim_text) and DEFINED_POINTS.search(evidence)
            and not UNCONDITIONAL_DOMAIN.search(evidence) and not EXPLICIT_DOMAIN.search(evidence)
        ):
            rejected.append(claim.model_copy(update={
                "semantic_status": "INSUFFICIENT", "verification_status": "SEMANTIC_INSUFFICIENT",
            }))
            continue
        length = len(evidence) + len(claim.claim_text)
        if length > 10_000:
            rejected.append(claim.model_copy(update={
                "semantic_status": "UNAVAILABLE", "verification_status": "SEMANTIC_UNAVAILABLE",
            }))
            continue
        if len(batch) >= 5 or size + length > 10_000:
            flush()
            size = 0
        key = str(index + 1)
        batch[key] = {"claim": claim.claim_text, "evidence": evidence}
        candidates[key] = claim
        size += length
    flush()
    return accepted, rejected


def review_verification(provider: LLMProvider, result: CitationVerificationResult) -> None:
    """Update the verified answer without changing the existing API shape."""
    accepted, rejected = review_claims(provider, result.validated_claims)
    if rejected:
        result.hallucination_flags.extend(rejected)
        result.validated_claims = accepted
        total = len(accepted) + len(result.hallucination_flags)
        result.grounding_score = round(len(accepted) / total, 4)
    else:
        result.validated_claims = accepted
