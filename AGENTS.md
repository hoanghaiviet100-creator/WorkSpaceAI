# WorkspaceAI Agent Protocol & System Guardrails (v2.5)

## 1. Fast-Context Protocol (Chống Lãng phí Token)
Khi bắt đầu bất kỳ nhiệm vụ nào, AI Agent **KHÔNG CẦN ĐỌC DÒ TỪNG TỆP MÃ NGUỒN**. Chỉ cần đọc tuần tự 3 tệp sau để nắm trọn 100% ngữ cảnh:
1. **`AGENTS.md`** (Tệp này): Nắm bắt ranh giới kiến trúc và luật bất biến.
2. **`.skills/codebase_map.md`**: Bản đồ toàn bộ Pydantic schemas, trường dữ liệu và chữ ký hàm public.
3. **`CHANGELOG.md`**: Lịch sử phiên bản, các tính năng vừa cập nhật và roadmap tương lai.
4. Khi cần chuyên sâu một lĩnh vực cụ thể, mới mở thêm:
   - `.skills/backend_and_rag_skill.md`: Chi tiết FastAPI, RAG, Ollama Qwen2.5-7B JSON prompt.
   - `.skills/frontend_streamlit_skill.md`: Chi tiết Streamlit 3 cột & Academic Teal UI.

## 2. Kiểm định 1-Chạm Bắt buộc (Single-Touch Verification)
Sau khi hoàn thành bất kỳ chỉnh sửa mã nguồn nào, AI Agent **CHỈ CẦN CHẠY 1 LỆNH DUY NHẤT**:
```bash
python verify.py
```
Lệnh này tự động kiểm tra:
- **Bước 1**: AST Syntax Check toàn bộ các file `.py`.
- **Bước 2**: R2 Stdlib Purity Gate (nghiêm cấm rò rỉ `pydantic`, `fastapi`, `numpy`, `httpx` vào `backend/algorithms/`).
- **Bước 3**: Chạy toàn bộ bộ test suite `pytest -v` (yêu cầu 100% PASSED).

---

## 3. Ranh giới Kiến trúc Phân tầng (Layered Architecture Rules)
- **`backend/core/`**: Pydantic schemas (`schemas.py`), cấu hình môi trường (`config.py`), và cổng lọc an toàn Safeguard XML (`guardrails.py`).
- **`backend/algorithms/`**: **100% PURE PYTHON STANDARD LIBRARY BẤT BIẾN**. Tuyệt đối KHÔNG import thư viện ngoài (`pydantic`, `fastapi`, `numpy`, `httpx`, `rank_bm25`). Không thực hiện network/file I/O.
- **`backend/repositories/`**: Lập chỉ mục cục bộ, Hybrid BM25 + Dense RRF Search và Pinpoint Reranker (`workspace_repository.py`).
- **`backend/providers/`**: Bộ sinh vector NumPy (`embedding_provider.py`), kết nối LLM Ollama/Gemini (`llm_provider.py`), và Prompt engineering (`prompts.py`).
- **`backend/services/`**: Nghiệp vụ chính gồm Ingestion (`document_service.py`), Q&A trích dẫn (`qa_service.py`), Đối soát tự động (`reconciliation_service.py`), Email FSM (`email_service.py`), và Phân luồng câu hỏi (`router_service.py`).
- **`backend/api/`**: Chỉ chứa route handlers FastAPI mỏng; ủy thác 100% xử lý cho tầng `services/` hoặc `algorithms/`.
- **`frontend/`**: Kiến trúc Modular Component Streamlit 3 cột (`state.py`, `styles.py`, `components/*`).

---

## 4. CSC10014 Pipeline Chuẩn
Mọi luồng xử lý đều tuân thủ 7 bước:
`REQUEST -> UNDERSTAND -> ROUTE -> RETRIEVE/COMPUTE -> REASON -> VERIFY -> RESPOND/ACT`

- **AUTONOMOUS MODE**: Áp dụng trực tiếp mọi chỉnh sửa/tạo tệp và chạy `python verify.py` tự động mà không cần hỏi lại người dùng ở từng thao tác nhỏ.
