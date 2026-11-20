"""Common F2 generation input/JSON boundaries; not authorization or grounding."""
from __future__ import annotations

import json

from pydantic import ValidationError

from backend.algorithms.f2_source_extraction import StudySpanKind
from backend.core.f2_study_schemas import SourceRef, StudyFormat, StudySourceSelection
from backend.providers.f2_study_provider import MAX_STUDY_RESPONSE_BYTES, StudyEvidence
from backend.services.f2_source_service import PreparedStudySources, SourceContentIssue, StudySourcePassage


class StudyGenerationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("non-JSON numeric constant")


def parse_generation_items(raw: str, root_field: str) -> list:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_STUDY_RESPONSE_BYTES:
        raise ValueError("invalid response type or size")
    data = json.loads(raw, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_constant)
    if not isinstance(data, dict) or set(data) != {root_field} or not isinstance(data[root_field], list):
        raise ValueError("expected only the requested item array")
    return data[root_field]


def prepare_generation_snapshot(
    prepared: PreparedStudySources, required_format: StudyFormat,
) -> tuple[StudySourceSelection, tuple[StudyEvidence, ...]]:
    if not isinstance(prepared, PreparedStudySources):
        raise StudyGenerationError("INVALID_PREPARED_SOURCES", "Cần dữ liệu nguồn đã được chuẩn bị hợp lệ.")
    try:
        selection = StudySourceSelection.model_validate(prepared.selection)
        if (
            not isinstance(prepared.workspace_id, str) or not prepared.workspace_id.strip()
            or prepared.workspace_id != prepared.workspace_id.strip()
        ):
            raise ValueError("workspace ID required")
        if not isinstance(prepared.passages, tuple) or not isinstance(prepared.issues, tuple):
            raise ValueError("immutable source collections required")
        evidence = []
        snapshots = {}
        seen = set()
        for passage in prepared.passages:
            if not isinstance(passage, StudySourcePassage) or not isinstance(passage.kind, StudySpanKind):
                raise ValueError("invalid source passage")
            ref = SourceRef.model_validate(passage.source_ref)
            if ref.doc_id not in selection.selected_doc_ids:
                raise ValueError("source outside selection")
            if len(ref.evidence_quote.splitlines()) != ref.end_line - ref.start_line + 1:
                raise ValueError("inconsistent source line span")
            identity = (ref.doc_version, ref.doc_hash)
            if ref.doc_id in snapshots and snapshots[ref.doc_id] != identity:
                raise ValueError("conflicting source snapshots")
            snapshots[ref.doc_id] = identity
            if ref in seen:
                continue
            seen.add(ref)
            evidence.append(StudyEvidence(f"S{len(evidence) + 1}", passage.kind.value, ref))
        for issue in prepared.issues:
            if not isinstance(issue, SourceContentIssue) or issue.doc_id not in selection.selected_doc_ids:
                raise ValueError("invalid source issue")
    except (ValidationError, ValueError, TypeError, AttributeError) as error:
        raise StudyGenerationError("INVALID_PREPARED_SOURCES", "Dữ liệu nguồn không hợp lệ; vui lòng chọn lại tài liệu.") from error
    if selection.study_format != required_format:
        label = "Quiz" if required_format == StudyFormat.QUIZ else "Flashcards"
        code = "QUIZ_FORMAT_REQUIRED" if required_format == StudyFormat.QUIZ else "FLASHCARDS_FORMAT_REQUIRED"
        raise StudyGenerationError(code, f"Yêu cầu này cần chọn định dạng {label}.")
    return selection, tuple(evidence)


def resolve_source_ids(ids: object, by_id: dict[str, SourceRef]) -> tuple[SourceRef, ...]:
    if not isinstance(ids, list) or not ids or any(not isinstance(s, str) or s not in by_id for s in ids):
        raise ValueError("unknown or missing source ID")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate source ID")
    return tuple(by_id[source_id] for source_id in ids)


__all__ = ["StudyGenerationError", "parse_generation_items", "prepare_generation_snapshot", "resolve_source_ids"]
