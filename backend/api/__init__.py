from backend.api.chat_routes import handle_user_request, router as chat_router
from backend.api.document_routes import router as document_router
from backend.api.email_routes import approve_email, router as email_router

__all__ = [
    "chat_router",
    "document_router",
    "email_router",
    "handle_user_request",
    "approve_email",
]
