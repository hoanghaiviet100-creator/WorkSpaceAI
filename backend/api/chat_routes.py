from fastapi import APIRouter
from backend.core.schemas import RouteType, UserRequest
from backend.services.email_service import email_service
from backend.services.qa_service import qa_service
from backend.services.reconciliation_service import reconciliation_service
from backend.services.router_service import route_user_request

router = APIRouter(prefix="/api", tags=["Chat & Orchestration"])


@router.post("/chat")
def handle_user_request(req: UserRequest):
    """
    POST /api/chat
    Router endpoint: Receives user request, classifies route, and delegates to corresponding service.
    """
    route, missing_slots = route_user_request(req)

    if route == RouteType.REJECTED_SAFEGUARD:
        return {
            "route": route,
            "status": "BLOCKED_BY_SAFEGUARD",
            "message": "Request blocked by R7 Prompt-Injection / Security Safeguard.",
            "details": missing_slots,
        }

    if route == RouteType.CLARIFICATION_FLOW:
        return {
            "route": route,
            "status": "AWAITING_CLARIFICATION",
            "message": f"Please clarify the following missing information before proceeding: {', '.join(missing_slots)}",
            "missing_slots": missing_slots,
        }

    if route == RouteType.QA_FLOW:
        return qa_service.answer_question(query=req.query)

    if route == RouteType.RECONCILE_FLOW:
        return reconciliation_service.reconcile(reference_date=req.reference_date)

    if route == RouteType.EMAIL_FLOW:
        return email_service.create_draft(req)

    return {
        "route": route,
        "status": "UNKNOWN_ROUTE",
        "message": "No matching handler found for request.",
    }


# Alias for backward-compatibility and clean route API
handle_chat = handle_user_request
