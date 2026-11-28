from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from backend.core.schemas import RouteType, UserRequest
from backend.services.email_service import email_service
from backend.services.qa_service import qa_service
from backend.services.reconciliation_service import reconciliation_service
from backend.services.router_service import route_user_request

router = APIRouter(prefix="/api", tags=["Chat & Orchestration"])


@router.post("/chat")
def handle_user_request(req: UserRequest) -> Dict[str, Any]:
    """
    POST /api/chat
    Router endpoint: Receives user request, classifies route, and delegates to corresponding service.
    """
    if req.verification_profile == "academic_grounded" and req.studio_tool != "email":
        from backend.services.f1_basic_qa import basic_qa
        try:
            return basic_qa.answer_question(req.query, req.selected_doc_ids, req.conversation_history)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

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
        if req.verification_profile == "evidence_centric_v0":
            from backend.services.f1_evidence_profile_service import EvidenceProfileError
            try:
                return qa_service.answer_question(query=req.query,selected_doc_ids=req.selected_doc_ids,
                    conversation_history=req.conversation_history,verification_profile=req.verification_profile)
            except EvidenceProfileError as exc:
                raise HTTPException(status_code=503,detail=f"{exc}: Evidence verification is unavailable.") from exc
        return qa_service.answer_question(
            query=req.query,
            selected_doc_ids=req.selected_doc_ids,
            conversation_history=req.conversation_history,
        )

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


@router.post("/chat/stream")
async def stream_question(req: UserRequest):
    import asyncio
    import json
    import threading
    from backend.vendor.surfsense.stream import event_stream
    from backend.services.f1_basic_qa import basic_qa
    from backend.providers.llm_provider import GenerationError
    from tools.resources import AdmissionDenied
    if req.verification_profile != "academic_grounded" or req.studio_tool == "email":
        raise HTTPException(status_code=400, detail="Streaming is available for Academic Q&A.")
    async def frames():
        loop=asyncio.get_running_loop(); queue=asyncio.Queue(); cancelled=threading.Event()
        def emit(event):
            if not cancelled.is_set():
                loop.call_soon_threadsafe(queue.put_nowait,event)
        def work():
            try:
                result=basic_qa.answer_question(req.query,req.selected_doc_ids,req.conversation_history,emit,cancelled.is_set)
                emit(dict(type='result',result=result))
            except AdmissionDenied as exc:
                from backend.services.f1_session_runtime import admission_message
                from backend.services.answer_messages import failure_message
                reason=str(exc)
                code=('BUSY' if 'BUSY' in reason or 'IN_FLIGHT' in reason else
                      'RESOURCE_LIMIT' if any(s in reason for s in ('RESOURCE_ADMISSION','RESOURCE_RESERVE','NO_SAFE_APPROVED')) else
                      'GENERATION_UNAVAILABLE')
                emit(dict(type='error',code=code,message=failure_message(req.query,code)))
            except ValueError:
                from backend.services.answer_messages import failure_message
                emit(dict(type='error',code='INVALID_INPUT',message=failure_message(req.query,'INVALID_INPUT')))
            except GenerationError as exc:
                from backend.services.answer_messages import failure_message
                emit(dict(type='error',code=str(exc),message=failure_message(req.query,str(exc))))
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Document answer failed')
                from backend.services.answer_messages import failure_message
                emit(dict(type='error',code='GENERATION_FAILED',message=failure_message(req.query,'GENERATION_FAILED')))
            finally:
                emit(dict(type='done'))
        worker=asyncio.create_task(asyncio.to_thread(work))
        try:
            while True:
                try:
                    event=await asyncio.wait_for(queue.get(),timeout=10)
                except asyncio.TimeoutError:
                    yield b': keep-alive\n\n'; continue
                yield ('data: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode('utf-8')
                if event['type']=='done': break
        finally:
            cancelled.set()
    return event_stream(frames())
