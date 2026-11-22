# F2-Q00 — Scope freeze, repository survey and isolated worktree

Ngày: 2026-11-11 (Asia/Bangkok). Trạng thái: **DONE** cho Q00; F2 Quiz/Flashcards chưa triển khai.

## 1. Kết quả và phạm vi đã chốt

- F2 là **Document-Based Quiz & Flashcard Generation**, dựa riêng mục 2.1.2 và FR2.01–FR2.05 của báo cáo nhóm.
- Quiz là trắc nghiệm **một đáp án đúng**. Mặc định yêu cầu **10 câu hỏi hoặc 10 flashcards**.
- SQLite persistence thực hiện **sau luồng MVP**; không tái sử dụng task tables của F2 cũ.
- Giữ nguyên nghiệp vụ, source và kiểm thử F1/F3. Q00 chỉ thêm/cập nhật tài liệu trong worktree mới.
- Bảo toàn checkout, staging và code F2 Task Management cũ. Không commit, push, merge, reset, clean, stash hoặc xóa code.
- Số option/câu chưa được người dùng chốt. Kế hoạch cũ đề xuất 4; đây chưa phải yêu cầu FR hay quyết định đã duyệt. Q01 chỉ cần ràng buộc single-choice nhất quán.
- Số lượng mặc định 10 là số lượng yêu cầu, không phải quyền bịa nội dung cho đủ 10 khi nguồn thiếu; FR2.02 yêu cầu thông báo và hướng dẫn chọn/bổ sung nguồn.

## 2. Git/worktree thực tế

| Hạng mục | Giá trị đã đo |
| --- | --- |
| Repository | `https://github.com/hoanghaiviet100-creator/WorkSpaceAI.git` |
| Checkout legacy | `D:\Projects\WorkSpaceAI` |
| Branch legacy | `feat/f2-document-task-management` |
| HEAD legacy, local main | `730dc75f57a517adc322ec243fed66eaa47825b9` |
| Base đã fetch, HEAD mới | `da40118de0adbda33c55200d30bd9915019d2619` |
| Branch mới | `feat/f2-quiz-flashcards` |
| Worktree mới | `C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards` |
| Upstream branch mới | Chưa thiết lập; tránh tracking nhầm `origin/main` |

Đã fetch riêng `origin main --no-tags`, cập nhật remote-tracking `origin/main` từ `730dc75` tới `da40118`. Không đổi local `main` hoặc checkout legacy. Base mới chứa React preview (`0a81d94`) và F3 email FSM/backend (merge `da40118`). `audit-checkout` trong thư mục cha là snapshot audit cũ detached `d4b2411`, không phải môi trường F2 hiện tại.

Đã thử công cụ desktop `create_worktree`; công cụ không trả kết quả sau vài phút. Sau khi dừng lời gọi và kiểm tra không có worktree/branch được tạo, dùng Git fallback:

```powershell
rtk proxy git -C D:\Projects\WorkSpaceAI worktree add --no-track -b feat/f2-quiz-flashcards 'C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards' origin/main
```

Đây là Git linked worktree nằm trong workspace được phép ghi; chưa có managed-worktree attachment trong desktop. Luôn dùng rõ đường dẫn worktree mới khi làm Q01. Đường dẫn `D:\Projects\WorkSpaceAI-F2-Quiz` trong kế hoạch trước chỉ là đề xuất, không được tạo.

## 3. Bảo toàn F2 Task Management cũ

Sáu tệp có thay đổi staged và unstaged trước Q00:

| Tệp | Trạng thái |
| --- | --- |
| `.skills/codebase_map.md` | `MM` |
| `CHANGELOG.md` | `MM` |
| `backend/core/f2_schemas.py` | `AM` |
| `backend/repositories/f2_sqlite_repository.py` | `AM` |
| `tests/test_feature2_contracts.py` | `AM` |
| `tests/test_feature2_persistence.py` | `AM` |

Giữ nguyên cả `.venv312/` chưa được ignore và ba patch/diff chưa được track. Lưu bản sao riêng của sáu tệp trên, ba patch/diff, binary staged/unstaged patches và Git index. Đối chiếu trước/sau đạt **8/8 nhóm bằng chứng**, bao gồm byte Git index và manifest SHA-256 của **511 tracked/untracked files**. Không đọc/ghi lại nội dung ignored environment/cache; chúng không được chạm tới. Không chạy test trong checkout legacy.

Bằng chứng máy cục bộ ở thư mục cha:

`C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q00-2026-11-11\evidence\original\`

- `before/`, `after/`: status đầy đủ, branch/HEAD, index entries, index backup, diff binary, manifest/hash.
- `before/files/`: bản sao code/docs đang thay đổi và ba patch/diff cũ.
- `preservation-check.json`: mọi phép so sánh đều `true`.

## 4. Nguồn yêu cầu và traceability

Đã đọc trực tiếp [báo cáo nhóm](https://docs.google.com/document/d/1H7GGkDmCAjpos6EKDC5vEoSFKo3pb-Jt0HTCn7t3Uag/edit?usp=drivesdk), tab `t.m0204maz95l7`, mục **2.1.2**, bảng số 2 (index 5289–6215). Revision được lưu trong `evidence/report-fr2.json` ở thư mục output của Q00.

| FR | Nội dung áp dụng | Task dự kiến |
| --- | --- | --- |
| FR2.01 | Chọn một/nhiều tài liệu đã upload trong workspace hiện tại; chọn Quiz hoặc Flashcards | Q01 selection contract; Q02 scope; Q08 UI/API |
| FR2.02 | Nhận diện khái niệm/sự kiện; thông báo khi không đủ nội dung sử dụng được và yêu cầu thêm/chọn nguồn khác | Q02 nguồn; Q05 validation |
| FR2.03 | Sinh câu hỏi luyện tập và answer key dựa trên các tệp đã chọn | Q01 contracts; Q03 generator; Q05 validation |
| FR2.04 | Sinh card có front là prompt, back là đáp án ngắn từ nguồn đã chọn | Q01 contracts; Q04 generator; Q05 validation |
| FR2.05 | Nộp câu trả lời và xem đáp án đúng, hoặc lật flashcard để xem đáp án | Q06 interaction; Q08 UI/API |

Pattern recognition: term–definition, concept–example, procedure/steps. Abstraction giữ ý nghĩa, khái niệm, sự kiện và ngữ cảnh cần thiết, lược bỏ trang trí/header lặp và đoạn không liên quan.

Báo cáo còn các đoạn/Use Case Task Management ở nơi khác và tab chương 1 còn nói Quiz/Flashcards ngoài phạm vi. Theo chỉ dẫn đã chốt, chỉ mục 2.1.2 và FR2.01–05 điều khiển F2 mới; không tự sửa toàn bộ báo cáo hoặc mở rộng F1/F3. SSOT v1.2 chưa được tìm thấy/xác minh trong lần Q00 này và không được dùng để suy ra thêm yêu cầu.

## 5. Khảo sát kiến trúc và interface tái sử dụng

| Thành phần hiện có | Điểm dùng cho F2 / giới hạn |
| --- | --- |
| `backend/core/schemas.py:DocumentChunk` | Có `chunk_id`, `doc_id`, `doc_name`, page/line, text, `doc_version`, `doc_hash`. Tham chiếu nguồn theo snapshot; không sửa schema dùng chung trong Q01. |
| `DocumentMetadata` | Có doc ID, version ID, file hash, loại file và metadata nạp nguồn. |
| `document_service.DocumentService.ingest_file` | Tái sử dụng upload/parser/chunking; không viết lại parser PDF cho F2. |
| `workspace_repository.WorkspaceRepository` | In-memory documents/chunks; `list_documents`, `get_document_chunks`, `search`, `build_page_lookup`. Chưa có trusted workspace authorization boundary cho F2. |
| `get_document_chunks(doc_id)` / `search` | Có alias theo doc_name/case-insensitive; không mặc nhiên bảo đảm exact ID/version/workspace isolation. Q02 cần F2 adapter kiểm tra exact metadata/chunk scope; không sửa F1 để giải quyết việc này. |
| `citation_verifier.verify_citations` | Thuật toán stdlib có thể dùng qua adapter sau này. Quote tồn tại không tự chứng minh answer key đúng về nghĩa. |
| `providers/llm_provider.py`, `prompts.py` | Có adapter mock/Ollama/Gemini và QA/summary/email; chưa có study generator interface/prompt. Không dùng câu trả lời F1 làm generator Quiz. |
| `backend/main.py`, `backend/api/` | Chỉ có chat/document/email routers; chưa có F2 study API. Việc đăng ký router để task Q08. |
| `frontend/app.py`, `frontend/components/` | Streamlit hiện có; kế hoạch trước dùng Streamlit cho Q08 MVP. Q01 chưa sửa frontend. |
| `frontend/src/` | React/TypeScript/Vite tồn tại song song; hiện là preview dùng localStorage/demo, chưa gọi backend thật cho study. Giữ nguyên preview F1/F3/Tasks. |
| `database/schema.sql` | MySQL DDL lịch sử, không phải SQLite runtime hoặc study persistence. Không chạy migration trong Q00/Q01. |

Không có model, service, API, UI hoặc tests Quiz/Flashcards trên base mới. `backend/core/f2_schemas.py` và SQLite task repository chỉ tồn tại trong checkout legacy, không được copy vào worktree mới.

## 6. Baseline đã chạy

| Check | Kết quả thực tế |
| --- | --- |
| `verify.py` | Exit 0; **30 passed**, 1 warning Starlette/TestClient deprecation |
| AST | **40 Python files PASS** |
| R2 stdlib purity | **PASS** |
| `pnpm install --frozen-lockfile` | Exit 0; không đổi lockfile |
| `pnpm build` (`tsc -b && vite build`) | Exit 0; Vite 6.4.5, **1595 modules transformed** |
| Source diff sau baseline | Sạch trước khi thêm tài liệu Q00 |
| Preservation legacy | **PASS**, byte index, staged/unstaged diff và 511 file hashes không đổi |

Runtime: CPython **3.12.14**, Pydantic **2.14.2**, pytest **9.2.0**, SQLite runtime **3.53.1**, Node **v24.22.1**, pnpm CLI báo **11.25.0**. SQLite runtime chỉ là thông tin môi trường, không có study persistence đã triển khai.

Python dùng môi trường audit đã có tại `..\tmp\workspaceai-audit-venv\Scripts\python.exe`. Các tiến trình test dùng `LLM_PROVIDER=mock`, `EMAIL_DISPATCH_MODE=local_mock`. Test giả lập SMTP exception bằng mocks; không gửi email hoặc gọi LLM thật. Chạy ngoài sandbox do TestClient cần loopback socket. Không tạo/sửa environment legacy.

Raw logs, command, cwd, environment overrides và exit codes nằm ở:

`C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q00-2026-11-11\evidence\baseline\`

File `frontend-install.json` ghi đúng subprocess exit 0. Lần đầu wrapper bị lỗi in ký tự Unicode sau khi đã lưu log/kết quả; đã sửa encoding stdout trong helper ngoài repository. Build sau đó đạt exit 0; không cần cài lại dependency.

Lệnh tái lập trong PowerShell:

```powershell
Set-Location 'C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards'
$env:LLM_PROVIDER = 'mock'
$env:EMAIL_DISPATCH_MODE = 'local_mock'
rtk proxy 'C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe' verify.py
Set-Location frontend
rtk proxy pnpm build
```

Baseline này chứng minh suite F1/F3 hiện có và build hiện tại chạy được; không chứng minh F2 mới đã hoạt động. Không dùng kết quả 104 tests legacy thay cho baseline này. Chưa chạy browser/UI E2E hoặc đánh giá chất lượng trên LLM/tài liệu thật.

## 7. Chưa hoàn thành / bàn giao

- Q01 Data Contracts chưa viết; packet ở [F2-Q01_TASK_CONTEXT_PACKET.md](F2-Q01_TASK_CONTEXT_PACKET.md).
- Q02 source extraction, Q03 Quiz generation, Q04 Flashcards, Q05 grounding/validation, Q06 practice chưa triển khai.
- Q08 API + Streamlit và Q09 evaluation/release chưa thực hiện. Q07 SQLite được xếp sau MVP theo quyết định mới nhất, dù số task giữ nguyên kế hoạch cũ.
- Source/workspace authorization, answer-key semantic validation và browser integration cần bằng chứng ở task tương ứng.
- Chưa có commit/PR/push/merge. Tài liệu Q00 để unstaged/untracked cho người dùng review.

Q00 đạt các tiêu chí: legacy còn nguyên; local main không đổi; branch/worktree tách biệt từ origin/main; interface đã khảo sát; baseline chạy được; có yêu cầu và packet Q01. Không cần hỏi lại các quyết định MVP đã chốt trước khi bắt đầu task tiếp theo khi được yêu cầu.
