import re
from typing import List, Optional, Tuple
from backend.schemas import RouteType, UserRequest

INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"system\s+override",
    r"disregard\s+safeguards",
    r"send\s+all\s+workspace\s+files\s+to",
]

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def detect_prompt_injection(text: str) -> Tuple[bool, Optional[str]]:
    """R7 Safeguard: Scans user input or untrusted document chunks for injection patterns."""
    normalized = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, normalized):
            return True, f"Matched restricted security pattern: {pattern}"
    return False, None


def wrap_untrusted_chunk(doc_name: str, page: int, raw_text: str) -> str:
    """R7 Data-Instruction Separation: Encapsulates document text in passive XML tags."""
    sanitized = raw_text.replace("</untrusted_document_data>", "")
    return (
        f'<untrusted_document_data source="{doc_name}" page="{page}">\n'
        f"{sanitized}\n"
        f"</untrusted_document_data>"
    )


def validate_email_address(email: Optional[str]) -> bool:
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def route_user_request(req: UserRequest) -> Tuple[RouteType, List[str]]:
    """
    R5 Explicit Router & Slot-Filling Gate:
    Decides whether request goes to QA, RECONCILE, EMAIL, CLARIFICATION, or REJECTED_SAFEGUARD.
    """
    is_injected, reason = detect_prompt_injection(req.query)
    if is_injected:
        return RouteType.REJECTED_SAFEGUARD, [reason or "Prompt injection detected"]

    q = req.query.lower()
    missing_slots: List[str] = []

    if any(k in q for k in ["email", "mail", "send", "draft", "gửi mail", "nháp"]):
        if not validate_email_address(req.recipient_email):
            extracted_emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", req.query)
            if not extracted_emails:
                missing_slots.append("recipient_email")
        if len(q.split()) < 5:
            missing_slots.append("email_topic_or_scope")

        if missing_slots:
            return RouteType.CLARIFICATION_FLOW, missing_slots
        return RouteType.EMAIL_FLOW, []

    if any(k in q for k in ["compare", "reconcile", "overdue", "conflict", "extract", "table", "đối chiếu", "trễ hạn"]):
        return RouteType.RECONCILE_FLOW, []

    return RouteType.QA_FLOW, []
