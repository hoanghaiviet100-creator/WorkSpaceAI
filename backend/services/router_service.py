import re
import unicodedata
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

    # Chuẩn hóa Unicode sang NFC để bàn phím gõ tiếng Việt tổ hợp (NFD) không làm sai lệch chuỗi
    q = unicodedata.normalize("NFC", req.query.lower())
    missing_slots: List[str] = []

    # Danh sách các mẫu câu thể hiện hành động soạn/gửi email rõ ràng
    email_action_patterns = [
        r"\bsoạn mail\b", r"\bviết mail\b", r"\bgửi mail\b", r"\btạo mail\b",
        r"\bsoạn thư\b", r"\bviết thư\b", r"\bgửi thư\b", r"\btạo thư\b",
        r"\bsoạn email\b", r"\bviết email\b", r"\bgửi email\b", r"\btạo email\b",
        r"\bdraft email\b", r"\bsend email\b", r"\bemail draft\b", r"\bdraft an email\b",
        r"\bnháp\b", r"\bdraft\b",
    ]
    # Câu hỏi bản chất khái niệm/định nghĩa về email hoặc giao thức (ví dụ: "giao thức là gì", "email là gì")
    is_concept_question = bool(
        re.search(r"\b(là gì|la gi|thế nào|như thế nào|dùng để|định nghĩa|khái niệm|giải thích|tìm hiểu)\b", q)
    )

    is_email_intent = (
        getattr(req, "studio_tool", None) == "email"
        or any(re.search(pat, q) for pat in email_action_patterns)
        or (
            any(re.search(rf"\b{k}\b", q) for k in ["email", "mail", "send"])
            and not is_concept_question
        )
    )

    if is_email_intent:
        if not validate_email_address(req.recipient_email):
            extracted_emails = re.findall(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", req.query)
            if extracted_emails:
                req.recipient_email = extracted_emails[0]
            else:
                missing_slots.append("recipient_email")

        # Nếu có lịch sử hội thoại trước đó (ví dụ vừa tóm tắt xong) hoặc qua giao diện email chuyên dụng,
        # cho phép hệ thống tự động kế thừa chủ đề từ ngữ cảnh mà không bắt ép người dùng nhập lại.
        has_context = bool(req.conversation_history) or bool(getattr(req, "studio_tool", None))
        if len(q.split()) < 4 and not has_context:
            missing_slots.append("email_topic_or_scope")

        if missing_slots:
            return RouteType.CLARIFICATION_FLOW, missing_slots
        return RouteType.EMAIL_FLOW, []

    if getattr(req, "allow_reconciliation", True) and any(
        k in q for k in ["compare", "reconcile", "overdue", "conflict", "extract", "table", "đối chiếu", "trễ hạn"]
    ):
        return RouteType.RECONCILE_FLOW, []

    return RouteType.QA_FLOW, []
