"""Package for deterministic R2 pure Python standard-library algorithms."""
from typing import Any

__all__ = [
    # Citation Verifier (Feature 1)
    "CitationClaim",
    "CitationVerificationResult",
    "verify_citations",
    # Cross-Document Reconciliation (Feature 2)
    "reconcile_requirements_and_tasks",
    "ReconciliationSummary",
    "ReconciledItemReport",
    "DateConflict",
    # Email FSM & Integrity Gate (Feature 3)
    "DRAFT",
    "APPROVED",
    "SENT",
    "FAILED",
    "DELIVERY_UNKNOWN",
    "ALL_FSM_STATES",
    "SecurityError",
    "FSMStateError",
    "validate_rfc5322_email",
    "compute_draft_hash",
    "approve_snapshot",
    "verify_and_lock_for_send",
]


def __getattr__(name: str) -> Any:
    if name in ("CitationClaim", "CitationVerificationResult", "verify_citations"):
        from backend.algorithms import citation_verifier
        return getattr(citation_verifier, name)
    if name in (
        "DRAFT",
        "APPROVED",
        "SENT",
        "FAILED",
        "DELIVERY_UNKNOWN",
        "ALL_FSM_STATES",
        "SecurityError",
        "FSMStateError",
        "validate_rfc5322_email",
        "compute_draft_hash",
        "approve_snapshot",
        "verify_and_lock_for_send",
    ):
        from backend.algorithms import email_state_machine
        return getattr(email_state_machine, name)
    if name in (
        "reconcile_requirements_and_tasks",
        "ReconciliationSummary",
        "ReconciledItemReport",
        "DateConflict",
    ):
        from backend.algorithms import reconciliation
        return getattr(reconciliation, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
