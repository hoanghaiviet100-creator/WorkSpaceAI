import re
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional
from backend.algorithms.feature1.citation_verifier import (
    CitationClaim,
    CitationVerificationResult as AlgoVerificationResult,
    verify_citations,
)
from backend.algorithms.feature1.outline_builder import NUMBERED, OutlineSection, build_outline, has_damaged_text, indexed_blocks, map_packets
from backend.core.config import settings
from backend.core.schemas import CitationVerificationResult, DocumentChunk, GeneratedClaim, RouteType
from backend.providers.feature1.embedding_provider import EmbeddingProvider, embedding_provider
from backend.providers.llm_provider import GeminiRequestError, GeminiUnavailableError, LLMProvider, llm_provider
from backend.providers.prompts import requests_detailed_answer
from backend.repositories.workspace_repository import STOP_WORDS, WorkspaceRepository, workspace_repository
from backend.services.feature1.claim_support import review_verification
from backend.services.feature1.research_index import ResearchIndex
from backend.services.feature1.document_summary import (
    LONG_DOCUMENT_CHARS,
    outline_detail_parts,
    summarize_long_document,
    summarize_outline_section,
)


def claim_schema_to_algorithm(claim: GeneratedClaim) -> CitationClaim:
    """Adapts a Pydantic GeneratedClaim into a pure stdlib CitationClaim."""
    return CitationClaim(
        claim_text=claim.claim_text,
        section=claim.section,
        subsection=claim.subsection,
        cited_doc_id=claim.cited_doc_id,
        cited_page=claim.cited_page,
        evidence_quote=claim.evidence_quote,
        verification_status=claim.verification_status,
        cited_start_line=claim.cited_start_line,
        cited_end_line=claim.cited_end_line,
        doc_version=claim.doc_version,
        doc_hash=claim.doc_hash,
        match_score=claim.match_score,
        matched_span=claim.matched_span,
        semantic_status=claim.semantic_status,
    )


def claim_algorithm_to_schema(claim: CitationClaim) -> GeneratedClaim:
    """Adapts a pure stdlib CitationClaim into a Pydantic GeneratedClaim."""
    evidence_span = None
    if claim.verification_status in ("VERIFIED_EXACT", "VERIFIED_FUZZY"):
        evidence_span = {
            "doc_id": claim.cited_doc_id,
            "page": claim.cited_page,
            "start_line": claim.cited_start_line,
            "end_line": claim.cited_end_line,
            "quote": claim.evidence_quote,
            "matched_span": claim.matched_span,
            "match_score": claim.match_score,
            "doc_version": claim.doc_version,
            "doc_hash": claim.doc_hash,
        }
    return GeneratedClaim(
        claim_text=claim.claim_text,
        section=claim.section,
        subsection=claim.subsection,
        cited_doc_id=claim.cited_doc_id,
        cited_page=claim.cited_page,
        evidence_quote=claim.evidence_quote,
        verification_status=claim.verification_status,
        cited_start_line=claim.cited_start_line,
        cited_end_line=claim.cited_end_line,
        doc_version=claim.doc_version,
        doc_hash=claim.doc_hash,
        match_score=claim.match_score,
        matched_span=claim.matched_span,
        evidence_span=evidence_span,
        semantic_status=claim.semantic_status,
    )


def verification_result_to_schema(
    result: AlgoVerificationResult,
) -> CitationVerificationResult:
    """Adapts pure stdlib CitationVerificationResult into Pydantic CitationVerificationResult."""
    return CitationVerificationResult(
        validated_claims=[claim_algorithm_to_schema(c) for c in result.validated_claims],
        hallucination_flags=[claim_algorithm_to_schema(c) for c in result.hallucination_flags],
        grounding_score=result.grounding_score,
    )


REFERENCE_PRONOUNS = {"nó", "it", "them"}
REFERENCE_PHRASES = re.compile(
    r"\b(?:cái này|điều này|thứ này|phần trên|ý trên|lệnh trên|ở trên|"
    r"chi tiết hơn|nói thêm|rõ hơn|the above|tell me more)\b"
)


def is_greeting(query: str) -> bool:
    clean = re.sub(r"[.!?,]+$", "", query.strip().lower()).strip()
    return clean in {"alo", "hello", "hi", "hey", "chào", "xin chào", "chào bạn", "bạn ơi", "cảm ơn", "thanks"}


def is_detail_followup(query: str) -> bool:
    """Recognize subject-free elaboration requests, not new named topics."""
    clean = re.sub(r"[.!?]+$", "", query.strip().lower()).strip()
    clean = re.sub(r"^(?:hãy|vui lòng|bạn có thể)\s+", "", clean)
    return bool(re.fullmatch(
        r"(?:(?:mô tả|giải thích|trình bày|phân tích|nói|viết|làm rõ|explain|describe|elaborate)\s+)?"
        r"(?:(?:lại|thêm)\s+)?(?:(?:một cách|cụ thể|kỹ|rõ)\s+)?"
        r"(?:chi tiết|cụ thể|rõ|kỹ|detailed|in detail|more detail|more)"
        r"(?:\s+(?:hơn|nữa|đi|giúp tôi|cho tôi|về nó|về phần trên))*", clean
    ))


FEATURE_REFERENCE = re.compile(r"\b(?:features?|feat|tính năng|tinh nang|f)\s*[:#-]?\s*(\d+)\b", re.IGNORECASE)
FEATURE_HEADING = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)*)[.)]?\s+)?(?:feature|tính năng|tinh nang)\s*(\d+)\s*(?:[—–:-]\s*\S|$)",
    re.IGNORECASE,
)
GIT_COMMAND_LIST = re.compile(
    r"(?:(?:hãy|vui lòng|bạn có thể)\s+)?(?:(?:nêu|kể|liệt kê|cho tôi|tổng hợp)\s+)?"
    r"(?:(?:danh sách|những|các)\s+)?(?:lệnh|câu lệnh)\s+git"
    r"(?:\s+(?:quan trọng(?: nhất)?|cơ bản|phổ biến|thường dùng|chính))?"
    r"(?:\s+(?:trong|có trong)\s+(?:file|tài liệu|pdf)(?:\s+này)?)?"
    r"|(?:(?:list|show me|what are)\s+)?(?:the\s+)?"
    r"(?:(?:key|important|essential|common|basic)\s+)?git commands",
    re.IGNORECASE,
)
OUTLINE_QUESTION = re.compile(
    r"(?:(?:hãy|vui lòng)\s+)?"
    r"(?:(?:tóm tắt|tóm gọn|tóm lược|giải thích|mô tả|trình bày|nêu(?: nội dung)?|nội dung)\s+)?"
    r"(?:chương|tiểu mục|mục|phần|chapter|section)\s+(\d+(?:\.\d+)*)"
    r"(?:\s+(?:(?:đang\s+)?nói về gì|là gì|có (?:gì|nội dung gì)|gồm những gì))?"
    r"(?:\s+trong (?:tài liệu|file|pdf)(?: này)?)?",
    re.IGNORECASE,
)
OUTLINE_DETAIL_QUESTION = re.compile(
    r"(?:(?:hãy|vui lòng)\s+)?"
    r"(?:(?:nêu|giải thích|mô tả|trình bày|phân tích|cho (?:tôi|mình) biết)\s+)?"
    r"(?:(?:nội dung\s+)?chi tiết"
    r"(?:\s+(?:những gì(?:\s+có)?(?:\s+ở)?|nội dung))?"
    r"(?:\s+(?:trong|của|về))?\s+)"
    r"(?:chương|tiểu mục|mục|phần|chapter|section)\s+(\d+(?:\.\d+)*)"
    r"(?:\s+trong (?:tài liệu|file|pdf)(?: này)?)?",
    re.IGNORECASE,
)
OUTLINE_DETAIL = re.compile(
    r"(?:[.!?…,:;]\s*|\s+)(?:(?:hãy|vui lòng)\s+)?"
    r"(?:(?:giải thích|mô tả|trình bày|phân tích)\s+(?:chi tiết\s+)?)?"
    r"(?:theo\s+)?(?:từng|các)\s+(?:tiểu mục|mục con)"
    r"(?:\s+(?:trong|của)\s+(?:chương|mục|phần)(?:\s+này)?)?$",
    re.I,
)
OUTLINE_TOPICS_QUESTION = re.compile(
    r"(?:chương|tiểu mục|mục|phần)\s+(\d+(?:\.\d+)*)\s+"
    r"(?:hướng dẫn|trình bày|đề cập(?: đến)?)\s+(?:những|các)\s+"
    r"(?:thao tác|bước|chủ đề|nội dung)\s+nào(?:\s+khi làm việc với\s+.+)?",
    re.I,
)
SECTION_FOLLOWUP = re.compile(
    r"(?:(?:hãy|vui lòng)\s+)?"
    r"(?P<action>tóm tắt|tóm gọn|tóm lược|giải thích|mô tả|trình bày|phân tích)"
    r"(?:\s+(?P<detail>chi tiết))?\s+(?:chương|tiểu mục|mục|phần)\s+(?:đó|trên|vừa rồi)",
    re.I,
)
BRIEF_DOCUMENT = re.compile(r"\b(?:tóm gọn|tóm tắt ngắn(?: gọn)?|ngắn gọn|vắn tắt|brief(?:ly)?|concise)\b", re.I)
DOCUMENT_FILENAME = re.compile(r"(?<=\w)\.(?:pdf|docx?|pptx?|txt|md|csv|xlsx?)\b", re.I)
EXERCISE_REFERENCE = re.compile(r"\b(?:bài(?: tập)?(?: số)?|exercise|problem)\s+(\d{1,4})\b", re.I)
REASONING_REQUEST = re.compile(r"\b(?:so sánh|đối chiếu|mâu thuẫn|vì sao|tại sao|chứng minh|compare|contrast|conflict|why|prove)\b", re.I)
COMMAND_COMPARISON = re.compile(
    r"^\s*(?:câu )?lệnh\s+.+?\s+khác\s+.+?\s+(?:ở điểm nào|như thế nào|thế nào)[?.!]*\s*$", re.I,
)
PROCEDURAL_QUESTION = re.compile(
    r"^\s*(?:how\s+(?:do|can|should|could)\s+(?:i|we|you)|(?:câu )?lệnh nào)\s+(.+)", re.I,
)
NAMED_FOLLOWUP = re.compile(
    r"\b(?:phần|chủ đề) vừa (?:nói|trao đổi|hỏi) về\s+(.+?)(?=\s+(?:và|rồi)\s+|[?,;]|$)", re.I,
)
TOPIC_EXPLANATION = re.compile(
    r"(?:hãy\s+)?(?:giải thích|nói rõ|mô tả)(?:\s+(?:thêm|kỹ hơn|chi tiết))?\s+về\s+"
    r"(?P<topic>.+?)(?:\s+(?:và\s+)?(?:cho|nêu|đưa(?: ra)?)\s+(?:một\s+)?"
    r"(?P<example>ví dụ)(?:\s+(?:trong|từ)\s+tài liệu)?)?",
    re.I,
)
COMMAND_REFERENCE = re.compile(
    r"\b(?:command cheat sheet|git command reference|bảng tra cứu lệnh git|bảng lệnh git)\b",
    re.IGNORECASE,
)
COMMAND_LINE = re.compile(r"^(git|gh)\s+[a-z][a-z-]*\b", re.IGNORECASE)
GIT_TASK_GUIDE = {
    "what changed?": ("Luồng hằng ngày", "Kiểm tra trạng thái và xem thay đổi trước khi ghi lại"),
    "stage": ("Luồng hằng ngày", "Đưa tệp hoặc từng phần thay đổi vào staging để chuẩn bị commit"),
    "commit": ("Luồng hằng ngày", "Ghi lại các thay đổi đã stage bằng một commit có thông điệp"),
    "set identity": ("Thiết lập kho", "Cấu hình tên và email tác giả của commit"),
    "new repo": ("Thiết lập kho", "Khởi tạo kho Git trong thư mục hiện tại"),
    "copy repo": ("Thiết lập kho", "Sao chép một kho đã có về máy"),
    "new branch": ("Làm việc nhóm", "Tạo nhánh mới và chuyển sang nhánh đó"),
    "switch branch": ("Làm việc nhóm", "Chuyển sang một nhánh đã có"),
    "merge": ("Làm việc nhóm", "Gộp thay đổi từ nhánh khác vào nhánh hiện tại"),
    "rebase own branch": ("Làm việc nhóm", "Đặt lại các commit của nhánh mình trên nền origin/main"),
    "download": ("Làm việc nhóm", "Lấy cập nhật từ kho từ xa"),
    "upload": ("Làm việc nhóm", "Đẩy nhánh lên kho từ xa và thiết lập nhánh theo dõi"),
    "discard file edits": ("Sửa sai và khôi phục", "Bỏ các chỉnh sửa chưa stage của tệp"),
    "unstage": ("Sửa sai và khôi phục", "Gỡ tệp khỏi staging để điều chỉnh nội dung commit"),
    "fix last commit": ("Sửa sai và khôi phục", "Chỉnh commit gần nhất"),
    "undo pushed commit": ("Sửa sai và khôi phục", "Tạo commit đảo ngược thay đổi đã đẩy lên"),
    "park work": ("Sửa sai và khôi phục", "Cất tạm thay đổi đang làm rồi lấy lại khi cần"),
    "rescue": ("Sửa sai và khôi phục", "Tra lại các vị trí trước đây của HEAD để tìm commit cần cứu"),
    "history": ("Tra cứu và đánh dấu", "Xem lịch sử commit và quan hệ giữa các nhánh"),
    "one commit": ("Tra cứu và đánh dấu", "Xem nội dung một commit theo mã hash"),
    "who wrote a line": ("Tra cứu và đánh dấu", "Tìm commit và tác giả liên quan đến từng dòng"),
    "search history": ("Tra cứu và đánh dấu", "Tìm commit theo thay đổi nội dung hoặc thông điệp"),
    "tag milestone": ("Tra cứu và đánh dấu", "Gắn tag cho một mốc rồi đẩy tag lên kho từ xa"),
    "contributions": ("Tra cứu và đánh dấu", "Đếm commit theo tác giả, bỏ qua merge commit"),
}
GIT_GROUP_ORDER = tuple(dict.fromkeys(group for group, _ in GIT_TASK_GUIDE.values()))


def git_command_reference_claims(
    lookup: dict[tuple[str, int], dict[str, Any]], doc_ids: set[str],
) -> list[GeneratedClaim]:
    """Extract task and command pairs with exact line ranges from reference tables."""
    claims = []
    for (doc_id, page), entry in sorted(lookup.items()):
        if doc_id not in doc_ids:
            continue
        lines = entry["text"].splitlines()
        heading = next((i for i, line in enumerate(lines) if COMMAND_REFERENCE.search(line)), None)
        if heading is None:
            continue
        header = [
            (i, line.strip().casefold()) for i, line in enumerate(lines[heading + 1:], heading + 1)
            if line.strip()
        ][:2]
        if len(header) != 2 or [label for _, label in header] not in (
            ["task", "command"], ["thao tác", "lệnh"], ["tác vụ", "lệnh"],
        ):
            continue

        first_line = entry["lines"][0]
        row_start = header[-1][0] + 1
        for i in range(row_start, len(lines)):
            command = lines[i].strip()
            match = COMMAND_LINE.match(command)
            if not match:
                continue
            while row_start < i and not lines[row_start].strip():
                row_start += 1
            task = " ".join(line.strip() for line in lines[row_start:i] if line.strip())
            if match[1].casefold() == "git" and 0 < len(task.split()) <= 8:
                group, explanation = GIT_TASK_GUIDE.get(
                    task.casefold(), ("Các lệnh khác trong tài liệu", task[0].upper() + task[1:]),
                )
                claims.append(GeneratedClaim(
                    claim_text=f"{explanation} — `{command}`",
                    section=group,
                    cited_doc_id=doc_id,
                    cited_page=page,
                    cited_start_line=first_line + row_start,
                    cited_end_line=first_line + i,
                    evidence_quote="\n".join(lines[row_start:i + 1]),
                    doc_version=entry["doc_version"],
                    doc_hash=entry["doc_hash"],
                ))
            row_start = i + 1
    order = {group: index for index, group in enumerate(GIT_GROUP_ORDER)}
    return sorted(claims, key=lambda claim: order.get(claim.section, len(order)))


def find_feature_section(chunks: List[DocumentChunk], feature: str) -> List[DocumentChunk]:
    """Keep only lines under the requested heading, excluding table-of-contents entries."""
    ordered = sorted(chunks, key=lambda c: (c.doc_id, c.page_number, c.start_line or 1))
    headings = {}
    numbered = {}
    for chunk in ordered:
        for index, line in enumerate(chunk.text.splitlines(), start=chunk.start_line or 1):
            if re.search(r"(?:\.\s*){3,}|\t+\d+\s*$", line):
                continue
            position = (chunk.doc_id, chunk.page_number, index)
            heading = FEATURE_HEADING.match(line)
            if heading:
                headings[position] = (heading[2], heading[1])
            number = re.match(r"^\s*(\d+(?:\.\d+)+)\s+[^\W\d_]", line)
            if number:
                numbered[position] = number[1]

    boundaries = sorted(headings)
    selected = []
    for index, start in enumerate(boundaries):
        number, prefix = headings[start]
        if number != feature:
            continue
        end = boundaries[index + 1] if index + 1 < len(boundaries) else None
        if prefix:
            end = min((position for position, label in numbered.items()
                       if position[0] == start[0] and position > start and label != prefix
                       and not label.startswith(prefix + ".") and (end is None or position < end)), default=end)
        for chunk in ordered:
            if chunk.doc_id != start[0]:
                continue
            first = chunk.start_line or 1
            lines = chunk.text.splitlines()
            kept = [(line_no, line) for line_no, line in enumerate(lines, start=first)
                    if (chunk.doc_id, chunk.page_number, line_no) >= start
                    and (end is None or (chunk.doc_id, chunk.page_number, line_no) < end)]
            if kept:
                selected.append(chunk.model_copy(update={
                    "text": "\n".join(line for _, line in kept), "start_line": kept[0][0], "end_line": kept[-1][0],
                }))
    return selected


def expand_contextual_query(query: str, history: Optional[List[Dict[str, str]]]) -> str:
    """
    R1/R5 Deterministic Contextual Query Expansion.
    Inherit the previous topic only when the question explicitly refers back.
    """
    if not history or FEATURE_REFERENCE.search(query):
        return query

    tokens = re.findall(r"\w+", query.lower())
    q_clean = query.strip().lower()

    # Check for explicit anaphoric pronouns or follow-up phrases
    has_reference = bool(set(tokens) & REFERENCE_PRONOUNS or REFERENCE_PHRASES.search(q_clean) or NAMED_FOLLOWUP.search(query))

    # Check if query starts with a follow-up conjunction (e.g., "Còn deadline?", "Thế báo cáo?")
    is_follow_up = q_clean.startswith(("còn ", "thế còn ", "vậy còn "))

    if not (has_reference or is_follow_up or is_detail_followup(query)):
        return query

    previous = previous_question(query, history)
    return f"{previous} {query.strip()}" if previous else query


def previous_question(query: str, history: Optional[List[Dict[str, str]]]) -> str:
    topic = NAMED_FOLLOWUP.search(query)
    topic_words = (set(re.findall(r"\w+", topic[1].casefold())) - STOP_WORDS) if topic else set()
    for turn in reversed(history or []):
        if turn.get("role") != "user":
            continue
        text = (turn.get("content") or "").strip()
        if (
            not text or text.casefold() == query.strip().casefold() or is_greeting(text)
            or is_detail_followup(text) or SECTION_FOLLOWUP.fullmatch(text.rstrip(".!?…").rstrip())
        ):
            continue
        if topic_words and not topic_words <= set(re.findall(r"\w+", text.casefold())):
            continue
        return text
    return ""


def outline_request(query: str) -> tuple[str, bool, bool] | None:
    """Find the outline number and the requested depth for an explicit section."""
    text = " ".join(query.split()).rstrip(".!?…").rstrip()
    topics = OUTLINE_TOPICS_QUESTION.fullmatch(text)
    if topics:
        return topics[1], True, False
    detail_suffix = OUTLINE_DETAIL.search(text)
    if detail_suffix:
        text = text[:detail_suffix.start()].rstrip(".!?…,:; ")
    detailed = OUTLINE_DETAIL_QUESTION.fullmatch(text)
    if not detailed and text.casefold().endswith(" chi tiết"):
        detailed = OUTLINE_QUESTION.fullmatch(text[:-len(" chi tiết")])
    match = detailed or OUTLINE_QUESTION.fullmatch(text)
    return (match[1], bool(detail_suffix or detailed), bool(detailed)) if match else None


def procedural_search_terms(query: str) -> str:
    """Build a second search from the task words or shared technical terms."""
    match = PROCEDURAL_QUESTION.match(query)
    if not match or re.search(r"`|(?<!\w)--?[a-z]", match[1], re.I):
        return ""
    words = re.findall(r"\w+", match[1].lower())
    if query.lstrip().casefold().startswith(("lệnh nào", "câu lệnh nào")):
        words = [word for word in words if word.isascii() and len(word) > 1]
    terms = [
        word[:-1] if re.fullmatch(r"[a-z]{3,}s", word) and not word.endswith(("ss", "us", "is")) else word
        for word in words if word not in STOP_WORDS
    ]
    return " ".join(terms) if len(terms) >= 2 else ""


def prioritize_topic_passages(
    chunks: list[DocumentChunk], topic: str, needs_example: bool,
) -> tuple[list[DocumentChunk], tuple[DocumentChunk, int, str] | None]:
    """Prefer intact lines on the topic over fragments, and retain a cited example when available."""
    pattern = re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, topic.split())) + r"(?!\w)", re.I)
    complete, fragments = [], []
    example = None
    for chunk in chunks:
        matches = [
            (index, line.strip()) for index, line in enumerate(chunk.text.splitlines(), chunk.start_line)
            if pattern.search(line)
        ]
        if not matches:
            continue
        (complete if any(len(line.split()) >= 4 for _, line in matches) else fragments).append(chunk)
        if needs_example and example is None:
            example = next((
                (chunk, index, line) for index, line in matches
                if line.startswith(("$ ", ">>> ")) and pattern.search(line.split(" #", 1)[0])
                and not has_damaged_text(line)
            ), None)
    ranked = complete + fragments
    if example is not None:
        ranked = [*ranked[:1], example[0], *ranked[1:]]
    return list({chunk.chunk_id: chunk for chunk in ranked}.values()), example


def align_claim_to_chunks(claim: GeneratedClaim, chunks: List[DocumentChunk]) -> GeneratedClaim:
    """
    Step 2.5: Normalizes and aligns citation coordinates.
    If the LLM extracted a quote that exists in a candidate chunk but had a 1-2 line offset,
    this helper snaps the line numbers, doc_id, doc_version, and doc_hash to the exact physical
    coordinates of the chunk.
    If the quote does NOT exist in any chunk (hallucination), it is left untouched so that
    verify_citations() can catch and flag it as UNGROUNDED_QUOTE.
    """
    quote_clean = claim.evidence_quote.strip().lower()
    if not quote_clean:
        return claim

    # Try to find the excerpt in retrieved candidate chunks
    source = claim.cited_doc_id.casefold()
    exact_ids = {chunk.doc_id for chunk in chunks if chunk.doc_id.casefold() == source}
    candidates = exact_ids or {
        chunk.doc_id for chunk in chunks
        if source in {
            chunk.doc_name.casefold(), chunk.doc_id.rsplit(".", 1)[0].casefold(),
            chunk.doc_name.rsplit(".", 1)[0].casefold(),
        }
    }
    if len(candidates) != 1:
        return claim
    doc_id = next(iter(candidates))
    claim = claim.model_copy(update={"cited_doc_id": doc_id})
    source_chunks = [
        chunk for chunk in chunks
        if chunk.doc_id == doc_id
        and (not claim.doc_hash or claim.doc_hash == chunk.doc_hash)
        and (not claim.doc_version or claim.doc_version == chunk.doc_version)
    ]
    # A quote repeated elsewhere must not move an already valid citation.
    if claim.cited_start_line is not None and claim.cited_end_line is not None:
        for chunk in source_chunks:
            if chunk.page_number != claim.cited_page:
                continue
            start = claim.cited_start_line - chunk.start_line
            end = claim.cited_end_line - chunk.start_line
            lines = chunk.text.splitlines()
            if 0 <= start <= end < len(lines) and quote_clean.count("\n") == end - start:
                if quote_clean in "\n".join(lines[start:end + 1]).lower():
                    return claim.model_copy(update={"doc_version": chunk.doc_version, "doc_hash": chunk.doc_hash})
    for chunk in sorted(source_chunks, key=lambda candidate: candidate.page_number != claim.cited_page):
        chunk_text_lower = chunk.text.lower()
        if quote_clean in chunk_text_lower:
            preceding_text = chunk_text_lower.split(quote_clean, 1)[0]
            start_offset = preceding_text.count("\n")
            quote_lines = quote_clean.count("\n")
            if any(has_damaged_text(line) for line in chunk.text.splitlines()[start_offset:start_offset + quote_lines + 1]):
                continue

            base_line = chunk.start_line if chunk.start_line is not None else 1
            actual_start_line = base_line + start_offset
            actual_end_line = actual_start_line + quote_lines

            return GeneratedClaim(
                claim_text=claim.claim_text,
                section=claim.section,
                cited_doc_id=chunk.doc_id,
                cited_page=chunk.page_number,
                cited_start_line=actual_start_line,
                cited_end_line=actual_end_line,
                doc_version=chunk.doc_version,
                doc_hash=chunk.doc_hash,
                evidence_quote=claim.evidence_quote,
                verification_status=claim.verification_status,
                match_score=claim.match_score,
                matched_span=claim.matched_span,
            )

    return claim


def supplied_evidence_lookup(chunks: list[DocumentChunk]) -> dict:
    """Use only actual prompt chunks, with original line numbers and no source aliases."""
    keys = {(chunk.doc_id, chunk.page_number) for chunk in chunks}
    scope = WorkspaceRepository()
    scope.chunks = chunks
    lookup = {key: value for key, value in scope.build_page_lookup().items() if key in keys}
    for entry in lookup.values():
        visible = []
        for start, lines in entry["windows"]:
            for number, line in enumerate(lines, start):
                if has_damaged_text(line):
                    continue
                if not visible or number != visible[-1][0] + len(visible[-1][1]):
                    visible.append((number, []))
                visible[-1][1].append(line)
        entry["windows"] = visible
    return lookup


def resolve_summary_target(
    query: str,
    repository: WorkspaceRepository,
    selected_doc_ids: Optional[List[str]] = None,
    require_explicit: bool = False,
) -> Optional[str]:
    """
    Intelligently identifies which document the user wants to summarize.
    Handles:
    - User types filename with or without extension ('Team_8_Proposal' or 'team_8_proposal.pdf').
    - User types with spaces, hyphens, or underscores ('team 8 proposal' vs 'Team_8_Proposal').
    - User refers to currently selected document ('tóm tắt file này', 'tóm tắt tài liệu đã chọn').
    - Prioritizes selected documents, then most recently uploaded documents.
    """
    q_lower = query.lower().strip()
    q_norm = re.sub(r"[\W_]+", " ", q_lower).strip()

    all_docs = repository.list_documents()
    if not all_docs:
        if repository.chunks:
            seen_ids = set()
            docs_from_chunks = []
            for c in repository.chunks:
                if c.doc_id not in seen_ids:
                    seen_ids.add(c.doc_id)
                    docs_from_chunks.append({"doc_id": c.doc_id, "doc_name": c.doc_name})
            all_docs = docs_from_chunks
        else:
            return None

    if selected_doc_ids is not None:
        all_docs = [d for d in all_docs if d.get("doc_id") in selected_doc_ids or d.get("doc_name") in selected_doc_ids]

    # Resolve an explicit filename before any stem or default selection.
    if DOCUMENT_FILENAME.search(q_lower):
        named = {
            doc["doc_id"] for doc in all_docs
            if any(
                re.search(rf"(?<![\w.-]){re.escape(name.casefold())}(?![\w-]|\.\w)", q_lower)
                for name in (doc.get("doc_name"), doc.get("doc_id")) if name
            )
        }
        return next(iter(named)) if len(named) == 1 else None

    # Step 1: Check for explicit mention of document name or stem in query
    for d in all_docs:
        d_name = d.get("doc_name") or d.get("doc_id") or ""
        d_id = d.get("doc_id") or ""
        d_stem = d_name.rsplit(".", 1)[0].lower() if "." in d_name else d_name.lower()
        d_id_stem = d_id.rsplit(".", 1)[0].lower() if "." in d_id else d_id.lower()
        d_norm = re.sub(r"[\W_]+", " ", d_stem).strip()

        # Check full filename
        if d_name.lower() in q_lower or d_id.lower() in q_lower:
            return d_id or d_name

        # Check stem without extension (e.g. "team_8_proposal" in "tóm tắt file team_8_proposal ấy")
        if len(d_stem) >= 3 and d_stem in q_lower:
            return d_id or d_name
        if len(d_id_stem) >= 3 and d_id_stem in q_lower:
            return d_id or d_name

        # Check normalized form with spaces (e.g. "team 8 proposal" vs "team_8_proposal")
        if len(d_norm) >= 3 and (d_norm in q_norm or d_norm.replace(" ", "") in q_norm.replace(" ", "")):
            return d_id or d_name

    if require_explicit:
        return None
    # Step 2: If query contains generic summary request, prioritize currently selected document in the sidebar
    if selected_doc_ids:
        for sel_id in selected_doc_ids:
            for d in all_docs:
                if d.get("doc_id") == sel_id or d.get("doc_name") == sel_id:
                    return d.get("doc_id") or sel_id
        return selected_doc_ids[0]

    # Step 3: If no specific doc mentioned and nothing selected, pick the most recently uploaded doc (last added)
    if all_docs:
        return all_docs[-1].get("doc_id") or all_docs[-1].get("doc_name")

    return None


def extract_summary_passages(
    chunks: List[DocumentChunk], *, detailed: bool,
    sections: Optional[Dict[tuple[int, int], tuple[str, str]]] = None,
) -> List[GeneratedClaim]:
    """Pick readable verbatim passages across a document when generation is unavailable."""
    passages_by_section = {}
    seen = set()
    chapter_only = bool(sections and len(set(sections.values())) > 24)
    for chunk in sorted(chunks, key=lambda chunk: (chunk.page_number, chunk.start_line or 1)):
        lines = chunk.text.splitlines()
        for index, line in enumerate(lines):
            if has_damaged_text(line):
                continue
            if not line.strip() or (not sections and index and lines[index - 1].strip() and len(line.strip()) < 70):
                continue
            location = chunk.page_number, (chunk.start_line or 1) + index
            section = sections.get(location) if sections else None
            if section and line.strip() == section[1]:
                continue
            excerpt = line.strip()
            end = index
            while len(excerpt) < 180 and end + 1 < len(lines) and lines[end + 1].strip():
                if has_damaged_text(lines[end + 1]):
                    break
                if sections and sections.get((location[0], location[1] + end - index + 1)) != section:
                    break
                end += 1
                excerpt += "\n" + lines[end].strip()
            if len(excerpt) > 500:
                excerpt = excerpt[:500].rsplit(maxsplit=1)[0]
                end = index + excerpt.count("\n")
            if excerpt.casefold() not in seen:
                seen.add(excerpt.casefold())
                group = section or (chunk.page_number,)
                if section and chapter_only:
                    group = (section[0], section[0])
                passages_by_section.setdefault(group, []).append((chunk, index, end, excerpt))

    groups = list(passages_by_section)
    limit = 32 if chapter_only else 24 if sections else 10 if detailed else 7
    if len(groups) > limit:
        groups = [groups[round(i * (len(groups) - 1) / (limit - 1))] for i in range(limit)]
    claims = []
    for group in groups:
        candidates = sorted(passages_by_section[group], key=lambda item: min(len(item[3].split()), 42), reverse=True)
        count = 1 if sections else 2 if detailed or len(groups) == 1 else 1
        for chunk, start, end, excerpt in candidates[:count]:
            line = chunk.start_line or 1
            claims.append(GeneratedClaim(
                claim_text=" ".join(excerpt.split()),
                section=group[0] if len(group) == 2 else f"Trang {chunk.page_number}", evidence_quote=excerpt,
                cited_doc_id=chunk.doc_id, cited_page=chunk.page_number, cited_start_line=line + start, cited_end_line=line + end,
                doc_version=chunk.doc_version, doc_hash=chunk.doc_hash,
            ))
    return claims


def outline_subsection_excerpt(first: DocumentChunk, section: OutlineSection) -> GeneratedClaim | None:
    """Show cited source prose when a generated subsection note cannot be verified."""
    packets = map_packets(section, 1500)
    passages = [
        first.model_copy(update={
            "text": block.text, "page_number": block.page,
            "start_line": block.start_line, "end_line": block.end_line,
        })
        for packet in packets[:1] for block in packet
    ]
    section_lines = {
        (passage.page_number, line): (section.title, section.title)
        for passage in passages for line in range(passage.start_line, passage.end_line + 1)
    }
    excerpts = extract_summary_passages(passages, detailed=False, sections=section_lines)
    if excerpts:
        claim = excerpts[0]
        return claim.model_copy(update={"claim_text": f"Trích đoạn: {claim.claim_text}"})
    if not passages:
        return None
    passage = passages[0]
    heading = passage.text.splitlines()[0]
    return GeneratedClaim(
        claim_text="Phần văn bản đọc được chỉ đủ để xác nhận tiêu đề.",
        cited_doc_id=first.doc_id,
        cited_page=passage.page_number,
        cited_start_line=passage.start_line,
        cited_end_line=passage.start_line,
        evidence_quote=heading,
        doc_version=first.doc_version,
        doc_hash=first.doc_hash,
    )


DOCUMENT_SOURCE = r"(?:file|tệp|tài liệu|báo cáo)"
DOCUMENT_TOPICS = re.compile(
    rf"\b{DOCUMENT_SOURCE}(?:\s+(?:này|trên|đó))?\s+(?:trình bày|gồm|có|đề cập(?: đến)?)\s+"
    r"(?:những\s+|các\s+)?(?:chủ đề|nội dung)(?:\s+chính)?\s+(?:nào|gì)\b", re.I,
)
DOCUMENT_CONTENT_QUESTION = re.compile(
    rf"\b(?:những gì có|có những gì)\s+(?:ở\s+)?(?:trong|trên)\s+{DOCUMENT_SOURCE}\b"
    rf"|\b{DOCUMENT_SOURCE}(?:\s+(?:này|trên|đó))?\s+(?:có|gồm|chứa)\s+những gì\b"
    rf"|\b{DOCUMENT_SOURCE}(?:\s+(?:này|trên|đó))?\s+(?:(?:đang\s+)?nói về (?:gì|chủ đề nào)|trình bày (?:nội dung |chủ đề )?(?:gì|nào))\b"
)
SUMMARY_REQUEST = re.compile(
    r"\b(?:tóm tắt|tóm gọn|tóm lược|tổng hợp|summari[sz]e|summary|overview|review file|tổng quan)\b"
)
SECTION_REQUEST = re.compile(
    r"\b(?:chương|chapter|tiểu mục|mục|section|phần|part|phụ lục|appendix|trang|pages?)\s+(?:\d+\b|[a-z]\b)"
    r"|\b(?:tóm tắt|tóm lược|summari[sz]e)\s+(?:về\s+|the\s+)?"
    r"(?:lệnh|commands?|khái niệm|quy trình|cách|chương|chapter|tiểu mục|section|phần|part|phụ lục|appendix)\b"
)


def asks_for_document_summary(query: str) -> bool:
    """Route document overviews separately from questions about individual sections."""
    text = " ".join(query.lower().split())
    if SECTION_REQUEST.search(text):
        return False
    return bool(
        SUMMARY_REQUEST.search(text)
        or DOCUMENT_TOPICS.search(text)
        or DOCUMENT_CONTENT_QUESTION.search(text)
        or any(phrase in text for phrase in ("chủ đề gì", "đang nói về", "những gì nổi bật trong file"))
        or (
            re.search(r"\b(?:nêu|miêu tả|mô tả|trình bày|describe)\b", text)
            and re.search(r"\b(?:toàn bộ|tất cả|entire|whole)\b", text)
            and re.search(rf"\b(?:{DOCUMENT_SOURCE}|document|report|pdf)\b", text)
        )
    )


NUMBERED_SECTION = re.compile(r"^(\d{1,2})\.(?:(\d{1,2})\.?\s+|\s+)(\S.*)$")
APPENDIX_SECTION = re.compile(r"^(?:Appendix|Phụ lục)\s+[A-Z]\s*[—–:-]\s+\S.+$", re.IGNORECASE)


def summary_sections(chunks: List[DocumentChunk]) -> Dict[tuple[int, int], tuple[str, str]]:
    """Find an ordered, numbered outline and attach its titles to source lines."""
    lines = {}
    for chunk in chunks:
        for line, text in enumerate(chunk.text.splitlines(), chunk.start_line):
            lines[chunk.page_number, line] = text.strip()

    headings = {}
    main = subsection = 0
    title = ""
    for location, text in sorted(lines.items()):
        if main >= 2 and APPENDIX_SECTION.fullmatch(text):
            title = text
            headings[location] = (title, title)
            continue
        match = NUMBERED_SECTION.fullmatch(text)
        if not match or len(match[3].split()) > 14 or match[3].endswith((".", "…")) or " . ." in text:
            continue
        number = int(match[1])
        if match[2] is None and number == main + 1:
            title = text
            main = number
            subsection = 0
            headings[location] = (title, title)
        elif main and number == main and match[2] and int(match[2]) == subsection + 1:
            subsection += 1
            headings[location] = (title, text)
    if main < 2:
        return {}

    result = {}
    section = None
    for location in sorted(lines):
        section = headings.get(location, section)
        if section:
            result[location] = section
    return result


class QAService:
    """Nghiệp vụ Q&A có đối soát trích dẫn (Grounded Q&A with Citation Verification)."""

    def __init__(
        self,
        repository: Optional[WorkspaceRepository] = None,
        provider: Optional[LLMProvider] = None,
        embed_provider: Optional[Any] = None,
        research_index: ResearchIndex | None = None,
    ) -> None:
        self.repository = repository or workspace_repository
        self.provider = provider or llm_provider
        self.embed_provider = embed_provider or embedding_provider
        self.research_index = research_index
        self.summary_cache_dir: Path | None = None
        # Inject embed_fn into repository if available
        embed_fn = self.embed_provider.get_embed_fn()
        if isinstance(self.repository, WorkspaceRepository) and isinstance(self.embed_provider, EmbeddingProvider):
            self.repository.set_embed_fn(
                embed_fn, index_id=self.embed_provider.index_id,
                semantic_weight=0.35 if self.embed_provider.using_hash_fallback else 0.65,
            )
        elif embed_fn is not None:
            self.repository.set_embed_fn(embed_fn)

    def document_topics(self, doc_id: str, match_threshold: float) -> Dict[str, Any]:
        """Read an explicit agenda before attempting a generated whole-document summary."""
        chunks = self.repository.get_document_chunks(doc_id)
        if not chunks:
            return self.summarize_document(doc_id, brief=True)
        rows = indexed_blocks(chunks)
        pages = sorted({page for page, _ in rows})[:6]
        for page in pages:
            lines = [(number, text.strip()) for (p, number), text in sorted(rows.items()) if p == page and text.strip()]
            if not lines or not re.fullmatch(
                r"(?:.+?\s*[:—–-]\s*)?(?:overview|agenda|table of contents|tổng quan|nội dung chính|mục lục)",
                lines[0][1], re.I,
            ):
                continue
            topics = [(number, text) for number, text in lines[1:]
                      if not re.fullmatch(r".+:\s*\d+\s*[-–]\s*\d+|\d+", text)]
            if not 3 <= len(topics) <= 12 or any(has_damaged_text(text) for _, text in topics):
                continue
            first = chunks[0]
            claims = [GeneratedClaim(
                claim_text=text, evidence_quote=text, cited_doc_id=first.doc_id, cited_page=page,
                cited_start_line=number, cited_end_line=number,
                doc_version=first.doc_version, doc_hash=first.doc_hash,
            ) for number, text in topics]
            return self._verify_answer(claims, match_threshold, lookup=supplied_evidence_lookup(chunks))
        return self.summarize_document(doc_id, brief=True)

    def summarize_document(self, doc_id: str, *, detailed: bool = False, brief: bool = False) -> Dict[str, Any]:
        """Summarizes a specific document in the workspace using the active LLM or deterministic engine."""
        chunks = self.repository.get_document_chunks(doc_id)
        if not chunks:
            # If not found by exact id, try matching substring or stem without extension
            clean_id = doc_id.lower().replace(".pdf", "").replace(".txt", "").replace(".csv", "").strip()
            matching = [
                c for c in self.repository.chunks
                if doc_id.lower() in c.doc_id.lower()
                or doc_id.lower() in c.doc_name.lower()
                or clean_id in c.doc_id.lower()
                or clean_id in c.doc_name.lower()
            ]
            chunks = matching if len({chunk.doc_id for chunk in matching}) == 1 else []
            if not chunks:
                return {
                    "route": RouteType.QA_FLOW,
                    "status": "DOCUMENT_NOT_FOUND",
                    "message": f"Không tìm thấy tài liệu `{doc_id}` trong Workspace để tóm tắt.",
                    "summary": "",
                    "grounding_score": 0.0,
                    "validated_claims": [],
                    "hallucination_flags": [],
                }

        doc_name = chunks[0].doc_name
        if settings.llm_provider in {"gemini", "ollama"} and not settings.offline_only:
            total_chars = sum(len(chunk.text) for chunk in chunks)
            if total_chars > LONG_DOCUMENT_CHARS and sum(
                len(line) + 1 for line in indexed_blocks(chunks).values()
            ) > LONG_DOCUMENT_CHARS:
                doc = self.repository.documents.get(chunks[0].doc_id)
                return summarize_long_document(
                    chunks, doc.pdf_headings if doc else [], self.repository.build_page_lookup(),
                    self.provider, self.summary_cache_dir, brief=brief,
                )
            is_gemini = settings.llm_provider == "gemini"
            chunks = sorted(chunks, key=lambda chunk: (chunk.page_number, chunk.start_line))
            sections_by_line = summary_sections(chunks) if detailed else {}
            source_sections = dict.fromkeys(sections_by_line.values())
            chapter_starts = {}
            for location, (chapter, _) in sections_by_line.items():
                chapter_starts.setdefault(chapter, location)
            budget = 120_000 if is_gemini else 20_000 if detailed else 5500
            if total_chars <= budget and (is_gemini or detailed or (len(chunks) <= 10 and total_chars <= 4500)):
                sampled = chunks
            else:
                sample_count = max(6, len(chunks) * budget // total_chars) if is_gemini or detailed else 6
                candidates = []
                continuations = []
                for page, line in chapter_starts.values():
                    chapter_intro = [
                        chunk for chunk in chunks
                        if chunk.page_number == page and chunk.end_line >= line
                    ]
                    candidates.extend(chapter_intro[:1])
                    continuations.extend(chapter_intro[1:2])
                candidates.extend(continuations)
                candidates.extend(
                    chunks[round(i * (len(chunks) - 1) / (sample_count - 1))] for i in range(sample_count)
                )
                sampled, seen, size = [], set(), 0
                for chunk in candidates:
                    if chunk.chunk_id not in seen and size + len(chunk.text) <= budget:
                        sampled.append(chunk)
                        seen.add(chunk.chunk_id)
                        size += len(chunk.text)
                sampled.sort(key=lambda chunk: (chunk.page_number, chunk.start_line))
            scope = "toàn bộ nội dung đã lập chỉ mục" if len(sampled) == len(chunks) else "các đoạn trích đại diện"
            summary_query = f"Tóm tắt {scope} của {doc_name}."
            if brief:
                summary_query += " Chỉ nêu ngắn gọn các chủ đề chính, gộp các ví dụ nhỏ theo chủ đề."
            if detailed:
                summary_query += " Hãy mô tả chi tiết các phần chính. Bao quát các đề mục nguồn theo thứ tự. "
                summary_query += "Giữ nguyên các điều kiện bắt buộc, quan hệ và/hoặc, ngoại lệ và số liệu quan trọng."
            def verify_summary(claims, evidence, *, align=True):
                return verification_result_to_schema(verify_citations(
                    [
                        claim_schema_to_algorithm(align_claim_to_chunks(claim, evidence) if align else claim)
                        for claim in claims if not has_damaged_text(claim.evidence_quote)
                    ],
                    supplied_evidence_lookup(evidence), theta_match=settings.theta_match,
                ))

            def find_missing_sections(claims):
                covered = {
                    sections_by_line.get((claim.cited_page, claim.cited_start_line)) for claim in claims
                }
                covered_main = {location[0] for location in covered if location}
                return [
                    (main, section) for main, section in source_sections
                    if (main != section and (main, section) not in covered)
                    or (main == section and main not in covered_main)
                ]

            started = monotonic()
            extracted = False
            try:
                raw = self.provider.generate_grounded_qa(summary_query, sampled, document_summary=True)
            except GeminiUnavailableError:
                sampled = chunks
                raw = extract_summary_passages(sampled, detailed=detailed, sections=sections_by_line)
                extracted = True
            if not is_gemini and not raw:
                sampled = chunks
                raw = extract_summary_passages(sampled, detailed=detailed, sections=sections_by_line)
                extracted = True
            verification = verify_summary(raw, sampled, align=not extracted)
            if not extracted:
                review_verification(self.provider, verification)
            claims = verification.validated_claims
            sections = {claim.section for claim in claims if claim.section}
            missing_sections = set(find_missing_sections(claims))
            pages = {chunk.page_number for chunk in sampled}
            cited_pages = {claim.cited_page for claim in claims}
            ordered_pages = sorted(pages)
            midpoint = len(ordered_pages) // 2
            covers_both_halves = bool(cited_pages.intersection(ordered_pages[:midpoint])) and bool(
                cited_pages.intersection(ordered_pages[midpoint:])
            )
            # Leave time for a supplement inside the chat client's response window.
            needs_page_supplement = is_gemini and len(pages) >= 8 and (
                len(claims) < 8 or len(sections) < 4 or not covers_both_halves
            )
            if not extracted and monotonic() - started < (100 if is_gemini else 115) and (
                missing_sections or needs_page_supplement
            ):
                if missing_sections:
                    remaining = [
                        chunk for chunk in chunks
                        if any(
                            sections_by_line.get((chunk.page_number, line)) in missing_sections
                            for line in range(chunk.start_line, chunk.end_line + 1)
                        )
                    ]
                    if sum(len(chunk.text) for chunk in remaining) > budget:
                        sampled_ids = {chunk.chunk_id for chunk in sampled}
                        remaining = [chunk for chunk in remaining if chunk.chunk_id in sampled_ids]
                else:
                    remaining = [chunk for chunk in sampled if chunk.page_number not in cited_pages] or sampled
                covered = "\n".join(f"- {claim.section or ''} | {claim.claim_text[:280]}" for claim in claims[:16])
                supplement_query = (
                    "Bổ sung tối đa 6 ý quan trọng còn thiếu cho bản tóm tắt. Ưu tiên mục, tính năng, kết quả "
                    "hoặc rủi ro chưa được nêu. Chỉ thêm nội dung mới có thể trích dẫn từ các đoạn cung cấp. "
                    "Nếu bổ sung vào một mục đã có, dùng nguyên tên mục. Các ý dưới đây chỉ để tránh lặp, "
                    f"không dùng làm bằng chứng:\n{covered or '(chưa có ý nào được kiểm chứng)'}"
                )
                if missing_sections:
                    supplement_query += "\nBổ sung ít nhất một ý có trích dẫn cho mỗi đề mục còn thiếu trong nguồn cung cấp."
                try:
                    extra = self.provider.generate_grounded_qa(
                        supplement_query, remaining, document_summary=True, supplemental_summary=True,
                    ) if remaining else []
                except GeminiRequestError:
                    extra = []
                added = verify_summary(extra, remaining)
                review_verification(self.provider, added)
                seen = {" ".join(claim.claim_text.casefold().split()) for claim in claims}
                for claim in added.validated_claims:
                    key = " ".join(claim.claim_text.casefold().split())
                    if key not in seen:
                        claims.append(claim)
                        seen.add(key)
                verification.hallucination_flags.extend(added.hallucination_flags)
                total = len(claims) + len(verification.hallucination_flags)
                verification.grounding_score = round(len(claims) / max(1, total), 4)

            if sections_by_line:
                claims.sort(key=lambda claim: (claim.cited_page, claim.cited_start_line or 1))
                for claim in claims:
                    location = sections_by_line.get((claim.cited_page, claim.cited_start_line))
                    if location:
                        section, subsection = location
                        claim.section = section
                        claim.subsection = subsection if subsection != section else None
            grouped = {}
            for index, claim in enumerate(claims):
                grouped.setdefault(claim.section or index, []).append(claim)
            claims = [claim for group in grouped.values() for claim in group]
            message = f"Tóm tắt dựa trên {scope}." if claims else "Model chưa cung cấp đủ trích dẫn hợp lệ để tóm tắt tài liệu này."
            if claims and not extracted:
                missing = find_missing_sections(claims)
                missing_main = {main for main, section in missing if main == section}
                missing_titles = [section for main, section in missing if main == section or main not in missing_main]
                if missing_titles:
                    message += " Chưa có ý kèm trích dẫn cho các mục: " + ", ".join(missing_titles) + "."
            if extracted:
                reason = "Gemini đang gián đoạn (503)." if is_gemini else "Ollama chưa trả về bản tóm tắt có trích dẫn."
                message = reason + (" Dưới đây là các đoạn nguyên văn đã kiểm tra trích dẫn."
                                    if claims else " Chưa tìm thấy đoạn trích phù hợp để hiển thị.")
            return {
                "route": RouteType.QA_FLOW,
                "status": "SUMMARY_GENERATED" if verification.validated_claims else "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "doc_name": doc_name,
                "summary": "\n\n".join(c.claim_text for c in claims),
                "message": message,
                "summary_scope": "representative_excerpts" if extracted or len(sampled) != len(chunks) else "all_indexed_passages",
                "grounding_score": verification.grounding_score,
                "validated_claims": claims,
                "hallucination_flags": verification.hallucination_flags,
            }
        summary_text = self.provider.generate_summary(doc_name, chunks)

        # Collect top representative chunk from each unique page for multi-page evidence inspection
        seen_pages = set()
        multi_claims: List[GeneratedClaim] = []
        for c in chunks:
            if c.page_number not in seen_pages:
                seen_pages.add(c.page_number)
                multi_claims.append(
                    GeneratedClaim(
                        claim_text=summary_text,
                        cited_doc_id=c.doc_id,
                        cited_page=c.page_number,
                        cited_start_line=c.start_line,
                        cited_end_line=c.end_line,
                        doc_version=c.doc_version,
                        doc_hash=c.doc_hash,
                        evidence_quote=c.text[:120],
                        verification_status="VERIFIED_EXACT",
                    )
                )

        if not multi_claims and chunks:
            top = chunks[0]
            multi_claims = [
                GeneratedClaim(
                    claim_text=summary_text,
                    cited_doc_id=top.doc_id,
                    cited_page=top.page_number,
                    cited_start_line=top.start_line,
                    cited_end_line=top.end_line,
                    doc_version=top.doc_version,
                    doc_hash=top.doc_hash,
                    evidence_quote=top.text[:120],
                    verification_status="VERIFIED_EXACT",
                )
            ]

        return {
            "route": RouteType.QA_FLOW,
            "status": "SUMMARY_GENERATED",
            "doc_name": doc_name,
            "summary": summary_text,
            "grounding_score": 1.0,
            "validated_claims": multi_claims,
            "hallucination_flags": [],
        }

    def _answer_outline_section(
        self, number: str, selected_doc_ids: Optional[List[str]], match_threshold: float,
        *, by_subsection: bool = False, detailed: bool = False,
    ) -> Dict[str, Any]:
        """Resolve an exact outline number inside the selected sources."""
        doc_ids = selected_doc_ids
        if doc_ids is None:
            doc_ids = self.repository.get_selected_doc_ids() or [
                doc["doc_id"] for doc in self.repository.list_documents()
            ]
        candidates = {}
        for doc_id in doc_ids:
            chunks = self.repository.get_document_chunks(doc_id)
            if not chunks or chunks[0].doc_id in candidates:
                continue
            first = chunks[0]
            doc = self.repository.documents.get(first.doc_id)
            outline = build_outline(chunks, doc.pdf_headings if doc else ())
            for section in outline:
                label = NUMBERED.fullmatch(section.title.strip())
                if not label or label[1] != number or section.level != number.count(".") + 1:
                    continue
                candidates[first.doc_id] = (first, outline, section, tuple(doc.pdf_headings) if doc else ())
                break
        if len(candidates) != 1:
            answer = self._verify_answer([], match_threshold, lookup={})
            answer["message"] = (
                f"Có nhiều tài liệu được chọn có mục {number}. Hãy chọn tài liệu bạn muốn hỏi."
                if candidates else f"Không tìm thấy mục {number} trong dàn ý của tài liệu được chọn."
            )
            return answer

        first, outline, section, headings = next(iter(candidates.values()))
        lookup = self.repository.build_page_lookup()
        children = [item for item in outline if item.parent_id == section.id]
        damaged_section = any(has_damaged_text(block.text) for block in section.blocks)
        if by_subsection and (children or detailed):
            generated = summarize_outline_section(
                first, outline, section, lookup, self.provider, self.summary_cache_dir,
                by_subsection=True, detailed=detailed,
            )
            claims = []
            for child in children or [section]:
                for part in outline_detail_parts(child) if detailed else [child]:
                    notes = [
                        claim for claim in generated
                        if claim.subsection == child.title and any(
                            claim.cited_page == block.page and claim.cited_start_line is not None
                            and claim.cited_end_line is not None
                            and block.start_line <= claim.cited_start_line <= claim.cited_end_line <= block.end_line
                            for block in part.blocks
                        )
                    ]
                    if not notes:
                        fallback = outline_subsection_excerpt(first, part)
                        notes = [fallback] if fallback else []
                    claims.extend(
                        claim.model_copy(update={
                            "section": section.title, "subsection": child.title if children else None,
                        })
                        for claim in notes
                    )
        elif damaged_section:
            claims = []
            for child in children:
                anchor = child.blocks[0]
                heading = anchor.text.splitlines()[0].strip()
                if not heading or has_damaged_text(heading):
                    continue
                label = NUMBERED.fullmatch(heading)
                title = label[2] if label else heading
                claims.append(GeneratedClaim(
                    claim_text=title,
                    section=section.title,
                    cited_doc_id=first.doc_id,
                    cited_page=anchor.page,
                    cited_start_line=anchor.start_line,
                    cited_end_line=anchor.start_line,
                    evidence_quote=heading,
                    doc_version=first.doc_version,
                    doc_hash=first.doc_hash,
                ))
        else:
            claims = summarize_outline_section(
                first, outline, section, lookup, self.provider, self.summary_cache_dir, headings=headings,
            )
        if not claims:
            block = section.blocks[0]
            lines = block.text.splitlines()[:8]
            end = next((index for index, line in enumerate(lines) if has_damaged_text(line)), len(lines))
            excerpt = "\n".join(lines[:end]).strip()
            claims = [GeneratedClaim(
                claim_text=excerpt,
                section=section.title,
                cited_doc_id=first.doc_id,
                cited_page=block.page,
                cited_start_line=block.start_line,
                cited_end_line=block.start_line + excerpt.count("\n"),
                evidence_quote=excerpt,
                doc_version=first.doc_version,
                doc_hash=first.doc_hash,
            )]
        return self._verify_answer(claims, match_threshold, lookup=lookup)

    def answer_question(
        self,
        query: str,
        top_k: int = 3,
        selected_doc_ids: Optional[List[str]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        tau_rel: Optional[float] = None,
        theta_match: Optional[float] = None,
        quiz_explanation: bool = False,
    ) -> Dict[str, Any]:
        if is_greeting(query):
            return {
                "route": RouteType.QA_FLOW, "status": "CONVERSATION",
                "message": "Chào bạn! Mình sẵn sàng hỗ trợ. Bạn có thể chọn tài liệu rồi hỏi về nội dung, yêu cầu tóm tắt hoặc giải thích một phần cụ thể.",
                "validated_claims": [], "hallucination_flags": [], "citations": [],
            }
        # 1. Rule: Explicit empty document selection must abstain immediately
        if selected_doc_ids is not None and len(selected_doc_ids) == 0:
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_NO_SOURCE_SELECTED",
                "message": "Chưa chọn tài liệu nguồn nào. Vui lòng chọn ít nhất một tài liệu trong Document Library để tra cứu.",
                "citations": [],
                "dense_available": getattr(self.repository, "dense_available", False),
                "validated_claims": [],
                "hallucination_flags": [],
                "grounding_score": 0.0,
            }

        q_lower = query.lower()
        match_threshold = theta_match if theta_match is not None else settings.theta_match
        detailed = not quiz_explanation and is_detail_followup(query)
        outline_question = None if quiz_explanation else outline_request(query)
        reference = None if quiz_explanation else SECTION_FOLLOWUP.fullmatch(" ".join(query.split()).rstrip(".!?…"))
        if reference or detailed:
            previous = previous_question(query, conversation_history)
            previous_outline = outline_request(previous)
            if previous_outline:
                explain = detailed or bool(reference["detail"]) or not reference["action"].casefold().startswith("tóm")
                outline_question = (previous_outline[0], explain, explain)
            elif reference or not previous:
                return {
                    "route": RouteType.CLARIFICATION_FLOW, "status": "AWAITING_CLARIFICATION",
                    "message": "Bạn muốn hỏi về chương, mục hoặc nội dung nào trong tài liệu đã chọn?",
                    "missing_slots": ["topic_or_section"], "validated_claims": [],
                }
        if outline_question:
            number, by_subsection, outline_detailed = outline_question
            return self._answer_outline_section(
                number, selected_doc_ids, match_threshold, by_subsection=by_subsection, detailed=outline_detailed,
            )
        retrieval_query = query if quiz_explanation else expand_contextual_query(query, conversation_history)
        summary_query = retrieval_query if detailed else query
        feature_refs = set() if quiz_explanation else set(FEATURE_REFERENCE.findall(retrieval_query))

        if not quiz_explanation and not feature_refs and asks_for_document_summary(summary_query):
            summary_ids = selected_doc_ids if selected_doc_ids is not None else self.repository.get_selected_doc_ids()
            if not summary_ids and selected_doc_ids is None:
                summary_ids = [doc["doc_id"] for doc in self.repository.list_documents()]
            canonical_ids = list(dict.fromkeys(
                chunk.doc_id for doc_id in summary_ids for chunk in self.repository.get_document_chunks(doc_id)
            ))
            target_doc = resolve_summary_target(summary_query, self.repository, canonical_ids, len(canonical_ids) > 1)
            if target_doc:
                if DOCUMENT_TOPICS.search(summary_query):
                    return self.document_topics(target_doc, match_threshold)
                brief = bool(BRIEF_DOCUMENT.search(summary_query))
                if brief:
                    return self.summarize_document(target_doc, brief=True)
                return self.summarize_document(
                    target_doc, detailed=detailed or requests_detailed_answer(summary_query),
                )
            if DOCUMENT_FILENAME.search(summary_query):
                answer = self._verify_answer([], match_threshold, lookup={})
                answer["message"] = "Không xác định được tài liệu được nêu tên trong các nguồn đã chọn."
                return answer
            if len(canonical_ids) > 1:
                answer = self._verify_answer([], match_threshold, lookup={})
                answer["message"] = "Có nhiều tài liệu được chọn. Hãy nêu tên tài liệu cần tóm tắt hoặc chỉ chọn một nguồn."
                return answer

        dense_active = getattr(self.repository, "dense_available", False)
        default_min_score = settings.dense_tau_rel if dense_active else settings.bm25_tau_rel
        min_score = tau_rel if tau_rel is not None else default_min_score
        if not quiz_explanation and GIT_COMMAND_LIST.fullmatch(query.strip().rstrip(".!?").strip()):
            doc_ids = selected_doc_ids
            if doc_ids is None:
                doc_ids = self.repository.get_selected_doc_ids() or [
                    doc["doc_id"] for doc in self.repository.list_documents()
                ]
            scoped_doc_ids = {
                chunk.doc_id for doc_id in doc_ids
                for chunk in self.repository.get_document_chunks(doc_id)
            }
            page_lookup = self.repository.build_page_lookup()
            table_claims = git_command_reference_claims(page_lookup, scoped_doc_ids)
            if table_claims:
                verified = self._verify_answer(table_claims, match_threshold, lookup=page_lookup)
                if verified["validated_claims"]:
                    return verified

        # 2. Deterministic Contextual Query Expansion
        weighted_query = FEATURE_REFERENCE.sub(lambda match: f"Feature {match[1]} tính năng {match[1]}", retrieval_query)

        # 3. Adaptive Top-K & Page Diversity based on query breadth
        is_broad_query = any(
            w in q_lower for w in ["tất cả", "toàn bộ", "danh sách", "gồm những gì", "các yêu cầu", "các tiêu chuẩn", "tổng hợp", "chi tiết"]
        ) or bool(re.search(r"\b(?:overview|all|list)\b", q_lower))
        effective_top_k = max(top_k, 5) if is_broad_query else top_k

        # 4. Hybrid retrieval
        scoped_ids = selected_doc_ids if selected_doc_ids is not None else self.repository.get_selected_doc_ids()
        exercise = EXERCISE_REFERENCE.search(query) if not quiz_explanation else None
        if exercise:
            label = re.compile(rf"^\s*(?:(?:bài(?: tập)?|exercise|problem)\s+)?{exercise[1]}[.)](?:\s|[^\d])", re.I)
            exercise_docs = scoped_ids or [doc["doc_id"] for doc in self.repository.list_documents()]
            damaged = []
            next_exercise = re.compile(r"^\s*\d{1,4}[.)](?:\s|[^\d])")
            for doc_id in exercise_docs:
                source = self.repository.get_document_chunks(doc_id)
                lines = indexed_blocks(source)
                for (page, number), line in lines.items():
                    if not label.match(line):
                        continue
                    continuation = [line]
                    for offset in range(1, 8):
                        following = lines.get((page, number + offset), "")
                        if not following.strip() or next_exercise.match(following):
                            break
                        continuation.append(following)
                    if has_damaged_text("\n".join(continuation)):
                        damaged.append(f"{source[0].doc_name} (trang PDF {page})")
            if damaged:
                answer = self._verify_answer([], match_threshold, lookup={})
                sources = ", ".join(dict.fromkeys(damaged))
                answer["message"] = f"Ký hiệu trong bài {exercise[1]} chưa đọc được rõ ở {sources}. Cần xem trang gốc để xác nhận đầy đủ đề bài."
                return answer
        section = []
        if len(feature_refs) == 1 and hasattr(self.repository, "chunks"):
            source_chunks = self.repository.chunks if not scoped_ids and selected_doc_ids is None else [
                chunk for doc_id in scoped_ids for chunk in self.repository.get_document_chunks(doc_id)
            ]
            section = find_feature_section(source_chunks, next(iter(feature_refs)))
        retrieved = section or self.repository.search(weighted_query, top_k=effective_top_k, selected_doc_ids=selected_doc_ids)
        topic_example = None
        if not section and not quiz_explanation and not feature_refs:
            topic_question = previous_question(query, conversation_history) if NAMED_FOLLOWUP.search(query) else ""
            focused_query = procedural_search_terms(topic_question or query) or topic_question
            topic_match = None if focused_query else TOPIC_EXPLANATION.fullmatch(query.strip().rstrip(".!?"))
            if topic_match:
                focused_query = topic_match["topic"].strip(" `\"'")
            if focused_query:
                focus_size = min(2, effective_top_k)
                focused = self.repository.search(
                    focused_query, top_k=max(12, focus_size) if topic_match else focus_size,
                    selected_doc_ids=selected_doc_ids,
                )
                if topic_match:
                    focused, topic_example = prioritize_topic_passages(focused, focused_query, bool(topic_match["example"]))
                relevant = {chunk.chunk_id: chunk for chunk in focused[:focus_size] if chunk.score >= min_score}
                if relevant:
                    retrieved = [*relevant.values(), *(chunk for chunk in retrieved if chunk.chunk_id not in relevant)][:effective_top_k]
        if not section and scoped_ids and 1 < len(scoped_ids) <= effective_top_k:
            represented = {chunk.doc_id for chunk in retrieved}
            for doc_id in scoped_ids:
                if doc_id in represented:
                    continue
                alternative = self.repository.search(weighted_query, top_k=1, selected_doc_ids=[doc_id])
                if alternative and alternative[0].score >= min_score and alternative[0].doc_id not in represented:
                    retrieved.append(alternative[0])
                    represented.add(alternative[0].doc_id)
        if self.research_index is not None and not section and not quiz_explanation and not feature_refs:
            if not retrieved or max(chunk.score for chunk in retrieved) < min_score:
                additional = self.research_index.search(weighted_query, effective_top_k, selected_doc_ids)
                if any(chunk.score >= min_score for chunk in additional):
                    retrieved = [chunk for chunk in additional if chunk.score >= min_score]
        if not retrieved or (not section and max(chunk.score for chunk in retrieved) < min_score):
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "message": "Không tìm thấy đủ bằng chứng trong các tài liệu hiện có của Workspace để trả lời câu hỏi này.",
                "citations": [],
                "dense_available": dense_active,
                "validated_claims": [],
                "hallucination_flags": [],
                "grounding_score": 0.0,
            }

        # A short document can be read in full for elaboration instead of returning
        # the same top snippets. Keep strict scope and a bounded character budget.
        if (detailed or is_broad_query) and not feature_refs and not quiz_explanation:
            doc_ids = {chunk.doc_id for chunk in retrieved if chunk.score >= min_score}
            expanded = sorted(
                [chunk for doc_id in doc_ids for chunk in self.repository.get_document_chunks(doc_id)],
                key=lambda chunk: (chunk.doc_id, chunk.page_number, chunk.start_line),
            ) if hasattr(self.repository, "get_document_chunks") else []
            if expanded and len(expanded) <= 10 and sum(len(chunk.text) for chunk in expanded) <= 4500:
                retrieved = expanded

        # 4. Grounded Reasoning with Conversation History & Structured Qwen Prompting
        if feature_refs:
            retrieval_query += "\nChỉ trả lời về tính năng được hỏi. Nêu cơ chế và chi tiết có trong nguồn; bỏ qua tổng quan dự án và các tính năng khác, trừ các liên kết cần để giải thích."
        source_names = {chunk.doc_id: chunk.doc_name for chunk in retrieved}
        answer_query = query if not quiz_explanation and NAMED_FOLLOWUP.search(query) else retrieval_query
        answer_passages = retrieved
        if topic_example and not any(chunk.chunk_id == topic_example[0].chunk_id for chunk in retrieved):
            topic_example = None
        if topic_example:
            answer_query = f"Giải thích {focused_query} là gì và dùng để làm gì theo tài liệu."
            example_id = topic_example[0].chunk_id
            if retrieved[0].chunk_id != example_id:
                answer_passages = [chunk for chunk in retrieved if chunk.chunk_id != example_id]
        if not quiz_explanation and COMMAND_COMPARISON.fullmatch(query):
            answer_query = (
                "Hãy mô tả kết quả của từng lệnh được chạy trong ví dụ liên quan của tài liệu. "
                "Chỉ nêu những gì xuất hiện trong ví dụ. So sánh nếu có bằng chứng cho cả hai lệnh. "
                f"Câu hỏi gốc: {query}"
            )
        raw_claims = self.provider.generate_grounded_qa(
            answer_query,
            answer_passages,
            conversation_history=conversation_history if retrieval_query != query and not feature_refs else None,
            **({"thinking": True} if settings.feature1_selective_thinking
               and settings.llm_provider == "ollama" and REASONING_REQUEST.search(query) else {}),
        )

        # 5. Snap claims to exact chunk coordinates (Step 2.5) while preserving hallucination detection
        aligned_claims = [align_claim_to_chunks(c, answer_passages) for c in raw_claims]
        verbatim = None
        if topic_example:
            source, line_number, excerpt = topic_example
            verbatim = GeneratedClaim(
                claim_text=f"Ví dụ trong tài liệu:\n\n```\n{excerpt}\n```",
                cited_doc_id=source.doc_id, cited_page=source.page_number,
                cited_start_line=line_number, cited_end_line=line_number,
                evidence_quote=excerpt, doc_version=source.doc_version, doc_hash=source.doc_hash,
            )
        # Verify against the retrieved passages, preserving citations' absolute lines.
        lookup = supplied_evidence_lookup(retrieved)
        result = self._verify_answer(aligned_claims, match_threshold, lookup=lookup, semantic=True, verbatim=verbatim)
        if len(source_names) > 1:
            result["validated_claims"].sort(key=lambda claim: claim.cited_doc_id)
            for claim in result["validated_claims"]:
                claim.section = source_names.get(claim.cited_doc_id, claim.cited_doc_id)
        return result

    def _verify_answer(
        self,
        claims: list[GeneratedClaim],
        match_threshold: float,
        *,
        lookup: Optional[dict] = None,
        semantic: bool = False,
        verbatim: GeneratedClaim | None = None,
    ) -> Dict[str, Any]:
        """Verify source spans and format the existing grounded Q&A response."""
        safe_claims = [claim for claim in claims if not has_damaged_text(claim.evidence_quote)]
        damaged = [
            claim.model_copy(update={"verification_status": "UNGROUNDED_QUOTE"})
            for claim in claims if has_damaged_text(claim.evidence_quote)
        ]
        evidence = lookup if lookup is not None else self.repository.build_page_lookup()
        algo_verification = verify_citations(
            [claim_schema_to_algorithm(c) for c in safe_claims],
            evidence,
            theta_match=match_threshold,
        )
        verification = verification_result_to_schema(algo_verification)
        if damaged:
            verification.hallucination_flags.extend(damaged)
            verification.grounding_score = round(len(verification.validated_claims) / len(claims), 4)
        if semantic:
            review_verification(self.provider, verification)
        if verbatim:
            # Extracted examples contain the exact source line and add no model inference.
            copied = verification_result_to_schema(verify_citations([claim_schema_to_algorithm(verbatim)], evidence, 1.0))
            verification.validated_claims.extend(c for c in copied.validated_claims if c.verification_status == "VERIFIED_EXACT")
            verification.hallucination_flags.extend(copied.hallucination_flags)
            total = len(verification.validated_claims) + len(verification.hallucination_flags)
            verification.grounding_score = round(len(verification.validated_claims) / total, 4) if total else 0.0
        dense_active = getattr(self.repository, "dense_available", False)

        # 7. Rule: If every claim fails citation verification -> Abstain
        if not verification.validated_claims:
            message = "Không tìm thấy đủ bằng chứng đã được kiểm chứng trích lục trong các tài liệu để trả lời câu hỏi này."
            if any(claim.semantic_status for claim in verification.hallucination_flags):
                message = "Chưa xác nhận được kết luận từ các đoạn trích tìm thấy."
            if any(claim.semantic_status == "UNAVAILABLE" for claim in verification.hallucination_flags):
                message = "Bước kiểm tra kết luận theo nguồn chưa hoàn tất. Bạn có thể thử lại."
            return {
                "route": RouteType.QA_FLOW,
                "status": "ABSTAINED_INSUFFICIENT_EVIDENCE",
                "message": message,
                "citations": [],
                "dense_available": dense_active,
                "validated_claims": [],
                "hallucination_flags": verification.hallucination_flags,
                "grounding_score": 0.0,
            }

        citations = []
        for c in verification.validated_claims:
            line_str = f", Dòng {c.cited_start_line}-{c.cited_end_line}" if c.cited_start_line and c.cited_end_line else ""
            citations.append(f"{c.cited_doc_id} (Trang {c.cited_page}{line_str})")

        return {
            "route": RouteType.QA_FLOW,
            "status": "ANSWER_VERIFIED",
            "grounding_score": verification.grounding_score,
            "dense_available": dense_active,
            "citations": citations,
            "validated_claims": verification.validated_claims,
            "hallucination_flags": verification.hallucination_flags,
        }


# Singleton instance
qa_service = QAService()


def handle_qa_request(query: str, top_k: int = 3) -> Dict[str, Any]:
    return qa_service.answer_question(query, top_k=top_k)
