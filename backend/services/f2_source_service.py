"""F2 source preparation over an explicitly supplied backend repository.

No parser, LLM, workspace singleton, persistence or action dispatch lives here.
The caller supplies server-resolved access context; this is not authentication.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import re
from typing import Literal, Protocol

from pydantic import ValidationError

from backend.algorithms.f2_source_extraction import StudySpanKind, extract_contextual_study_spans
from backend.algorithms.f2_content_support import LearningObjective, build_learning_objectives
from backend.core.f2_study_schemas import SourceRef, StudySourceSelection
from backend.core.guardrails import detect_prompt_injection
from backend.core.schemas import DocumentChunk, DocumentMetadata


class StudySourceRepository(Protocol):
    # Read stored metadata directly: list_documents() can synthesize legacy
    # metadata from orphan chunks and cannot serve as independent source truth.
    @property
    def documents(self) -> Mapping[str, DocumentMetadata]: ...

    def get_document_chunks(self, doc_id: str) -> Sequence[DocumentChunk]: ...


@dataclass(frozen=True)
class SourceAccessContext:
    """Backend-resolved workspace and allowed document IDs; never client truth."""

    workspace_id: str
    allowed_doc_ids: frozenset[str]

    def __post_init__(self) -> None:
        ids = self.allowed_doc_ids
        if not _valid_id(self.workspace_id) or not isinstance(ids, frozenset):
            raise ValueError("expected a workspace ID and frozen allowed document IDs")
        if any(not _valid_id(doc_id) for doc_id in ids):
            raise ValueError("allowed document IDs must be exact nonblank strings")


@dataclass(frozen=True)
class StudySourcePassage:
    kind: StudySpanKind
    source_ref: SourceRef

    @property
    def text(self) -> str:
        return self.source_ref.evidence_quote


@dataclass(frozen=True)
class SourceContentIssue:
    doc_id: str
    code: Literal["NO_USABLE_CONTENT", "SUSPICIOUS_SOURCE_CONTENT"]
    message: str
    chunk_id: str | None = None


@dataclass(frozen=True)
class PreparedStudySources:
    workspace_id: str
    selection: StudySourceSelection
    passages: tuple[StudySourcePassage, ...]
    issues: tuple[SourceContentIssue, ...]

    @property
    def learning_objectives(self) -> tuple[LearningObjective, ...]:
        return build_learning_objectives(tuple((f"S{i}", p.text) for i, p in enumerate(self.passages, 1)))

    @property
    def status(self) -> Literal["READY", "PARTIAL", "INSUFFICIENT_CONTENT"]:
        if not self.passages:
            return "INSUFFICIENT_CONTENT"
        return "PARTIAL" if self.issues else "READY"

    @property
    def message(self) -> str:
        if self.status == "INSUFFICIENT_CONTENT":
            return "Không đủ nội dung sử dụng được. Vui lòng thêm hoặc chọn tài liệu khác có lớp văn bản."
        if self.status == "PARTIAL":
            return "Đã lấy được nội dung từ một phần nguồn. Hãy xem cảnh báo và bổ sung hoặc chọn lại tài liệu nếu cần."
        return "Đã tìm thấy nội dung ôn tập từ các tài liệu đã chọn."


@dataclass(frozen=True)
class SourceChunkPreview:
    chunk_id: str
    page_number: int
    start_line: int
    end_line: int
    text: str
    excluded_as_suspicious: bool


@dataclass(frozen=True)
class SourceDocumentPreview:
    doc_id: str
    doc_name: str
    doc_version: str
    doc_hash: str
    page_numbers: tuple[int, ...]
    text_character_count: int
    usable_passage_count: int
    category_counts: tuple[tuple[str, int], ...]
    chunks: tuple[SourceChunkPreview, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class SourceInspection:
    workspace_id: str
    selection: StudySourceSelection
    documents: tuple[SourceDocumentPreview, ...]


class SourcePreparationError(ValueError):
    def __init__(self, code: str, message: str, doc_ids: tuple[str, ...] = ()):
        super().__init__(message)
        self.code = code
        self.doc_ids = doc_ids


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _metadata_signature(metadata: DocumentMetadata) -> tuple:
    # Explicit request selection does not depend on mutable UI is_selected.
    return (
        metadata.doc_id, metadata.doc_name, metadata.file_type,
        metadata.version_id, metadata.file_hash, metadata.chunk_count,
        metadata.page_count, metadata.total_lines,
    )


def _boundary_pipe_padding_agrees(a: str, a_chunk: DocumentChunk, b: str, b_chunk: DocumentChunk,
                                  line_number: int) -> bool:
    """Recognize only the existing ingestion join/strip artifact on pipe rows.

    The shared cleaner joins pipe cells with surrounding ASCII spaces; the
    chunker strips the whole window, trimming only its first/last line. Keep
    repository text and citation quotes verbatim. Internal whitespace, words,
    operators, units, indentation outside pipe margins and locators are not
    normalized or repaired here.
    """
    if a == b:
        return True
    core = a.strip(" \t")
    if not core or core != b.strip(" \t"):
        return False
    a_left, b_left = len(a) - len(a.lstrip(" \t")), len(b) - len(b.lstrip(" \t"))
    a_right, b_right = len(a) - len(a.rstrip(" \t")), len(b) - len(b.rstrip(" \t"))
    if a[:a_left] != b[:b_left]:
        if not core.startswith("|") or not (
            (a_left == 0 and line_number == a_chunk.start_line)
            or (b_left == 0 and line_number == b_chunk.start_line)
        ):
            return False
    if (a[len(a) - a_right:] if a_right else "") != (b[len(b) - b_right:] if b_right else ""):
        if not core.endswith("|") or not (
            (a_right == 0 and line_number == a_chunk.end_line)
            or (b_right == 0 and line_number == b_chunk.end_line)
        ):
            return False
    return True


class F2SourceService:
    def __init__(self, repository: StudySourceRepository):
        self.repository = repository

    def _metadata(self, doc_id: str) -> DocumentMetadata:
        record = self.repository.documents.get(doc_id)
        if record is None:
            raise SourcePreparationError(
                "SOURCE_NOT_FOUND", "Tài liệu đã chọn không còn tồn tại. Vui lòng chọn lại nguồn.", (doc_id,)
            )
        try:
            metadata = DocumentMetadata.model_validate(record.model_dump(), strict=True)
        except (ValidationError, AttributeError) as error:
            raise SourcePreparationError(
                "INVALID_PROVENANCE", "Metadata nguồn không hợp lệ. Vui lòng nạp lại tài liệu.", (doc_id,)
            ) from error
        if (
            metadata.doc_id != doc_id or not _valid_id(metadata.version_id)
            or not re.fullmatch(r"[0-9a-f]{64}", metadata.file_hash)
            or metadata.chunk_count < 0 or metadata.page_count < 0 or metadata.total_lines < 0
            or (metadata.chunk_count > 0 and (metadata.page_count == 0 or metadata.total_lines == 0))
        ):
            raise SourcePreparationError(
                "INVALID_PROVENANCE",
                "Thiếu hoặc sai định danh, version/hash nguồn. Vui lòng nạp lại tài liệu.", (doc_id,),
            )
        return metadata

    def _chunks(self, metadata: DocumentMetadata) -> tuple[DocumentChunk, ...]:
        doc_id = metadata.doc_id
        try:
            # Shared retrieval accepts name/case aliases. Discard them before
            # validation; do not inspect, emit or use their content as context.
            records = self.repository.get_document_chunks(doc_id)
            chunks = tuple(
                DocumentChunk.model_validate(record.model_dump(), strict=True)
                for record in records if getattr(record, "doc_id", None) == doc_id
            )
        except (ValidationError, AttributeError) as error:
            raise SourcePreparationError(
                "INVALID_PROVENANCE", "Dữ liệu đoạn nguồn không hợp lệ. Vui lòng nạp lại tài liệu.", (doc_id,)
            ) from error
        except Exception as error:
            raise SourcePreparationError(
                "SOURCE_READ_FAILED", "Không đọc được nguồn. Vui lòng thử lại hoặc chọn tài liệu khác.", (doc_id,)
            ) from error
        if len(chunks) != metadata.chunk_count:
            raise SourcePreparationError(
                "SOURCE_INCONSISTENT", "Số đoạn nguồn không khớp metadata. Vui lòng nạp lại tài liệu.", (doc_id,)
            )
        ids: set[str] = set()
        lines: dict[tuple[int, int], list[tuple[str, DocumentChunk]]] = {}
        for chunk in chunks:
            if (
                not _valid_id(chunk.chunk_id) or chunk.chunk_id in ids
                or chunk.doc_version != metadata.version_id or chunk.doc_hash != metadata.file_hash
                or chunk.doc_name != metadata.doc_name or chunk.page_number < 1
                or chunk.start_line < 1 or chunk.end_line < chunk.start_line
            ):
                raise SourcePreparationError(
                    "SOURCE_INCONSISTENT",
                    "Định danh, version/hash hoặc vị trí đoạn nguồn không nhất quán. Vui lòng nạp lại tài liệu.",
                    (doc_id,),
                )
            ids.add(chunk.chunk_id)
            if not chunk.text.strip():
                continue
            physical_lines = chunk.text.splitlines()
            if len(physical_lines) != chunk.end_line - chunk.start_line + 1:
                raise SourcePreparationError(
                    "INVALID_PROVENANCE", "Nội dung không khớp vị trí dòng. Vui lòng nạp lại tài liệu.", (doc_id,)
                )
            for offset, line in enumerate(physical_lines, chunk.start_line):
                key = (chunk.page_number, offset)
                for previous, previous_chunk in lines.get(key, ()):
                    if not _boundary_pipe_padding_agrees(previous, previous_chunk, line, chunk, offset):
                        raise SourcePreparationError(
                            "SOURCE_INCONSISTENT",
                            f"Các đoạn nguồn chồng lấp có nội dung khác nhau trong '{metadata.doc_name}', "
                            f"trang {chunk.page_number}, dòng {offset} "
                            f"({previous_chunk.chunk_id} / {chunk.chunk_id}). Vui lòng nạp lại tài liệu.", (doc_id,),
                        )
                lines.setdefault(key, []).append((line, chunk))
        return tuple(sorted(chunks, key=lambda c: (c.page_number, c.start_line, c.end_line, c.chunk_id)))

    def inspect_sources(self, selection: StudySourceSelection, *, context: SourceAccessContext) -> SourceInspection:
        """Read-only, exact-scoped extraction preview. Not OCR or a quality proof.

        Uses the same validated metadata/chunk loader as preparation. Warnings
        describe observable symptoms; a PDF's original formulas/images cannot
        be certified from extracted text. Preview does not call an AI provider.
        """
        try:
            selection = StudySourceSelection.model_validate(selection)
        except ValidationError as error:
            raise SourcePreparationError("INVALID_SELECTION", "Lựa chọn nguồn không hợp lệ.") from error
        try:
            if not isinstance(context, SourceAccessContext):
                raise ValueError("missing backend context")
            context = SourceAccessContext(context.workspace_id, context.allowed_doc_ids)
        except (ValueError, AttributeError) as error:
            raise SourcePreparationError("INVALID_CONTEXT", "Thiếu phạm vi nguồn hợp lệ do backend cung cấp.") from error
        denied = tuple(d for d in selection.selected_doc_ids if d not in context.allowed_doc_ids)
        if denied:
            raise SourcePreparationError("FORBIDDEN_SOURCE", "Nguồn không thuộc phạm vi workspace được phép.", denied)
        metadata = tuple(self._metadata(d) for d in selection.selected_doc_ids)
        documents = []
        for document in metadata:
            previews, categories, seen, lines = [], {}, set(), {}
            for chunk in self._chunks(document):
                suspicious, _ = detect_prompt_injection(chunk.text)
                previews.append(SourceChunkPreview(chunk.chunk_id, chunk.page_number,
                    chunk.start_line, chunk.end_line, chunk.text, suspicious))
                for offset, line in enumerate(chunk.text.splitlines(), chunk.start_line):
                    lines[(chunk.page_number, offset)] = line
                if suspicious:
                    continue
                for span in extract_contextual_study_spans(chunk.text):
                    key = (chunk.page_number, chunk.start_line + span.start_line - 1,
                           chunk.start_line + span.end_line - 1, span.text)
                    if key not in seen:
                        seen.add(key)
                        categories[span.kind.value] = categories.get(span.kind.value, 0) + 1
            text = "\n".join(lines[k] for k in sorted(lines))
            warnings = []
            if document.file_type.lower() == "pdf":
                warnings.append("Đây là lớp chữ đã trích từ PDF; hãy đối chiếu bản gốc để kiểm tra công thức, bảng và hình. Chưa có OCR/đối chiếu hình ảnh.")
            if not seen:
                warnings.append("Không có đoạn nào đạt quy tắc chuẩn bị nguồn hiện tại. Văn bản bên dưới vẫn cho biết ứng dụng đã đọc được gì.")
            if len(text.strip()) < 80:
                warnings.append("Lượng chữ trích xuất ít; hãy kiểm tra các trang và nội dung gốc.")
            if "\ufffd" in text or any(0xE000 <= ord(c) <= 0xF8FF for c in text):
                warnings.append("Có ký tự thay thế hoặc ký tự font riêng; công thức/ký hiệu có thể cần kiểm tra thủ công.")
            visible = [c for c in text if not c.isspace()]
            if len(visible) >= 20 and sum(not c.isalnum() for c in visible) / len(visible) > .3:
                warnings.append("Văn bản có nhiều ký hiệu. Chưa thể kết luận công thức đã được trích đúng.")
            if any(p.excluded_as_suspicious for p in previews):
                warnings.append("Có đoạn chứa chỉ thị đáng ngờ; đoạn đó không được đưa vào sinh học liệu.")
            documents.append(SourceDocumentPreview(document.doc_id, document.doc_name, document.version_id,
                document.file_hash, tuple(sorted({p.page_number for p in previews})), len(text), len(seen),
                tuple(sorted(categories.items())), tuple(previews), tuple(warnings)))
        for document in metadata:
            try:
                current = self._metadata(document.doc_id)
            except SourcePreparationError as error:
                raise SourcePreparationError("SOURCE_CHANGED", "Nguồn thay đổi trong khi xem; hãy tải lại nội dung.") from error
            if _metadata_signature(current) != _metadata_signature(document):
                raise SourcePreparationError("SOURCE_CHANGED", "Nguồn thay đổi trong khi xem; hãy tải lại nội dung.")
        return SourceInspection(context.workspace_id, selection, tuple(documents))

    def prepare_sources(
        self, selection: StudySourceSelection, *, context: SourceAccessContext
    ) -> PreparedStudySources:
        """Resolve exact scoped sources into immutable, unverified study passages.

        READY means usable spans exist, not enough supported items for the
        requested_count. Generation/semantic checks follow in Q03–Q05. Metadata
        is checked again before returning, without claiming an atomic DB read.
        """
        try:
            selection = StudySourceSelection.model_validate(selection)
        except ValidationError as error:
            raise SourcePreparationError("INVALID_SELECTION", "Lựa chọn nguồn hoặc định dạng học không hợp lệ.") from error
        if not isinstance(context, SourceAccessContext):
            raise SourcePreparationError("INVALID_CONTEXT", "Thiếu phạm vi nguồn được backend cho phép.")
        denied = tuple(
            doc_id for doc_id in selection.selected_doc_ids if doc_id not in context.allowed_doc_ids
        )
        if denied:
            raise SourcePreparationError(
                "FORBIDDEN_SOURCE", "Nguồn đã chọn không thuộc phạm vi workspace được phép.", denied
            )
        metadata = tuple(self._metadata(doc_id) for doc_id in selection.selected_doc_ids)
        passages: list[StudySourcePassage] = []
        issues: list[SourceContentIssue] = []
        seen: set[tuple] = set()
        for document in metadata:
            first = len(passages)
            for chunk in self._chunks(document):
                suspicious, _ = detect_prompt_injection(chunk.text)
                if suspicious:
                    issues.append(SourceContentIssue(
                        document.doc_id, "SUSPICIOUS_SOURCE_CONTENT",
                        "Đã bỏ qua đoạn có chỉ thị đáng ngờ; hãy chọn nguồn khác hoặc kiểm tra lại tài liệu.",
                        chunk.chunk_id,
                    ))
                    continue
                for span in extract_contextual_study_spans(chunk.text):
                    start = chunk.start_line + span.start_line - 1
                    end = chunk.start_line + span.end_line - 1
                    key = (document.doc_id, chunk.page_number, start, end, span.text)
                    if key in seen:
                        continue
                    seen.add(key)
                    ref = SourceRef(
                        doc_id=document.doc_id, doc_version=document.version_id,
                        doc_hash=document.file_hash, page_number=chunk.page_number,
                        chunk_id=chunk.chunk_id, start_line=start, end_line=end,
                        evidence_quote=span.text,
                    )
                    passages.append(StudySourcePassage(span.kind, ref))
            if len(passages) == first:
                issues.append(SourceContentIssue(
                    document.doc_id, "NO_USABLE_CONTENT",
                    "Không tìm thấy khái niệm hoặc thông tin sử dụng được; hãy bổ sung/chọn tài liệu khác có lớp văn bản.",
                ))
        for document in metadata:
            try:
                current = self._metadata(document.doc_id)
            except SourcePreparationError as error:
                raise SourcePreparationError(
                    "SOURCE_CHANGED", "Nguồn thay đổi trong khi đọc. Vui lòng chọn lại tài liệu và thử lại.",
                    (document.doc_id,),
                ) from error
            if _metadata_signature(current) != _metadata_signature(document):
                raise SourcePreparationError(
                    "SOURCE_CHANGED", "Nguồn thay đổi trong khi đọc. Vui lòng chọn lại tài liệu và thử lại.",
                    (document.doc_id,),
                )
        return PreparedStudySources(context.workspace_id, selection, tuple(passages), tuple(issues))


__all__ = [
    "StudySourceRepository", "SourceAccessContext", "StudySourcePassage",
    "SourceContentIssue", "PreparedStudySources", "SourcePreparationError", "F2SourceService",
    "SourceChunkPreview", "SourceDocumentPreview", "SourceInspection",
]
