"""
backend/algorithms/email_state_machine.py
R2 Deterministic Capability #3: Email State Machine & Anti-Tamper Verification.
100% Python Standard Library Only (Zero third-party imports).
"""
import hashlib
import re
from typing import Any, List


class SecurityError(Exception):
    """Raised when email payload integrity verification fails or tamper is detected."""
    pass


def _validate_email(email: str) -> bool:
    """Pure standard-library RFC-5322 basic format validation."""
    if not email or not isinstance(email, str):
        return False
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()))


def compute_draft_hash(recipient: str, subject: str, body: str, attachments: List[str]) -> str:
    """Computes SHA-256 hash over normalized email draft fields."""
    raw = f"{recipient.strip()}|{subject.strip()}|{body.strip()}|{','.join(sorted(attachments))}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def prepare_draft_for_approval(draft: Any) -> Any:
    """
    Validates recipient email address, transitions draft to PENDING_APPROVAL,
    and locks in the draft SHA-256 integrity hash.
    Works with both dicts and objects with attributes.
    """
    recipient = getattr(draft, "recipient_email", None) or (draft.get("recipient_email") if isinstance(draft, dict) else "")
    subject = getattr(draft, "subject", None) or (draft.get("subject") if isinstance(draft, dict) else "")
    body = getattr(draft, "body", None) or (draft.get("body") if isinstance(draft, dict) else "")
    attachments = getattr(draft, "attachment_ids", None) or (draft.get("attachment_ids") if isinstance(draft, dict) else [])
    if attachments is None:
        attachments = []

    if not _validate_email(recipient):
        raise ValueError(f"Invalid RFC-5322 recipient email: {recipient}")

    payload_hash = compute_draft_hash(recipient, subject, body, attachments)

    if isinstance(draft, dict):
        draft["state"] = "PENDING_APPROVAL"
        draft["payload_hash"] = payload_hash
    else:
        # Check if state is Enum or str
        state_attr = getattr(draft, "state", None)
        if state_attr is not None and hasattr(state_attr, "__class__") and hasattr(state_attr.__class__, "PENDING_APPROVAL"):
            draft.state = state_attr.__class__.PENDING_APPROVAL
        else:
            draft.state = "PENDING_APPROVAL"
        draft.payload_hash = payload_hash

    return draft


def approve_and_verify_email_send(
    stored_draft: Any,
    approved_recipient: str,
    approved_subject: str,
    approved_body: str,
    approved_attachments: List[str],
    user_confirmed: bool,
) -> Any:
    """
    R2 Deterministic Capability #3:
    Enforces strict state transition PENDING_APPROVAL -> APPROVED and checks SHA-256 integrity.
    """
    if not user_confirmed:
        raise PermissionError("Email send blocked: explicit human approval flag is False.")

    draft_state = getattr(stored_draft, "state", None) or (stored_draft.get("state") if isinstance(stored_draft, dict) else "")
    state_str = getattr(draft_state, "value", str(draft_state))

    if state_str != "PENDING_APPROVAL":
        raise RuntimeError(f"Invalid FSM transition from state {state_str} to APPROVED.")

    if not _validate_email(approved_recipient):
        raise ValueError(f"Invalid recipient email address: {approved_recipient}")

    incoming_hash = compute_draft_hash(
        approved_recipient, approved_subject, approved_body, approved_attachments or []
    )
    expected_hash = getattr(stored_draft, "payload_hash", None) or (stored_draft.get("payload_hash") if isinstance(stored_draft, dict) else "")

    if incoming_hash != expected_hash:
        raise SecurityError("Payload hash mismatch! Draft was modified without re-staging approval.")

    if isinstance(stored_draft, dict):
        stored_draft["state"] = "APPROVED"
    else:
        state_attr = getattr(stored_draft, "state", None)
        if state_attr is not None and hasattr(state_attr, "__class__") and hasattr(state_attr.__class__, "APPROVED"):
            stored_draft.state = state_attr.__class__.APPROVED
        else:
            stored_draft.state = "APPROVED"

    return stored_draft
