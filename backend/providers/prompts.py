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
3. Ý KHẲNG ĐỊNH RIÊNG BIỆT (CLAIM): Với mỗi trích dẫn trong "citations", cung cấp trường "claim" là ý khẳng định hoặc câu kết luận cụ thể mà trích dẫn đó hỗ trợ (để hệ thống kiểm chứng theo từng luận điểm).
4. TRÍCH NGUYÊN VĂN (EXCERPT): Trường "excerpt" trong mảng "citations" PHẢI LÀ TRÍCH ĐOẠN NGUYÊN VĂN 100% từng câu chữ từ tài liệu gốc, không sửa đổi hay tóm tắt, để hệ thống đối soát tự động kiểm tra.
5. TỌA ĐỘ DÒNG VÀ TRANG: Lấy chính xác số trang (page) và số dòng (line_start, line_end) từ các nhãn [Dòng K] được gắn sẵn trong từng đoạn tài liệu.
6. ĐỊNH DẠNG ĐẦU RA: Bạn BẮT BUỘC phải trả về DUY NHẤT một đối tượng JSON hợp lệ (không kèm lời dẫn) theo cấu trúc:
{
  "answer": "Câu trả lời chi tiết bằng tiếng Việt, giải thích đầy đủ các ý hỏi, cuối mỗi ý có gắn nhãn [Tên tài liệu, Trang X, Dòng Y-Z]...",
  "citations": [
    {
      "claim": "Ý khẳng định hoặc câu kết luận cụ thể được hỗ trợ bởi trích dẫn này",
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
    """
    Builds comprehensive NotebookLM-style Executive Briefing prompt.
    Structures outputs into:
    1. Executive Summary & Purpose
    2. Core Technical Themes & Deliverables
    3. Quantitative Metrics, Deadlines & Policies
    4. Key Actionable Takeaways & Next Steps
    """
    # Sample representative chunks across distinct pages if total length is very large
    selected_chunks = chunks
    if len(chunks) > 12:
        pages_seen = set()
        picked = []
        for c in chunks:
            if c.page_number not in pages_seen:
                pages_seen.add(c.page_number)
                picked.append(c)
        if len(picked) < 8:
            picked.extend(chunks[:8])
        selected_chunks = picked[:12]

    combined_text = "\n\n".join(
        f"[Trang {c.page_number}, Dòng {c.start_line}-{c.end_line}]:\n{c.text}"
        for c in selected_chunks
    )
    prompt = (
        f"Bạn là Chuyên gia Phân tích Tài liệu Cấp cao của WorkspaceAI (phong cách tóm tắt chuyên sâu tương đương NotebookLM).\n"
        f"Dưới đây là toàn bộ các phần nội dung trích xuất từ tài liệu '{doc_name}'.\n"
        f"Hãy tổng hợp và tạo bản Tóm tắt Toàn diện (Executive Briefing Document) bằng tiếng Việt theo định dạng Markdown chuẩn mực sau:\n\n"
        f"### 📄 Tóm tắt Tài liệu Toàn diện: **{doc_name}**\n\n"
        f"#### 1. 🎯 Tổng quan Điều hành & Bản chất Tài liệu (Executive Briefing)\n"
        f"- Nêu rõ mục đích, phạm vi, đối tượng áp dụng và bối cảnh chính của tài liệu.\n\n"
        f"#### 2. 📌 Các Trọng tâm Kỹ thuật & Yêu cầu Cốt lõi (Core Themes & Requirements)\n"
        f"- Trình bày chi tiết các tiêu chuẩn kỹ thuật, module hoặc tính năng bắt buộc.\n"
        f"- Với mỗi ý quan trọng, hãy ghi chú nguồn tham chiếu dạng `[Trang X]`.\n\n"
        f"#### 3. ⏱️ Dữ liệu Định lượng, Hạn chót & Thành phần Hồ sơ (Metrics & Deadlines)\n"
        f"- Liệt kê cụ thể các con số định lượng (số trang, tỷ lệ %, điểm số, dung lượng).\n"
        f"- Các mốc thời hạn (deadline) và danh mục các thành phần hồ sơ nộp bài/bàn giao.\n\n"
        f"#### 4. 💡 Khuyến nghị Thực thi & Những Điều Cần Làm Ngay (Actionable Takeaways)\n"
        f"- Các rủi ro tiềm ẩn, lưu ý quan trọng cần tuân thủ và gợi ý các bước triển khai tiếp theo cho nhóm.\n\n"
        f"Dữ liệu nguồn:\n"
        f"<untrusted_document_data>\n{combined_text}\n</untrusted_document_data>"
    )
    return prompt


def build_email_prompt(
    query: str,
    chunks: List[DocumentChunk],
    recipient_email: Optional[str] = None,
) -> str:
    """Builds dynamic email drafting prompt – fully AI-generated, NO static template."""
    context_str = "\n".join(f"- [{c.doc_name} p.{c.page_number}]: {c.text}" for c in chunks) if chunks else ""
    context_block = f"\nThông tin workspace liên quan:\n{context_str}\n" if context_str else ""
    prompt = (
        "Bạn là trợ lý soạn email thông minh cho sinh viên.\n\n"
        f"Yêu cầu: \"{query}\"\n"
        f"Người nhận: {recipient_email or 'thầy/cô'}\n"
        f"{context_block}\n"
        "Hãy VIẾT email hoàn chỉnh phù hợp với yêu cầu trên theo phong cách tự nhiên của người gửi.\n"
        "QUAN TRỌNG:\n"
        "- Nếu là xin nghỉ học / báo bệnh / việc cá nhân → viết giọng sinh viên nhắn thầy cô, thân thiện, ngắn gọn (VD: 'Dạ thầy/cô ơi, hôm nay em...')\n"
        "- Nếu là báo cáo / đề xuất chính thức → viết trang trọng hơn\n"
        "- KHÔNG dùng khuôn mẫu cứng 'Kính gửi Quý Thầy/Cô, Em đại diện nhóm thực hiện đồ án CSC10014...'\n"
        "- Tiêu đề phải ngắn gọn, phản ánh đúng nội dung\n\n"
        "Ví dụ cho email xin nghỉ học:\n"
        "SUBJECT: Xin nghỉ học môn Giải Tích hôm nay\n"
        "BODY:\n"
        "Dạ thầy ơi, hôm nay em bị sốt nên không thể đến lớp được ạ. Em xin phép được nghỉ buổi học Giải Tích hôm nay. Em sẽ bù bài đầy đủ ạ, em cảm ơn thầy!\n\n"
        "Giờ hãy viết email theo yêu cầu trên (KHÔNG copy y chang ví dụ, tự sinh nội dung phù hợp):\n"
        "SUBJECT: <tiêu đề ngắn gọn>\n"
        "BODY:\n"
        "<nội dung email tự nhiên theo ngữ cảnh, bao gồm lời chào phù hợp và chữ ký>"
    )
    return prompt
