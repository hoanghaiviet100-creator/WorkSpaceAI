"""
backend/providers/prompts.py
System Prompts and Templates for WorkspaceAI (Track C - CSC10014).

Decouples all prompt engineering from LLM Provider execution logic.
Ensures strict grounding, explicit line numbering, zero hallucinations,
and structured JSON outputs for Ollama qwen2.5:7b and Gemini.
"""
from typing import List, Optional
from backend.core.guardrails import wrap_untrusted_chunk
from backend.core.schemas import DocumentChunk


QWEN_SYSTEM_PROMPT = """Bạn là Trợ lý Học thuật Chuyên sâu WorkspaceAI (Đồ án CSC10014).
Nhiệm vụ của bạn là trả lời câu hỏi của người dùng một cách CHÍNH XÁC, CHI TIẾT, ĐẦY ĐỦ dựa DUY NHẤT vào các đoạn tài liệu được cung cấp.

CÁC NGUYÊN TẮC BẮT BUỘC (KHÔNG ĐƯỢC VI PHẠM):
1. CĂN CỨ 100%: Tuyệt đối không suy diễn, không tự bịa đặt thông tin nằm ngoài các đoạn tài liệu dưới đây. Nếu tài liệu không đủ dữ liệu để trả lời câu hỏi, hãy ghi rõ là tài liệu không đề cập.
2. ĐÁNH DẤU TRÍCH DẪN: Cuối mỗi câu hoặc ý trả lời trong trường "answer", hãy ghi rõ nhãn nguồn dạng: [Tên tài liệu, Trang X, Dòng Y-Z].
3. TRÍCH NGUYÊN VĂN (EXCERPT): Trường "excerpt" trong mảng "citations" PHẢI LÀ TRÍCH ĐOẠN NGUYÊN VĂN 100% từng câu chữ từ tài liệu gốc, không sửa đổi hay tóm tắt, để hệ thống đối soát tự động kiểm tra.
4. TỌA ĐỘ DÒNG VÀ TRANG: Lấy chính xác số trang (page) và số dòng (line_start, line_end) từ các nhãn [Dòng K] được gắn sẵn trong từng đoạn tài liệu.
5. ĐỊNH DẠNG ĐẦU RA: Bạn BẮT BUỘC phải trả về DUY NHẤT một đối tượng JSON hợp lệ (không kèm lời dẫn) theo cấu trúc:
{
  "answer": "Câu trả lời chi tiết bằng tiếng Việt, giải thích đầy đủ các ý hỏi, cuối mỗi ý có gắn nhãn [Tên tài liệu, Trang X, Dòng Y-Z]...",
  "citations": [
    {
      "doc_id": "Project_Brief.pdf",
      "page": 6,
      "line_start": 1,
      "line_end": 2,
      "excerpt": "Trích nguyên văn 100% câu chữ từ tài liệu gốc làm bằng chứng..."
    }
  ]
}
"""


def format_chunk_for_llm(chunk: DocumentChunk) -> str:
    """
    Formats a single document chunk with explicit page, boundary, and line labels.
    Example:
    === TÀI LIỆU: Project_Brief.pdf | TÊN: Project_Brief.pdf | TRANG: 6 | DÒNG: 1-2 ===
    [Dòng 1] Submission Package: 01 Engineering Report (12-18 pages recommended)...
    [Dòng 2] Late submissions without prior approval will be subject to deduction.
    """
    lines = chunk.text.splitlines()
    start_l = chunk.start_line if chunk.start_line is not None else 1
    labeled_lines = []
    for idx, line in enumerate(lines):
        line_num = start_l + idx
        labeled_lines.append(f"[Dòng {line_num}] {line}")
    body = "\n".join(labeled_lines)

    header = f"=== TÀI LIỆU: {chunk.doc_id} | TÊN: {chunk.doc_name} | TRANG: {chunk.page_number} | DÒNG: {chunk.start_line}-{chunk.end_line} ==="
    return f"{header}\n{body}"


def build_qa_prompt(
    query: str,
    chunks: List[DocumentChunk],
    conversation_history: Optional[List[dict]] = None,
) -> str:
    """Builds the comprehensive, guardrailed prompt for grounded Q&A."""
    chunks_context = "\n\n".join(format_chunk_for_llm(c) for c in chunks)
    wrapped_context = f"<untrusted_document_data>\n{chunks_context}\n</untrusted_document_data>"

    history_block = ""
    if conversation_history:
        recent_turns = conversation_history[-4:]
        formatted_turns = [
            f"{'Người dùng' if t.get('role') == 'user' else 'Trợ lý'}: {t.get('content', '')}"
            for t in recent_turns if t.get("content")
        ]
        if formatted_turns:
            history_block = "Lịch sử hội thoại trước đó:\n" + "\n".join(formatted_turns) + "\n\n"

    prompt = (
        f"{QWEN_SYSTEM_PROMPT}\n\n"
        f"--- TÀI LIỆU CUNG CẤP ---\n{wrapped_context}\n\n"
        f"{history_block}"
        f"Câu hỏi của người dùng: {query}\n\n"
        f"Hãy trả về JSON theo đúng định dạng được yêu cầu:"
    )
    return prompt


def build_summary_prompt(doc_name: str, chunks: List[DocumentChunk]) -> str:
    """Builds structured executive summary prompt."""
    combined_text = "\n\n".join(
        f"[Trang {c.page_number}, Dòng {c.start_line}-{c.end_line}]:\n{c.text}"
        for c in chunks
    )
    prompt = (
        f"Bạn là chuyên gia phân tích tài liệu học thuật WorkspaceAI.\n"
        f"Dưới đây là toàn bộ nội dung trích xuất từ tài liệu '{doc_name}'.\n"
        f"Hãy tạo bản tóm tắt tài liệu súc tích, chuyên nghiệp bằng tiếng Việt theo định dạng Markdown:\n\n"
        f"### 📄 Tóm tắt Tài liệu: {doc_name}\n"
        f"#### 1. 🎯 Mục tiêu & Tổng quan\n"
        f"(Mô tả tóm tắt mục tiêu chính của tài liệu)\n\n"
        f"#### 2. 📌 Các Yêu cầu & Nội dung Cốt lõi\n"
        f"(Danh sách các yêu cầu kỹ thuật, mốc công việc chính)\n\n"
        f"#### 3. ⏱️ Mốc Thời hạn & Quy định Nộp bài\n"
        f"(Các thông tin về deadline, thành phần hồ sơ nếu có)\n\n"
        f"#### 4. 💡 Lưu ý Quan trọng cho Nhóm Thực hiện\n"
        f"(Lời khuyên hoặc lưu ý quan trọng trích từ tài liệu)\n\n"
        f"Nội dung tài liệu:\n"
        f"<untrusted_document_data>\n{combined_text}\n</untrusted_document_data>"
    )
    return prompt


def build_email_prompt(
    query: str,
    chunks: List[DocumentChunk],
    recipient_email: Optional[str] = None,
) -> str:
    """Builds email drafting prompt."""
    context_str = "\n".join(f"- [{c.doc_name} p.{c.page_number}]: {c.text}" for c in chunks)
    prompt = (
        "Bạn là trợ lý ảo hỗ trợ soạn thảo email học thuật cho đồ án môn học CSC10014 (WorkspaceAI).\n"
        f"Yêu cầu của người dùng: \"{query}\"\n"
        f"Người nhận dự kiến: {recipient_email or 'Giảng viên'}\n"
        f"Dữ liệu liên quan từ workspace:\n{context_str}\n\n"
        "Hãy tạo 1 Tiêu đề (Subject) và Nội dung email (Body) bằng tiếng Việt thật trang trọng, lịch sự và rõ ràng.\n"
        "Định dạng kết quả trả về CHÍNH XÁC theo cấu trúc sau:\n"
        "SUBJECT: <tiêu đề bắt đầu bằng [CSC10014]>\n"
        "BODY:\n"
        "<nội dung email có lời chào, nội dung chi tiết, lời cảm ơn và chữ ký Nhóm sinh viên CSC10014>"
    )
    return prompt
