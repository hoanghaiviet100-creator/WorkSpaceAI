import hashlib
from typing import List
from backend.core.guardrails import validate_email_address
from backend.core.schemas import EmailDraftPayload, EmailState


class SecurityError(Exception):
    """Raised when email payload integrity verification fails or tamper is detected."""
    pass


def compute_draft_hash(recipient: str, subject: str, body: str, attachments: List[str]) -> str:
    """Computes SHA-256 hash over normalized email draft fields."""
    raw = f"{recipient.strip()}|{subject.strip()}|{body.strip()}|{','.join(sorted(attachments))}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def prepare_draft_for_approval(draft: EmailDraftPayload) -> EmailDraftPayload:
    """
    Validates recipient email address, transitions draft to PENDING_APPROVAL,
    and locks in the draft SHA-256 integrity hash.
    """
    if not validate_email_address(draft.recipient_email):
        raise ValueError(f"Invalid RFC-5322 recipient email: {draft.recipient_email}")
    draft.state = EmailState.PENDING_APPROVAL
    draft.payload_hash = compute_draft_hash(
        draft.recipient_email, draft.subject, draft.body, draft.attachment_ids
    )
    return draft


def approve_and_verify_email_send(
    stored_draft: EmailDraftPayload,
    approved_recipient: str,
    approved_subject: str,
    approved_body: str,
    approved_attachments: List[str],
    user_confirmed: bool,
) -> EmailDraftPayload:
    """
    R2 Deterministic Capability #3:
    Enforces strict state transition PENDING_APPROVAL -> APPROVED and checks SHA-256 integrity.
    """
    if not user_confirmed:
        raise PermissionError("Email send blocked: explicit human approval flag is False.")
    if stored_draft.state != EmailState.PENDING_APPROVAL:
        raise RuntimeError(f"Invalid FSM transition from state {stored_draft.state} to APPROVED.")
    if not validate_email_address(approved_recipient):
        raise ValueError(f"Invalid recipient email address: {approved_recipient}")

    incoming_hash = compute_draft_hash(
        approved_recipient, approved_subject, approved_body, approved_attachments
    )
    if incoming_hash != stored_draft.payload_hash:
        raise SecurityError("Payload hash mismatch! Draft was modified without re-staging approval.")

    stored_draft.state = EmailState.APPROVED
    return stored_draft
