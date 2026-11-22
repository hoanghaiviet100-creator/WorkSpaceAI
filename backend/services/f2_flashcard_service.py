"""Internal F2 Flashcard generation; structural checks, not semantic validation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from backend.algorithms.f2_flashcard_generation import DEFAULT_MAX_BACK_WORDS
from backend.core.f2_study_schemas import Flashcard, FlashcardDeck, StudyFormat, StudySourceSelection
from backend.providers.f2_flashcard_provider import (
    DeterministicFlashcardProvider, FlashcardGenerationProvider, FlashcardProviderError,
)
from backend.services.f2_generation_support import (
    StudyGenerationError, parse_generation_items, prepare_generation_snapshot, resolve_source_ids,
)
from backend.services.f2_source_service import PreparedStudySources, SourceContentIssue


@dataclass(frozen=True)
class FlashcardGenerationIssue:
    code: str
    message: str
    card_index: int | None = None


@dataclass(frozen=True)
class FlashcardGenerationResult:
    workspace_id: str
    selection: StudySourceSelection
    deck: FlashcardDeck | None
    provider_name: str
    issues: tuple[FlashcardGenerationIssue, ...] = ()
    source_issues: tuple[SourceContentIssue, ...] = ()
    failed: bool = False

    @property
    def status(self) -> Literal["COMPLETE", "PARTIAL", "INSUFFICIENT_CONTENT", "ERROR"]:
        if self.failed:
            return "ERROR"
        if self.deck is None:
            return "INSUFFICIENT_CONTENT"
        if len(self.deck.cards) < self.selection.requested_count or self.issues or self.source_issues:
            return "PARTIAL"
        return "COMPLETE"

    @property
    def message(self) -> str:
        if self.status == "ERROR":
            return "Không tạo được flashcards hợp lệ. Vui lòng thử lại hoặc chọn nguồn khác."
        if self.deck is None:
            return "Chưa đủ nội dung để tạo flashcards ngắn gọn. Vui lòng bổ sung hoặc chọn tài liệu khác."
        count = len(self.deck.cards)
        if self.status == "PARTIAL":
            return f"Đã tạo {count}/{self.selection.requested_count} flashcards. Hãy xem cảnh báo hoặc bổ sung nguồn. Nội dung chưa được kiểm chứng."
        return f"Đã tạo {count} flashcards. Nội dung chưa được kiểm chứng."


class FlashcardGenerationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class F2FlashcardService:
    def __init__(
        self, provider: FlashcardGenerationProvider | None = None,
        *, fallback_provider: FlashcardGenerationProvider | None = None,
        max_back_words: int = DEFAULT_MAX_BACK_WORDS,
    ):
        if type(max_back_words) is not int or max_back_words < 1:
            raise ValueError("max_back_words must be a positive integer")
        self.max_back_words = max_back_words
        self.provider = provider if provider is not None else DeterministicFlashcardProvider(max_back_words=max_back_words)
        self.fallback_provider = fallback_provider

    def generate_flashcards(self, prepared: PreparedStudySources) -> FlashcardGenerationResult:
        """Generate bounded front/back cards with references hydrated by backend.

        The local default for concise answers is 60 whitespace-separated words;
        it is configurable generation policy, not a new Q01 schema restriction.
        Longer answers are omitted, never silently cut into incomplete claims.
        """
        try:
            selection, evidence = prepare_generation_snapshot(prepared, StudyFormat.FLASHCARDS)
        except StudyGenerationError as error:
            raise FlashcardGenerationError(error.code, str(error)) from error
        provider = self.provider
        issues: list[FlashcardGenerationIssue] = []

        def result(deck=None, *, failed=False):
            return FlashcardGenerationResult(
                prepared.workspace_id, selection, deck, provider.name,
                tuple(issues), prepared.issues, failed,
            )

        if not evidence:
            issues.append(FlashcardGenerationIssue("INSUFFICIENT_SOURCE_CONTENT", prepared.message))
            return result()
        try:
            raw = provider.generate(evidence, selection.requested_count)
        except FlashcardProviderError as error:
            if self.fallback_provider is None or error.code not in ("PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE"):
                issues.append(FlashcardGenerationIssue(error.code, str(error)))
                return result(failed=True)
            issues.append(FlashcardGenerationIssue("FALLBACK_USED", "Dịch vụ chính không khả dụng; đã dùng chế độ sinh flashcards dự phòng."))
            provider = self.fallback_provider
            try:
                raw = provider.generate(evidence, selection.requested_count)
            except Exception:
                issues.append(FlashcardGenerationIssue("FALLBACK_FAILED", "Chế độ dự phòng không tạo được flashcards."))
                return result(failed=True)
        except Exception:
            issues.append(FlashcardGenerationIssue("PROVIDER_FAILED", "Dịch vụ sinh flashcards gặp lỗi; vui lòng thử lại."))
            return result(failed=True)
        try:
            drafts = parse_generation_items(raw, "cards")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            issues.append(FlashcardGenerationIssue("INVALID_PROVIDER_OUTPUT", "Phản hồi sinh flashcards không hợp lệ; đã dừng sử dụng phản hồi này."))
            return result(failed=True)
        if not drafts:
            issues.append(FlashcardGenerationIssue("INSUFFICIENT_GENERATABLE_CONTENT", "Chưa đủ nội dung để tạo flashcards ngắn gọn; hãy bổ sung hoặc chọn tài liệu khác."))
            return result()
        by_id = {item.source_id: item.source_ref for item in evidence}
        candidates: dict[str, tuple[int, Flashcard]] = {}
        conflicts: set[str] = set()
        for index, draft in enumerate(drafts, 1):
            try:
                if not isinstance(draft, dict) or set(draft) != {"front", "back", "source_ids"}:
                    raise ValueError("unexpected card fields")
                card = Flashcard(
                    card_id=f"candidate-{index}", front=draft["front"], back=draft["back"],
                    source_refs=resolve_source_ids(draft["source_ids"], by_id),
                )
                if len(card.back.split()) > self.max_back_words:
                    issues.append(FlashcardGenerationIssue("ANSWER_TOO_LONG", "Đã bỏ flashcard có câu trả lời quá dài; không cắt mất nội dung.", index))
                    continue
                key = " ".join(card.front.split()).casefold()
                if key in candidates:
                    previous = candidates[key][1]
                    if " ".join(previous.back.split()).casefold() != " ".join(card.back.split()).casefold():
                        conflicts.add(key)
                        issues.append(FlashcardGenerationIssue("CONFLICTING_CARD", "Đã bỏ các flashcards cùng prompt nhưng có đáp án mâu thuẫn.", index))
                    else:
                        issues.append(FlashcardGenerationIssue("DUPLICATE_CARD", "Đã bỏ flashcard trùng nội dung.", index))
                    continue
                candidates[key] = (index, card)
            except (ValidationError, ValueError, TypeError):
                issues.append(FlashcardGenerationIssue("INVALID_CARD", "Đã bỏ flashcard thiếu front/back hoặc nguồn hợp lệ.", index))
        accepted = [item for key, item in candidates.items() if key not in conflicts]
        if len(accepted) > selection.requested_count:
            issues.append(FlashcardGenerationIssue("EXCESS_ITEMS_IGNORED", "Đã bỏ các flashcards vượt số lượng yêu cầu.", accepted[selection.requested_count][0]))
        cards = tuple(
            Flashcard(card_id=f"c{index}", front=card.front, back=card.back, source_refs=card.source_refs)
            for index, (_, card) in enumerate(accepted[:selection.requested_count], 1)
        )
        if not cards:
            issues.append(FlashcardGenerationIssue("NO_VALID_CARDS", "Không có flashcard nào qua kiểm tra cấu trúc, độ ngắn và snapshot nguồn."))
            return result(failed=True)
        deck = FlashcardDeck(deck_id=str(uuid4()), selection=selection, cards=cards)
        if len(cards) < selection.requested_count:
            issues.append(FlashcardGenerationIssue("FEWER_CARDS_THAN_REQUESTED", "Số flashcards hợp lệ ít hơn yêu cầu; không sinh bù thông tin thiếu."))
        return result(deck)


__all__ = ["FlashcardGenerationIssue", "FlashcardGenerationResult", "FlashcardGenerationError", "F2FlashcardService"]
