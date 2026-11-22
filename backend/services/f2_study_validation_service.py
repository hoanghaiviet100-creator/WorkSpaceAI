"""Q05 fail-closed gate over trusted, current, scoped repository evidence.

Receipts are internal point-in-time results, not authorization tokens. Callers
must validate again at use after edits/source changes; no atomic read or raw
file-hash recomputation is claimed. No routes, grading or persistence here.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json

from pydantic import ValidationError

from backend.algorithms.f2_content_support import (
    CARD_CLOZE_PREFIX, QUIZ_CLOZE_PREFIX, learning_question_kind,
    validate_flashcard_content_support, validate_quiz_content_support,
)
from backend.core.f2_study_schemas import FlashcardDeck, QuizSet, StudyFormat
from backend.core.f2_validation_schemas import StudyItemValidation, StudyValidationIssue, StudyValidationResult
from backend.core.guardrails import detect_prompt_injection
from backend.services.f2_source_service import (
    F2SourceService, PreparedStudySources, SourceAccessContext, SourcePreparationError, StudySourceRepository,
)


class StudyValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _digest(data: object) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def study_resource_digest(resource: QuizSet | FlashcardDeck) -> str:
    """Bind an internal receipt to the entire revalidated resource, including key."""
    if not isinstance(resource, (QuizSet, FlashcardDeck)):
        raise ValueError("expected a QuizSet or FlashcardDeck")
    checked = type(resource).model_validate(resource)
    return _digest(checked.model_dump(mode="json"))


def _snapshot_digest(prepared: PreparedStudySources) -> str:
    return _digest({
        "workspace_id": prepared.workspace_id,
        "selection": prepared.selection.model_dump(mode="json"),
        "passages": [{"kind": p.kind.value, "source_ref": p.source_ref.model_dump(mode="json")}
                     for p in prepared.passages],
        "issues": [asdict(issue) for issue in prepared.issues],
    })


def _issue(code: str, message: str, *, reject: bool = False) -> StudyValidationIssue:
    return StudyValidationIssue(code=code, message=message, severity="REJECTED" if reject else "REVIEW_REQUIRED")


class F2StudyValidationService:
    def __init__(self, repository: StudySourceRepository):
        self.sources = F2SourceService(repository)

    def validate_quiz(self, quiz: QuizSet, *, workspace_id: str, context: SourceAccessContext) -> StudyValidationResult:
        return self._validate(quiz, QuizSet, StudyFormat.QUIZ, workspace_id, context)

    def validate_flashcards(self, deck: FlashcardDeck, *, workspace_id: str, context: SourceAccessContext) -> StudyValidationResult:
        return self._validate(deck, FlashcardDeck, StudyFormat.FLASHCARDS, workspace_id, context)

    def _validate(self, resource, model, study_format, workspace_id, context):
        # A request workspace ID is not authority. Reconstruct even a tampered
        # dataclass before any repository access; the resolver stays external.
        try:
            if not isinstance(context, SourceAccessContext):
                raise ValueError("missing context")
            context = SourceAccessContext(context.workspace_id, context.allowed_doc_ids)
        except (ValueError, AttributeError) as error:
            raise StudyValidationError("INVALID_CONTEXT", "Thiếu phạm vi nguồn hợp lệ do backend cung cấp.") from error
        if not isinstance(workspace_id, str) or workspace_id != context.workspace_id:
            raise StudyValidationError("WORKSPACE_MISMATCH", "Workspace học liệu không khớp phạm vi backend.")
        try:
            checked = model.model_validate(resource)
        except ValidationError:
            return StudyValidationResult(
                workspace_id=workspace_id, study_format=study_format, structure_status="INVALID",
                issues=(_issue("INVALID_RESOURCE", "Cấu trúc học liệu không hợp lệ; hãy tạo lại.", reject=True),),
            )
        resource_id = checked.quiz_set_id if model is QuizSet else checked.deck_id
        digest = study_resource_digest(checked)
        entries = checked.questions if model is QuizSet else checked.cards
        global_issues = []
        try:
            current = self.sources.prepare_sources(checked.selection, context=context)
        except SourcePreparationError as error:
            global_issues.append(_issue(error.code, str(error), reject=True))
            current = None
        except Exception:
            global_issues.append(_issue("SOURCE_READ_FAILED", "Không đọc được nguồn hiện tại; vui lòng thử lại.", reject=True))
            current = None
        results = []
        if current is not None:
            snapshot_digest = _snapshot_digest(current)
            aliases = {p.source_ref: f"S{i}" for i, p in enumerate(current.passages, 1)}
            all_sources = tuple((aliases[p.source_ref], p.text) for p in current.passages)
            for source_issue in current.issues:
                global_issues.append(_issue(source_issue.code, source_issue.message))
            for entry in entries:
                item_id = entry.question_id if model is QuizSet else entry.card_id
                if any(ref not in aliases for ref in entry.source_refs):
                    results.append(StudyItemValidation(
                        item_id=item_id, source_status="FAILED", support_status="NOT_CHECKED",
                        issues=(_issue("SOURCE_REF_MISMATCH", "Trích dẫn không khớp nguồn hiện tại: định danh/version/hash/vị trí hoặc nguyên văn.", reject=True),),
                    ))
                    continue
                texts = ((entry.question, entry.explanation, *(option.text for option in entry.options))
                         if model is QuizSet else (entry.front, entry.back))
                if any(detect_prompt_injection(text)[0] for text in texts):
                    results.append(StudyItemValidation(
                        item_id=item_id, source_status="MATCHED", support_status="REJECTED",
                        issues=(_issue("SUSPICIOUS_ITEM_CONTENT", "Học liệu chứa chỉ thị đáng ngờ; hãy tạo lại.", reject=True),),
                    ))
                    continue
                cited = tuple((aliases[ref], ref.evidence_quote) for ref in entry.source_refs)
                if model is QuizSet:
                    decision = validate_quiz_content_support(entry.question,
                        tuple((o.option_id, o.text) for o in entry.options), entry.correct_option_id,
                        entry.explanation, cited, all_sources)
                else:
                    decision = validate_flashcard_content_support(entry.front, entry.back, cited, all_sources)
                issues = () if decision.status == "SUPPORTED" else (
                    _issue(decision.code, decision.message, reject=decision.status == "REJECTED"),)
                results.append(StudyItemValidation(item_id=item_id, source_status="MATCHED",
                    support_status=decision.status, issues=issues))
            # Observe all selected sources a second time, including uncited
            # definitions that may disambiguate answers. Detect visible changes
            # without claiming transactional isolation or permanent freshness.
            try:
                after = self.sources.prepare_sources(checked.selection, context=context)
                if _snapshot_digest(after) != snapshot_digest:
                    raise SourcePreparationError("SOURCE_CHANGED", "Nguồn thay đổi trong khi kiểm chứng; hãy thử lại.")
            except SourcePreparationError as error:
                global_issues.append(_issue("SOURCE_CHANGED", str(error), reject=True))
            except Exception:
                global_issues.append(_issue("SOURCE_READ_FAILED", "Không đọc lại được nguồn; hãy thử lại.", reject=True))
        else:
            snapshot_digest = None
            results = [StudyItemValidation(
                item_id=e.question_id if model is QuizSet else e.card_id,
                source_status="NOT_CHECKED", support_status="NOT_CHECKED") for e in entries]

        # Imported Q01 resources can bypass generation dedup/count policies.
        prompts = [" ".join((e.question if model is QuizSet else e.front).split()).casefold() for e in entries]
        if len(prompts) != len(set(prompts)):
            global_issues.append(_issue("DUPLICATE_OR_CONFLICTING_ITEMS", "Có câu hỏi/mặt trước trùng nhau; cần review và tạo lại."))
        if len(entries) > checked.selection.requested_count:
            global_issues.append(_issue("EXCESS_ITEMS", "Số học liệu vượt lựa chọn ban đầu; cần tạo lại đúng số lượng."))
        return StudyValidationResult(
            workspace_id=workspace_id, study_format=study_format, resource_id=resource_id,
            resource_digest=digest, source_snapshot_digest=snapshot_digest, structure_status="VALID",
            method=("EXTRACTIVE_STUDY_V2" if any(
                (e.question if model is QuizSet else e.front).strip().startswith((QUIZ_CLOZE_PREFIX, CARD_CLOZE_PREFIX))
                or learning_question_kind(e.question if model is QuizSet else e.front)
                for e in entries) else "EXTRACTIVE_DEFINITION_V1"),
            items=tuple(results), issues=tuple(global_issues),
        )
