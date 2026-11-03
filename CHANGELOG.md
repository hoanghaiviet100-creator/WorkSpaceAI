# WorkspaceAI — Changelog & Roadmap

Tất cả các thay đổi và nâng cấp quan trọng của dự án **WorkspaceAI (CSC10014 Track C - Intelligent Document Workspace)** được ghi nhận tại đây theo chuẩn [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased] Roadmap
- [ ] Tích hợp bộ OCR đa phương thức cục bộ (Surya / PaddleOCR) cho PDF dạng ảnh quét hoàn toàn offline.
- [ ] Mở rộng Graph RAG: Trích xuất Knowledge Graph liên tài liệu (Entity - Relationship) tăng cường cho đối soát nhiều tầng.
- [ ] Hỗ trợ hàng đợi bất đồng bộ phân tán (Celery / Redis) khi ingest tài liệu dung lượng lớn (> 500 trang).

---

## [2.6.1] - 2026-11-03 — Dynamic Natural Language Target Resolution & Robust Gemini Live Fallback
### Added
- **Natural Language Summary Target Resolution (`resolve_summary_target` trong `qa_service.py`)**:
  - Bóc tách mục tiêu tóm tắt từ câu hỏi tự nhiên: hỗ trợ tên file bỏ đuôi mở rộng (stem matching như `team_8_proposal` khớp `Team_8_Proposal.pdf`), chuẩn hóa dấu cách và gạch dưới (`team 8 proposal` khớp `Team_8_Proposal`).
  - Tự động ưu tiên tài liệu đang được tick chọn trong Document Library (`selected_doc_ids`) cho các câu hỏi tổng quan ("tóm tắt tài liệu này", "tóm tắt file vừa chọn").
  - Bổ sung bài kiểm thử `test_13_resolve_summary_target_stem_and_selection` và `test_14_frontend_state_initialization` (20/20 tests PASSED).

### Fixed
- **Khắc phục Lỗi NameError `settings` trong `frontend/state.py`**: Bổ sung `from backend.core.config import settings` và tham số mặc định cho `ollama_online()`, giúp Streamlit khởi chạy mượt mà ngay lần đầu.
- **Khắc phục Lỗi Tóm tắt Nhầm File (`Project_Brief.pdf`)**: Giải quyết triệt để lỗi người dùng yêu cầu *"Tóm tắt file Team_8_proposal ấy"* nhưng hệ thống lại tóm tắt `Project_Brief.pdf` do không tìm thấy đuôi `.pdf` trong câu hỏi và mặc định lấy file đầu tiên.
- **Tự động Kích hoạt AI Engine trong Streamlit (`frontend/state.py`)**: Sửa lỗi giao diện luôn mặc định ở chế độ `"offline"` (Mock Engine). Giờ đây tự động phát hiện `GEMINI_API_KEY` để chọn ngay `"gemini"`, hoặc nhận diện Ollama đang chạy để chọn `"ollama"`.
- **Khắc phục Lỗi 404 Google Gemini API (`backend/providers/llm_provider.py`)**: Chuyển sang mô hình chính thức hoạt động ổn định `gemini-flash-lite-latest` kèm cơ chế multi-model fallback tự động.
- **Cải tiến Trả lời khi không trúng Intent Tóm tắt**: Không còn in thô mã định dạng chunk khi ở chế độ offline, hỗ trợ câu trả lời tự nhiên, có cấu trúc rõ ràng.

---


## [2.6.0] - 2026-11-03 — NotebookLM-Grade Evidence Q&A & Complete Document Summarization
### Added
- **Tóm tắt Tài liệu Toàn diện chuẩn NotebookLM (`summarize_document`)**: Tạo bản tóm tắt phân cấp 4 phần chuyên nghiệp (Executive Briefing, Core Themes kèm nhãn nguồn trang, Quantitative Metrics & Deadlines, Actionable Takeaways) và sinh trích dẫn trích lục đa trang cho phép click soi chiếu tức thì.
- **Tô sáng Trích dẫn Nhiều dòng (Multi-line Citation Highlighting)**: Cải tiến `highlight_evidence_in_page()` xử lý span trích dẫn trải dài qua nhiều dòng vật lý mà không làm rách thẻ HTML.
- **Fuzzy Doc ID & Extension Resolver**: `citation_verifier.py` và `workspace_repository.py` hỗ trợ đối soát linh hoạt tên file không phân biệt hoa thường và tự động bù đuôi `.pdf`/`.txt`.
- **Adaptive Top-K & Page Diversity**: Tự động tăng `top_k = 5` khi câu hỏi mang tính tổng quan, bao quát đa dạng các trang khác nhau thay vì dồn cục vào 1 trang.
- **Mở rộng Bộ Kiểm Thử (18/18 Tests PASSED)**: Bổ sung `test_10_multiline_evidence_highlighting`, `test_11_notebooklm_comprehensive_document_summary`, `test_12_flexible_doc_id_matching`.

### Fixed
- **Khắc phục Lỗi Xếp hạng Pinpoint Reranker**: Áp dụng Relevance Gate và sắp xếp theo `(x.score, x.pinpoint_score, x.rrf_score)` để đảm bảo các chunk có liên quan từ vựng/ngữ nghĩa luôn được ưu tiên, ngăn chặn chunk rác chiếm top chỉ vì vô tình chứa số.
- **Khử trùng lặp dòng gối đầu trong `build_page_lookup()`**: Tự động deduplicate các dòng overlap 2 dòng giữa các chunk kề nhau khi ghép nối toàn văn trang gốc cho Evidence Viewer.
- **Ngăn chặn Hiện tượng Trôi Chủ đề (Topic Drift) trong `expand_contextual_query()`**: Bỏ nhầm các từ hỏi (*khi nào, ở đâu*) ra khỏi danh sách đại từ tham chiếu, chỉ mở rộng ngữ cảnh khi câu hỏi thực sự chứa đại từ anaphoric (*nó, đó, ở trên, còn...*) hoặc là câu cụt.
- **Granular Claim Statement Parsing trong `llm_provider.py`**: Gán từng câu khẳng định cụ thể cho từng trích dẫn trong mảng `citations`, khắc phục tình trạng 1 trích dẫn sai làm báo cờ đỏ toàn bộ câu trả lời.

---

## [2.5.0] - 2026-11-02 — AI-Native Architecture & High-Precision Grounded Workspace
### Added
- **Script kiểm định 1-chạm `verify.py`**: Tự động duyệt cú pháp AST toàn bộ mã nguồn, kiểm tra nghiêm ngặt ranh giới R2 Stdlib Purity (zero third-party leak), và thực thi toàn bộ test suite chỉ bằng lệnh `python verify.py`.
- **Bản đồ chữ ký & schema `.skills/codebase_map.md`**: Tổng hợp toàn bộ sơ đồ module, Pydantic schemas và public function signatures, giúp AI Agent nắm bắt 100% ngữ cảnh trong một lần đọc duy nhất (tiết kiệm hơn 75% lượng token dò file).
- **Pinpoint Reranker trong `workspace_repository.py`**: Tự động phát hiện ý định hỏi về số liệu, thời hạn, thực thể (*khi nào, hạn nộp, bao nhiêu, tỷ lệ, deadline...*) để cộng điểm ưu tiên chính xác cho chunk mang thông tin chi tiết trước khi gửi sang LLM.
- **Tự động trích xuất Yêu cầu `extract_requirements_from_workspace()` trong `reconciliation_service.py`**: Quét văn bản tài liệu người dùng tải lên để tự động bóc tách các mốc deadline, tiêu chí bắt buộc thành danh sách `RequirementItem` thực tế.
- **Tương tác động trên `reconciliation_board.py`**: Nút bấm *"🔄 Trích xuất Yêu cầu từ Tài liệu đã chọn"* cho phép đối soát chéo đề bài vừa nạp với bảng công việc Kanban theo thời gian thực.
- **Tài liệu hợp nhất `.skills/backend_and_rag_skill.md`**: Gộp các quy tắc Backend FastAPI, Hybrid RAG và chuẩn prompt JSON Ollama `qwen2.5:7b`.

### Changed
- **Bảo toàn 100% Stdlib tại `backend/algorithms/`**: Chuẩn hóa toàn bộ cấu trúc dữ liệu (`ReconciliationSummary`, `ReconciledItemReport`, `DateConflict`) sang `@dataclass` thuần chuẩn Python, loại bỏ hoàn toàn việc phụ thuộc Pydantic trong `backend/algorithms/`.
- **Cải tiến bóc tách văn bản trong `document_service.py`**: Giữ nguyên vẹn cấu trúc dòng bảng biểu (`|` và phân cột) cũng như các dòng chứa mốc số liệu, hạn nộp.
- **Cập nhật `AGENTS.md`**: Chuẩn hóa quy trình Fast-Context Protocol và tích hợp các luật bất biến kiến trúc Layered Architecture.

### Removed
- Xóa bỏ các tệp skill dư thừa: `.skills/architecture_guard.md`, `.skills/backendFastAPISkill.md`, `.skills/rag_qwen_optimization_skill.md`.

---

## [2.0.0] - 2026-11-02 — Modular Frontend Architecture & Qwen2.5 Optimization
### Added
- **Kiến trúc Modular Component tại `frontend/`**: Tách nhỏ `frontend/app.py` (từ 52.3KB) thành `state.py`, `styles.py` và thư mục `components/` (`sidebar_library.py`, `chat_panel.py`, `evidence_viewer.py`, `reconciliation_board.py`, `email_assistant.py`).
- **SubwordHashVectorizer (384-d)** trong `embedding_provider.py`: Bộ sinh vector đặc trưng thuần NumPy giúp nhánh Dense Cosine Similarity luôn hoạt động ngay cả khi môi trường không có PyTorch.
- **Tokenizer Bi-gram tiếng Việt** trong `workspace_repository.py`: Tách từ ghép kỹ thuật (*hạn_nộp*, *báo_cáo*, *đối_soát*...) giúp BM25 bắt trúng ngữ nghĩa từ vựng.
- **Tách biệt Prompt Templates tại `prompts.py`**: Hệ thống hóa prompt Grounded QA, Summary và Email Drafting.

### Fixed
- Khắc phục lỗi ngắt dòng cứng PDF bằng thuật toán Sliding Window có overlap 2 dòng.
- Sửa lỗi lệch tọa độ trích dẫn với hàm `align_claim_to_chunks()`.

---

## [1.0.0] - 2026-10-26 — Khởi tạo Khung Dự án CSC10014 Track C
- Khởi tạo kiến trúc phân tầng CSC10014: REQUEST -> UNDERSTAND -> ROUTE -> RETRIEVE/COMPUTE -> REASON -> VERIFY -> RESPOND/ACT.
- Cài đặt 3 thuật toán tất định R2: Reconciliation, Citation Verifier, Email FSM.
- Tích hợp cổng lọc an toàn R7 Safeguard chống prompt injection.
