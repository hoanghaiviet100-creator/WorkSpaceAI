# WorkspaceAI — Changelog & Roadmap

Tất cả các thay đổi và nâng cấp quan trọng của dự án **WorkspaceAI (CSC10014 Track C - Intelligent Document Workspace)** được ghi nhận tại đây theo chuẩn [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased] Roadmap
- [ ] Tích hợp bộ OCR đa phương thức cục bộ (Surya / PaddleOCR) cho PDF dạng ảnh quét hoàn toàn offline.
- [ ] Mở rộng Graph RAG: Trích xuất Knowledge Graph liên tài liệu (Entity - Relationship) tăng cường cho đối soát nhiều tầng.
- [ ] Hỗ trợ hàng đợi bất đồng bộ phân tán (Celery / Redis) khi ingest tài liệu dung lượng lớn (> 500 trang).

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
