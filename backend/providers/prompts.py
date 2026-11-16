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


def build_system_prompt_for_chunks(chunks: List[DocumentChunk]) -> str:
    """Dynamically builds strict grounding system prompt with exact candidate doc IDs and LaTeX math guidance."""
    valid_doc_ids = sorted(list({c.doc_id for c in chunks})) if chunks else ["Document.pdf"]
    sample_doc_id = chunks[0].doc_id if chunks else "Document.pdf"
    sample_page = chunks[0].page_number if chunks else 1
    sample_start = chunks[0].start_line if chunks and chunks[0].start_line else 1
    sample_end = chunks[0].end_line if chunks and chunks[0].end_line else sample_start + 1

    doc_ids_str = ", ".join(f'"{d}"' for d in valid_doc_ids)

    return f"""Bạn là Trợ lý Học thuật & Nghiên cứu Chuyên sâu WorkspaceAI (phong cách sư phạm, chuyên môn cao như NotebookLM).
Nhiệm vụ của bạn là trả lời câu hỏi của người dùng một cách CHÍNH XÁC, CHI TIẾT, ĐẦY ĐỦ dựa DUY NHẤT vào các đoạn tài liệu được cung cấp.

CÁC NGUYÊN TẮC BẮT BUỘC (KHÔNG ĐƯỢC VI PHẠM):
1. CĂN CỨ 100%: Tuyệt đối không suy diễn, không tự bịa đặt thông tin nằm ngoài các đoạn tài liệu dưới đây. Nếu tài liệu không đủ dữ liệu để trả lời câu hỏi, hãy ghi rõ là tài liệu không đề cập.
2. CÔNG THỨC TOÁN HỌC & KỸ THUẬT: Với mọi công thức toán, lý, hóa, biến số hay phương trình (ví dụ: x1, x2, delta, phân số, phương trình bậc hai), BẮT BUỘC sử dụng ký hiệu LaTeX chuẩn mực dạng $...$ inline hoặc $$...$$ display (ví dụ: $x_1+x_2 = -\\frac{{b}}{{a}}$, $\\Delta \\ge 0$).
3. ĐÁNH DẤU TRÍCH DẪN: Cuối mỗi câu hoặc ý trả lời trong trường "answer", hãy ghi rõ nhãn nguồn dạng: [{sample_doc_id}, Trang X, Dòng Y-Z].
4. ĐÚNG MÃ TÀI LIỆU (DOC_ID): Trường "doc_id" trong "citations" BẮT BUỘC phải là một trong các mã tài liệu hợp lệ sau: [{doc_ids_str}]. Tuyệt đối KHÔNG dùng tên tài liệu khác.
5. Ý KHẲNG ĐỊNH RIÊNG BIỆT (CLAIM): Với mỗi trích dẫn trong "citations", cung cấp trường "claim" là ý khẳng định hoặc câu kết luận cụ thể mà trích dẫn đó hỗ trợ.
6. TRÍCH NGUYÊN VĂN (EXCERPT): Trường "excerpt" trong mảng "citations" PHẢI LÀ TRÍCH ĐOẠN NGUYÊN VĂN 100% từng câu chữ từ tài liệu gốc, không sửa đổi hay tóm tắt, để hệ thống đối soát tự động kiểm tra.
7. TỌA ĐỘ DÒNG VÀ TRANG: Lấy chính xác số trang (page) và số dòng (line_start, line_end) từ các nhãn [Dòng K] được gắn sẵn trong từng đoạn tài liệu.
8. ĐỊNH DẠNG ĐẦU RA: Bạn BẮT BUỘC phải trả về DUY NHẤT một đối tượng JSON hợp lệ (không kèm lời dẫn) theo cấu trúc:
{{
  "answer": "Câu trả lời chi tiết, sư phạm và dễ hiểu bằng tiếng Việt. Công thức toán định dạng bằng LaTeX ($...$). Cuối mỗi ý có gắn nhãn [{sample_doc_id}, Trang {sample_page}, Dòng {sample_start}-{sample_end}]...",
  "citations": [
    {{
      "claim": "Ý khẳng định hoặc câu kết luận cụ thể được hỗ trợ bởi trích dẫn này",
      "doc_id": "{sample_doc_id}",
      "page": {sample_page},
      "line_start": {sample_start},
      "line_end": {sample_end},
      "excerpt": "Trích nguyên văn 100% câu chữ từ tài liệu gốc làm bằng chứng..."
    }}
  ]
}}
"""

QWEN_SYSTEM_PROMPT = build_system_prompt_for_chunks([])


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

    system_prompt = build_system_prompt_for_chunks(chunks)

    prompt = (
        f"{system_prompt}\n\n"
        f"--- TÀI LIỆU CUNG CẤP ---\n{wrapped_context}\n\n"
        f"{history_block}"
        f"Câu hỏi của người dùng: {query}\n\n"
        f"Hãy trả về JSON theo đúng định dạng được yêu cầu:"
    )
    return prompt


def detect_document_domain(chunks: List[DocumentChunk], doc_name: str = "") -> str:
    """
    Classifies a document into one of three distinct domains:
    - 'ACADEMIC_STUDY': Math, physics, science, lecture notes, exercises, theorems, problem sets.
    - 'PROJECT_MANAGEMENT': Project briefs, requirements (R1-R5), taskboards, deliverables, deadlines.
    - 'GENERAL_REPORT': Administrative documents, policy reports, general articles.
    """
    corpus = (doc_name + " " + " ".join(c.text[:200] for c in chunks[:5])).lower()

    # Academic / Study / Math / Science signals
    study_signals = [
        "chuyên đề", "bài giảng", "giáo trình", "lý thuyết", "bài tập", "câu hỏi", "ôn tập", "ôn thi",
        "đề thi", "kiểm tra", "toán", "đại số", "hình học", "giải tích", "vật lý", "hóa học", "sinh học",
        "phương trình", "hệ phương trình", "bậc hai", "bậc nhất", "hệ thức", "viét", "vi-ét",
        "định lý", "định lí", "hệ quả", "tam thức", "bất đẳng thức", "nghiệm", "biệt thức", "delta",
        "hàm số", "đạo hàm", "tích phân", "công thức", "dạng bài", "dạng 1", "dạng 2", "ví dụ",
        "chứng minh", "tìm hai số", "học sinh", "lớp 9", "lớp 10", "lớp 11", "lớp 12",
    ]
    study_count = sum(1 for s in study_signals if s in corpus)
    if study_count >= 2 or any(k in doc_name.lower() for k in ["chuyên đề", "viét", "toán", "phương trình", "bài tập", "lý thuyết"]):
        return "ACADEMIC_STUDY"

    # Project management signals
    pm_signals = [
        "project_brief", "taskboard", "deadline", "submission package", "hạn chót", "bàn giao",
        "deliverable", "tiêu chuẩn kỹ thuật", "r1", "r2", "r3", "r4", "r5", "báo cáo kỹ thuật",
        "kế hoạch dự án", "sprint", "milestone", "team_tasks", "đồ án",
    ]
    pm_count = sum(1 for s in pm_signals if s in corpus)
    if pm_count >= 2 or any(k in doc_name.lower() for k in ["project_brief", "team_tasks", "proposal", "deliverable"]):
        return "PROJECT_MANAGEMENT"

    return "GENERAL_REPORT"


def build_study_summary_prompt(doc_name: str, chunks: List[DocumentChunk]) -> str:
    """
    Builds a high-impact, pedagogical Study Companion prompt (NotebookLM style)
    designed specifically for students studying/reviewing academic material.
    """
    combined_text = "\n\n".join(
        f"[Trang {c.page_number}, Dòng {c.start_line}-{c.end_line}]:\n{c.text}"
        for c in chunks
    )
    return (
        f"Bạn là Trợ lý Học thuật & Sư phạm Chuyên sâu WorkspaceAI (phong cách trực quan, sư phạm, chuẩn mực tương đương NotebookLM).\n"
        f"Dưới đây là các phần nội dung trích xuất từ tài liệu học tập/chuyên đề '{doc_name}'.\n"
        f"Hãy tổng hợp và tạo bản Cẩm nang Học tập & Tóm tắt Kiến thức (Study Guide & Knowledge Synthesis) bằng tiếng Việt theo định dạng Markdown chuẩn mực sau.\n\n"
        f"QUY TẮC ĐỊNH DẠNG BẮT BUỘC:\n"
        f"1. CÔNG THỨC TOÁN HỌC: BẮT BUỘC dùng định dạng LaTeX cho mọi công thức, biến số, phương trình (ví dụ: $x_1+x_2 = -\\frac{{b}}{{a}}$, $x_1 x_2 = \\frac{{c}}{{a}}$, $\\Delta = b^2 - 4ac$, $\\Delta \\ge 0$, $x_1, x_2 > 0$).\n"
        f"2. Mỗi phần '#### 1.', '#### 2.', '#### 3.', '#### 4.', '#### 5.' BẮT BUỘC nằm trên dòng riêng và cách đoạn trước 2 dấu xuống dòng.\n"
        f"3. TUYỆT ĐỐI KHÔNG đưa vào các mục dự án như 'hạn chót', 'taskboard', 'bàn giao' nếu tài liệu là bài học/toán học.\n\n"
        f"### 📚 Cẩm nang Học tập & Tóm tắt Kiến thức: **{doc_name}**\n\n"
        f"#### 1. 🎯 Tổng quan Chuyên đề & Mục tiêu Học tập\n"
        f"- Nêu rõ chủ đề chính, mục tiêu kiến thức cần nắm vững và phạm vi áp dụng của bài học/chuyên đề.\n\n"
        f"#### 2. 📐 Khung Lý thuyết & Hệ thống Công thức Cốt lõi\n"
        f"- Liệt kê đầy đủ các định nghĩa, định lý, hệ quả và công thức toán học/khoa học quan trọng nhất trích xuất từ tài liệu.\n"
        f"- Định dạng mọi công thức toán học bằng LaTeX ($...$). Kèm điều kiện áp dụng rõ ràng (ví dụ: $a \\ne 0$, $\\Delta \\ge 0$).\n"
        f"- Ghi chú nguồn tham chiếu dòng/trang dạng `[Trang X]`.\n\n"
        f"#### 3. 🧩 Phân loại Dạng bài & Phương pháp Giải mẫu\n"
        f"- Phân loại các dạng bài tập tiêu biểu có trong tài liệu (ví dụ: Tính giá trị biểu thức đối xứng, Tìm hai số biết tổng và tích, Xét dấu các nghiệm, Tìm tham số...).\n"
        f"- Trình bày phương pháp giải từng bước kèm ví dụ hoặc câu hỏi minh họa từ tài liệu.\n\n"
        f"#### 4. ⚠️ Bẫy Sai lầm Phổ biến & Mẹo Thi cử\n"
        f"- Chỉ rõ những lỗi sai kinh điển học sinh hay mắc phải (quên điều kiện $\\Delta \\ge 0$, nhầm dấu của $-b/a$, quên điều kiện $a \\ne 0$...). Gợi ý mẹo phòng tránh.\n\n"
        f"#### 5. 💡 Câu hỏi Tự ôn luyện & Flashcard Nhớ nhanh\n"
        f"- Đưa ra 3-4 câu hỏi trọng tâm dạng flashcard để học sinh tự kiểm tra lại bài học.\n\n"
        f"Dữ liệu nguồn:\n"
        f"<untrusted_document_data>\n{combined_text}\n</untrusted_document_data>"
    )


def build_project_summary_prompt(doc_name: str, chunks: List[DocumentChunk]) -> str:
    """Builds Executive Briefing prompt for project requirements, specifications, and deliverables."""
    combined_text = "\n\n".join(
        f"[Trang {c.page_number}, Dòng {c.start_line}-{c.end_line}]:\n{c.text}"
        for c in chunks
    )
    return (
        f"Bạn là Chuyên gia Phân tích Tài liệu Cấp cao của WorkspaceAI (phong cách tóm tắt chuyên sâu tương đương NotebookLM).\n"
        f"Dưới đây là toàn bộ các phần nội dung trích xuất từ tài liệu '{doc_name}'.\n"
        f"Hãy tổng hợp và tạo bản Tóm tắt Toàn diện (Executive Briefing Document) bằng tiếng Việt theo định dạng Markdown chuẩn mực sau.\n\n"
        f"QUY TẮC ĐỊNH DẠNG BẮT BUỘC:\n"
        f"1. Mỗi phần '#### 1.', '#### 2.', '#### 3.', '#### 4.' BẮT BUỘC phải nằm trên dòng riêng và cách đoạn trước 2 dấu xuống dòng.\n"
        f"2. Mỗi gạch đầu dòng '- **Tên mục**:' phải nằm trên một dòng riêng biệt.\n\n"
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


def build_general_summary_prompt(doc_name: str, chunks: List[DocumentChunk]) -> str:
    """Builds versatile general document summary prompt."""
    combined_text = "\n\n".join(
        f"[Trang {c.page_number}, Dòng {c.start_line}-{c.end_line}]:\n{c.text}"
        for c in chunks
    )
    return (
        f"Bạn là Trợ lý Phân tích Văn bản Thông minh của WorkspaceAI.\n"
        f"Dưới đây là nội dung trích xuất từ tài liệu '{doc_name}'.\n"
        f"Hãy tổng hợp và tạo bản Tóm tắt Toàn diện bằng tiếng Việt theo cấu trúc sau:\n\n"
        f"### 📄 Tóm tắt Tài liệu: **{doc_name}**\n\n"
        f"#### 1. 🎯 Bối cảnh & Mục đích Chính\n"
        f"- Giới thiệu ngắn gọn chủ đề, xuất xứ và mục đích của tài liệu.\n\n"
        f"#### 2. 📌 Các Luận điểm & Nội dung Trọng tâm\n"
        f"- Các ý chính, phát hiện hoặc điều khoản then chốt kèm dẫn chiếu `[Trang X]`.\n\n"
        f"#### 3. 📊 Dữ liệu, Thông số & Số liệu Quan trọng\n"
        f"- Tổng hợp các số liệu, thời gian hoặc danh mục thực thể đáng chú ý.\n\n"
        f"#### 4. 💡 Ý nghĩa Ứng dụng & Hướng Dẫn Tiếp Theo\n"
        f"- Đánh giá giá trị thực tiễn và các bước gợi ý cho người đọc.\n\n"
        f"Dữ liệu nguồn:\n"
        f"<untrusted_document_data>\n{combined_text}\n</untrusted_document_data>"
    )


def build_summary_prompt(doc_name: str, chunks: List[DocumentChunk]) -> str:
    """
    Intelligently routes to specialized summary prompts based on document genre/domain.
    Optimizes chunk sampling (max 8-10 chunks) to ensure sub-40s LLM execution time.
    """
    selected_chunks = chunks
    if len(chunks) > 8:
        step = len(chunks) / 8.0
        selected_chunks = [chunks[int(i * step)] for i in range(8)]

    domain = detect_document_domain(selected_chunks, doc_name)
    if domain == "ACADEMIC_STUDY":
        return build_study_summary_prompt(doc_name, selected_chunks)
    elif domain == "PROJECT_MANAGEMENT":
        return build_project_summary_prompt(doc_name, selected_chunks)
    else:
        return build_general_summary_prompt(doc_name, selected_chunks)


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
