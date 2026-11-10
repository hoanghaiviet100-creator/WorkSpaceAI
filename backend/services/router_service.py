import re
from typing import List, Tuple
from backend.core.guardrails import detect_prompt_injection, validate_email_address
from backend.core.schemas import RouteType, UserRequest


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
    # Explicit Studio actions reuse the same guarded services without guessing from goal text.
    if req.studio_tool == "plan":
        return RouteType.QA_FLOW, []

    email_keywords = [
        "email", "mail", "send", "draft", "gửi mail", "nháp",
        "soạn mail", "viết mail", "soạn thư", "viết thư", "gửi thư",
    ]
    if req.studio_tool == "email" or any(re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", q) for k in email_keywords):
        if not validate_email_address(req.recipient_email):
            extracted_emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", req.query)
            if extracted_emails:
                req.recipient_email = extracted_emails[0]
            else:
                missing_slots.append("recipient_email")
        if len(q.split()) < 4:
            missing_slots.append("email_topic_or_scope")

        if missing_slots:
            return RouteType.CLARIFICATION_FLOW, missing_slots
        return RouteType.EMAIL_FLOW, []


    if any(re.search(r"(?<!\w)" + re.escape(k) + r"(?!\w)", q) for k in ["compare", "reconcile", "overdue", "conflict", "extract", "table", "đối chiếu", "trễ hạn"]):
        return RouteType.RECONCILE_FLOW, []

    return RouteType.QA_FLOW, []
