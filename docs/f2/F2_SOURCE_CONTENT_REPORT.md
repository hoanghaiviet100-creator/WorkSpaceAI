# F2 — Source inspection, broader generation and draft review

Ngày thực hiện: 2026-11-13. Phạm vi được duyệt: ba hướng đầu; chưa làm hướng tự giải/kiểm tra bài tập Toán/Lý. Báo cáo này cập nhật giới hạn definition-only trong các báo cáo cũ; các báo cáo Q00–Q06 vẫn giữ nguyên.

## Branch và bảo toàn

- Branch: `feat/f2-quiz-flashcards`.
- Worktree: `C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards`.
- HEAD và origin/main: `da40118de0adbda33c55200d30bd9915019d2619`.
- Không stage/commit/push/merge/reset/clean/stash hay xóa code cũ. F1/F3 không sửa.
- Baseline trước đợt này: 551 tests. Snapshot 46 file trước sửa tại `output/f2-source-content-2026-11-13/evidence/before-files-sha256.json`, gồm 44 file F2 untracked và 2 tài liệu tracked.
- Audit cuối nằm ngoài checkout: `output/f2-source-content-2026-11-13/evidence/final-audit.json`; so legacy `D:\Projects\WorkSpaceAI` với snapshot Q00, gồm branch/HEAD/index/diffs và 511 file tracked/untracked không ignored.

## Thực hiện

1. **Xem nội dung trích xuất:** nút opt-in hiển thị text chunk thực tế, trang/dòng, số ký tự, số trang có chữ, số đoạn đủ quy tắc Q02 và phân loại definition/fact/example/procedure. Số ký tự tính trên dòng duy nhất theo trang/dòng, chunk hiển thị có thể chồng. Cảnh báo lớp chữ PDF không chứng nhận công thức/hình/bảng; cảnh báo ít chữ, không có đoạn hợp lệ, ký tự thay thế/font riêng, nhiều ký hiệu và chỉ dẫn đáng ngờ. Dùng kiểm tra scope/provenance hiện có, không gọi AI.
2. **Sinh từ nội dung:** AI mặc định chế độ `Nội dung tài liệu`, cho phép sự kiện/quy tắc/điều kiện/ví dụ/quy trình và câu hỏi tự nhiên từ nguồn. Prompt yêu cầu giữ điều kiện, phủ định, đơn vị, trích dẫn liên quan, không bù số lượng, không tự giải bài Toán/Lý. Có thể chọn lại `Định nghĩa (như bản cũ)`. Offline giữ nguyên. Wrapper gọi transport Gemini/NIM/Ollama hiện có; Q03/Q04 vẫn parse JSON và hydrate source refs ở backend.
3. **Kiểm chứng/bản nháp:** mẫu định nghĩa cũ tiếp tục hoạt động. Thêm điền một chỗ trống khôi phục toàn bộ quote sau chuẩn hóa whitespace, >=4 từ ngữ cảnh, đúng một lựa chọn khớp, giữ case/đơn vị/dấu câu, mọi trích dẫn hỗ trợ, không có biến thể mâu thuẫn trong nguồn đã chọn. Quiz explanation phải trùng toàn quote. Sai key nhận diện được bị REJECTED; câu tự nhiên/diễn giải hoặc bằng chứng chưa đủ giữ REVIEW_REQUIRED.

Bản nháp có nhãn chế độ soạn/review, hiển thị đáp án **AI đề xuất**, trích dẫn và lý do từng mục. Khi nguồn hiện tại không MATCHED, nội dung lưu trong nháp không hiển thị. Không có nút gắn VERIFIED thủ công. Bộ có cả mục đạt và chưa đạt giữ toàn bộ bản gốc; người dùng có thể chủ động chọn `Luyện tập N mục đã kiểm chứng`. Service đọc/kiểm chứng lại, tạo subset giữ selection/requested_count, Q06 kiểm tra độc lập lần nữa. Luyện tập ẩn phần soạn đáp án; có thể quay lại nháp bằng nút rõ ràng.

Diagnostics phân biệt nguồn không có đoạn đủ điều kiện (không gọi bộ sinh), bộ sinh trả danh sách rỗng, lỗi API, đầu ra không hợp lệ và nội dung cần review. Vendor error hiển thị HTTP status an toàn, không body/key. Chọn provider/nhập key chưa chứng minh kết nối/quota hoạt động.

## File tạo/chỉnh sửa

| Hành động | File |
|---|---|
| Tạo | `backend/algorithms/f2_content_support.py` |
| Tạo | `backend/providers/f2_source_content_provider.py` |
| Tạo | `backend/services/f2_study_draft_service.py` |
| Tạo | `tests/test_f2_source_content.py` |
| Tạo | `tests/test_f2_source_content_ui.py` |
| Tạo | `docs/f2/F2_SOURCE_CONTENT_REPORT.md` |
| Sửa | `backend/services/f2_source_service.py` — thêm inspection, prepare giữ nguyên |
| Sửa | `backend/services/f2_study_validation_service.py` — gọi support mở rộng |
| Sửa | `backend/core/f2_validation_schemas.py` — method V2/message |
| Sửa | `backend/providers/f2_gemini_provider.py` — HTTP error status |
| Sửa | `backend/providers/f2_nvidia_nim_provider.py` — HTTP error status |
| Sửa | `frontend/components/f2_manual_panel.py` — preview/mode/draft/subset/diagnostics |
| Sửa | `frontend/f2_manual_app.py` — mô tả phạm vi thực tế |
| Sửa | `.skills/codebase_map.md` |
| Sửa | `CHANGELOG.md` |

## Kiểm thử thực tế

Runtime: CPython 3.12.14 tại `C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe`. Wrapper lưu command/cwd/env/exit code/log nguyên bản. Cloud test dùng `httpx.MockTransport`, không gọi Google/NVIDIA thật. AppTest dùng DocumentService thật để ingest TXT trong test; không seed dữ liệu vào sản phẩm.

Chạy trong worktree (lệnh bên dưới tương đương command ghi trong evidence; wrapper bên ngoài checkout là `output/f2-source-content-2026-11-13/run_check.py`):

```powershell
rtk proxy 'C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe' -m pytest tests/test_f2_source_content.py tests/test_f2_source_content_ui.py tests/test_f2_manual_ui.py tests/test_f2_ai_providers.py tests/test_f2_nvidia_nim_provider.py -v
rtk proxy 'C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe' verify.py
```

| Kiểm tra | Kết quả |
|---|---|
| Tập trung | 158 passed in 11.13s; exit 0 |
| Backend/protocol mới | 45 passed trong focused/full |
| UI mới | 13 passed trong focused/full |
| 100 UI/Gemini/NIM test cũ | Pass, file test cũ không sửa |
| Toàn bộ `verify.py` | 609 passed, 1 warning in 12.49s; exit 0 |
| AST / R2 | 78 tệp hợp lệ / PASS |

Có một chỉnh sửa chặn hiển thị quote nháp stale và assertion tương ứng sau focused; full verify phía trên chạy sau chỉnh sửa đó và pass. Warning còn lại là Starlette/TestClient dùng httpx đã deprecated, không phải lỗi test.

Evidence ngoài checkout:

- `output/f2-source-content-2026-11-13/evidence/baseline/focused.json` và `focused.log`.
- `output/f2-source-content-2026-11-13/evidence/baseline/verify.json` và `verify.log`.
- `output/f2-source-content-2026-11-13/evidence/source-content-only.patch`, `final-audit.json`, `legacy-preservation.json`, `status.txt`, `worktrees.txt`.
- `output/f2-source-content-2026-11-13/evidence/ui-source-content.png`: UI trình duyệt local với Gemini / `Nội dung tài liệu`; key rỗng, chưa nạp tài liệu, không có kết quả tạo giả.

Kiểm tra trình duyệt: tab cũ báo Connection error, không có listener :8512 và PID cũ không tồn tại. Khởi động Streamlit ẩn mới, bind `127.0.0.1:8512`, PID 15824; metadata/log ở `output/f2-source-content-2026-11-13/server.*`. Reload thành công, xác nhận UI mới và chế độ sinh. Không upload PDF/key hoặc nhấn tạo trong trình duyệt. Vì server cũ đã dừng, phiên mới trống; không thể khôi phục dữ liệu chỉ lưu trong process cũ. Migration hot reload giữ repository/key widget được kiểm thử bằng AppTest, không được coi là khôi phục process đã mất.

## Giới hạn còn lại và bước tiếp theo

- Kiểm chứng tự động **chỉ** chứng minh đối chiếu nguyên văn theo mẫu định nghĩa hoặc cloze. Không tự chứng minh đúng sai của mọi câu hỏi diễn giải, tính chính xác ngoài đời hoặc chất lượng tài liệu. Không có semantic judge tổng quát hay người duyệt thực hiện qua nút approve.
- Không OCR, không đối chiếu hình/công thức gốc, không tự giải Toán/Lý. PDF đề bài thuần túy, ảnh hoặc công thức bị hỏng có thể tiếp tục không tạo được học liệu đạt kiểm chứng; không nới gate để hiển thị thành công giả.
- Không xác minh live key/quota/model hay đánh giá hai PDF thực tế của người dùng trong đợt này. API/UI hiện là harness local, chưa phải full Q08 auth/API tích hợp. SQLite vẫn sau MVP.
- Thử thủ công tiếp: mở `http://127.0.0.1:8512/`, nạp lại tài liệu, chọn đúng nguồn, bấm `Xem nội dung đã trích xuất`; kiểm tra công thức/dòng trước. Chọn Quiz/Flashcards, Gemini/NIM/Ollama và `Nội dung tài liệu`; tự nhập key rồi bấm tạo. Nếu vào nháp, xem trạng thái/lý do/citation; chỉ chọn subset được kiểm chứng khi phù hợp. Nếu lỗi API, dùng HTTP status hiển thị để kiểm tra cấu hình/quota/quyền model.
