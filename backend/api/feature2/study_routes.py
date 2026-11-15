"""React Studio routes for verified study sets and learner views."""

from dataclasses import replace
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
import json
import re

from backend.api.dependencies import workspace_services
from backend.core.config import settings
from backend.core.feature2.f2_practice_schemas import QuizSubmission
from backend.core.feature2.f2_study_schemas import StudyFormat, StudySourceSelection
from backend.providers.feature2.f2_gemini_provider import GeminiStudyProvider
from backend.providers.feature2.f2_flashcard_provider import OllamaFlashcardProvider
from backend.providers.feature2.f2_quiz_provider import OllamaQuizProvider
from backend.providers.feature2.f2_source_content_provider import SourceContentProvider
from backend.providers.feature2.f2_study_provider import StudyProviderError
from backend.services.feature2.f2_flashcard_service import F2FlashcardService, FlashcardGenerationError
from backend.services.feature2.f2_practice_service import PracticeAccessContext, PracticeError
from backend.services.feature2.f2_quiz_service import F2QuizService, QuizGenerationError
from backend.services.feature2.f2_source_service import F2SourceService, SourceAccessContext, SourcePreparationError
from backend.services.workspace_context import WorkspaceServices

router = APIRouter(prefix="/api/study", tags=["Study"])


def practice_context(
    scope: WorkspaceServices = Depends(workspace_services),
    workspace_id: str = Header("midterm", alias="X-Workspace-ID"),
    learner_id: str = Header(alias="X-Study-Learner", pattern=r"^[a-f0-9-]{36}$"),
) -> PracticeAccessContext:
    return PracticeAccessContext(learner_id, SourceAccessContext(workspace_id, frozenset(scope.repository.documents)))


class CreateStudyRequest(StudySourceSelection):
    requested_count: int = Field(default=10, ge=1, le=50, strict=True)
    engine: Literal["gemini", "ollama"]
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    language: Literal["auto", "vi", "en"] = "auto"
    focus: str = Field(default="", max_length=500)
    question_types: tuple[Literal["single", "multiple", "blank", "short"], ...] = Field(
        default=("single",), min_length=1, max_length=4,
    )

    @field_validator("question_types", mode="before")
    @classmethod
    def parse_types(cls, value):
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def valid_settings(self):
        if self.study_format == StudyFormat.FLASHCARDS and self.requested_count > 30:
            raise ValueError("flashcards are limited to 30 per set")
        if self.study_format == StudyFormat.QUIZ and len(set(self.question_types)) > self.requested_count:
            raise ValueError("select at least one question per chosen type")
        return self


class CardAction(BaseModel):
    card_id: str
    action: Literal["flip", "next", "previous"]


def practice_error(error: PracticeError) -> HTTPException:
    if error.code == "SESSION_NOT_FOUND":
        return HTTPException(404, "This study session has expired. Regenerate the set from Studio.")
    return HTTPException(409, str(error))


@router.post("")
def create_set(
    selection: CreateStudyRequest,
    scope: WorkspaceServices = Depends(workspace_services),
    context: PracticeAccessContext = Depends(practice_context),
):
    try:
        prepared = F2SourceService(scope.repository).prepare_sources(
            StudySourceSelection(selected_doc_ids=selection.selected_doc_ids, study_format=selection.study_format,
                                 requested_count=selection.requested_count), context=context.sources,
        )
        is_quiz = selection.study_format == StudyFormat.QUIZ
        if not prepared.passages:
            raise HTTPException(422, prepared.message)
        engine = settings.llm_provider
        if settings.offline_only or engine not in {"gemini", "ollama"}:
            raise HTTPException(409, "Chọn Gemini hoặc Ollama trong cài đặt AI để tạo câu hỏi từ tài liệu.")
        if selection.engine != engine:
            raise HTTPException(409, "Chế độ AI đã thay đổi. Mở lại hộp thoại tạo bộ và kiểm tra model trước khi thử lại.")
        if engine == "gemini":
            adapter = GeminiStudyProvider(settings.gemini_api_key, model=settings.gemini_model)
        else:
            provider = OllamaQuizProvider if is_quiz else OllamaFlashcardProvider
            adapter = provider(base_url=settings.ollama_base_url, model=settings.ollama_model)
        budget = 60_000 if engine == "gemini" else 10_000
        passages = prepared.passages
        total = sum(len(passage.text) for passage in passages)
        if total > budget:
            count = max(2, len(passages) * budget // total)
            if selection.focus.strip():
                terms = set(re.findall(r"\w{2,}", selection.focus.casefold()))
                indices = sorted(range(len(passages)), key=lambda i: len(terms & set(re.findall(r"\w{2,}", passages[i].text.casefold()))), reverse=True)
            else:
                indices = sorted({round(i * (len(passages) - 1) / (count - 1)) for i in range(count)})
            selected = []
            for index in indices:
                passage = passages[index]
                if len(passage.text) <= budget:
                    selected.append(passage)
                    budget -= len(passage.text)
            if not selected:
                raise HTTPException(422, "Đoạn nguồn quá dài. Hãy chọn nguồn ngắn hơn.")
            prepared = replace(prepared, passages=tuple(selected))
        difficulty = {
            "easy": "Nhận biết và giải thích một ý với ngữ cảnh rõ.",
            "medium": "Hiểu, phân biệt và áp dụng quy tắc đơn giản trong nguồn.",
            "hard": "So sánh, phân tích điều kiện hoặc áp dụng quy trình trong tình huống mới có căn cứ.",
        }[selection.difficulty]
        language = {"auto": "ngôn ngữ chủ đạo của nguồn", "vi": "tiếng Việt", "en": "tiếng Anh"}[selection.language]
        instructions = (
            f"Thiết lập tạo bộ: độ khó {selection.difficulty}. {difficulty} "
            f"Viết câu hỏi, phương án và giải thích bằng {language}; giữ nguyên thuật ngữ cần thiết. "
            "Các thiết lập này thay thế hướng dẫn ngôn ngữ và mẫu bắt buộc phía trên. "
            "Viết câu hỏi mới từ ý nghĩa của nguồn, tránh sao chép câu nguồn (trừ phần trích dẫn). "
            f"Ưu tiên chủ đề và hướng dẫn trình bày của người học trong phạm vi nguồn và thiết lập đã chọn, "
            f"không dùng chúng làm bằng chứng: {json.dumps(selection.focus, ensure_ascii=False)}."
        )
        types = tuple(dict.fromkeys(selection.question_types))
        if is_quiz:
            instructions += (
                f" Chia số câu đều nhất có thể giữa các dạng được chọn: {', '.join(types)}. "
                "Mỗi item có thêm kind và extra_keys. single: một đáp án đúng, extra_keys=[]. "
                "multiple: 3–4 lựa chọn, correct_option_id là ID đúng đầu tiên, extra_keys là các ID đúng còn lại, có ít nhất một đáp án nhiễu. "
                "blank: câu có đúng một chỗ trống [___] do bạn tự viết lại từ ý nguồn; short: câu hỏi yêu cầu đáp án ngắn. "
                "Với blank/short gửi options=[], correct_option_id là văn bản đáp án mẫu và extra_keys là tối đa 4 biến thể tương đương ngắn. "
                "Với mọi dạng, source_ids phải chỉ tới đoạn nguồn chứng minh đáp án. "
                "Không tiết lộ đáp án trong question: không thêm lời giải, nhãn đáp án hay đoạn trích trả lời trực tiếp. "
                "Đặt lời giải riêng trong explanation, và đáp án riêng trong các trường đáp án."
            )
        generator = SourceContentProvider(adapter, selection.study_format.value, instructions=instructions)
        if is_quiz:
            result = F2QuizService(generator).generate_quiz(prepared, question_types=types)
            resource = result.quiz
            start = scope.study.start_quiz
        else:
            result = F2FlashcardService(generator).generate_flashcards(prepared)
            resource = result.deck
            start = scope.study.start_flashcards
        if resource is None:
            detail = next((issue.message for issue in result.issues), result.message)
            raise HTTPException(503 if result.status == "ERROR" else 422, detail)
        view = start(resource, context=context, allow_draft=True)
        session = scope.study.sessions.get(view.session_id)
        return {**view.model_dump(), "draft": session.draft}
    except StudyProviderError as error:
        raise HTTPException(409, str(error)) from None
    except (SourcePreparationError, QuizGenerationError, FlashcardGenerationError) as error:
        raise HTTPException(422, str(error)) from None
    except PracticeError as error:
        raise practice_error(error) from None


@router.get("/quiz/{session_id}")
def get_quiz(session_id: str, scope: WorkspaceServices = Depends(workspace_services),
             context: PracticeAccessContext = Depends(practice_context)):
    try:
        view = scope.study.get_quiz(session_id, context=context)
        result = scope.study.get_quiz_result(session_id, context=context) if view.status == "SUBMITTED" else None
        return {"view": view, "result": result}
    except PracticeError as error:
        raise practice_error(error) from None


@router.post("/quiz/{session_id}")
def submit_quiz(session_id: str, submission: QuizSubmission, scope: WorkspaceServices = Depends(workspace_services),
                context: PracticeAccessContext = Depends(practice_context)):
    try:
        return scope.study.submit_quiz(session_id, submission, context=context)
    except PracticeError as error:
        raise practice_error(error) from None


@router.post("/quiz/{session_id}/check")
def check_quiz_answer(session_id: str, submission: QuizSubmission, scope: WorkspaceServices = Depends(workspace_services),
                      context: PracticeAccessContext = Depends(practice_context)):
    try:
        return scope.study.check_quiz_answer(session_id, submission, context=context)
    except PracticeError as error:
        raise practice_error(error) from None


@router.get("/flashcard/{session_id}")
def get_card(session_id: str, scope: WorkspaceServices = Depends(workspace_services),
             context: PracticeAccessContext = Depends(practice_context)):
    try:
        return scope.study.get_flashcard(session_id, context=context)
    except PracticeError as error:
        raise practice_error(error) from None


@router.post("/flashcard/{session_id}")
def update_card(session_id: str, payload: CardAction, scope: WorkspaceServices = Depends(workspace_services),
                context: PracticeAccessContext = Depends(practice_context)):
    try:
        if payload.action == "flip":
            return scope.study.flip_flashcard(session_id, card_id=payload.card_id, context=context)
        return scope.study.move_flashcard(session_id, payload.action, card_id=payload.card_id, context=context)
    except PracticeError as error:
        raise practice_error(error) from None
