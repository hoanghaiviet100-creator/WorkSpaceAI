"""Package for deterministic R2 pure Python algorithms."""
from typing import Any

__all__ = [
    "reconcile_requirements_and_tasks",
    "CitationClaim",
    "CitationVerificationResult",
    "verify_citations",
    "compute_draft_hash",
    "prepare_draft_for_approval",
    "approve_and_verify_email_send",
    "SecurityError",
]


def __getattr__(name: str) -> Any:
    if name in ("CitationClaim", "CitationVerificationResult", "verify_citations"):
        from backend.algorithms import citation_verifier
        return getattr(citation_verifier, name)
    if name in (
        "SecurityError",
        "approve_and_verify_email_send",
        "compute_draft_hash",
        "prepare_draft_for_approval",
    ):
        from backend.algorithms import email_state_machine
        return getattr(email_state_machine, name)
    if name == "reconcile_requirements_and_tasks":
        from backend.algorithms import reconciliation
        return getattr(reconciliation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
