# Task Context Packet — F2-Q01: Data Contracts

Status: **READY — chưa triển khai**. Prepared 2026-11-11 (Asia/Bangkok). Packet này chỉ dành cho Q01, dựa trên Q00 đã hoàn thành và kế hoạch trong chat “Kiểm tra và lập kế hoạch F2”.

## 1. Mục tiêu, FR mapping và nguồn yêu cầu

Định nghĩa model dùng chung cho chọn nguồn, Quiz và Flashcards; kiểm tra dữ liệu cấu trúc trước khi nối generator/service/UI. Mapping: **FR2.01, FR2.03, FR2.04**; hỗ trợ provenance cho FR2.02/FR2.05. Chưa tuyên bố hoàn thành luồng sản phẩm nào qua schema tests.

Nguồn: [báo cáo nhóm](https://docs.google.com/document/d/1H7GGkDmCAjpos6EKDC5vEoSFKo3pb-Jt0HTCn7t3Uag/edit?usp=drivesdk), tab `t.m0204maz95l7`, mục **2.1.2**, bảng FR2.01–FR2.05. Các đoạn Task Management khác của báo cáo không điều khiển F2 mới. Đọc thêm [Q00 report](F2-Q00_REPORT.md); raw requirement snapshot ở output Q00.

Quyết định không hỏi lại: Quiz single-choice một đáp án đúng; mặc định 10 questions/cards; SQLite sau MVP; F1/F3 giữ nguyên; bảo toàn legacy. Không đưa spaced repetition, adaptive learning, lịch sử thi, leaderboard hoặc migration task vào Q01.

## 2. Môi trường và Git bắt buộc

```text
Repository: https://github.com/hoanghaiviet100-creator/WorkSpaceAI.git
Working directory: C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards
Branch: feat/f2-quiz-flashcards
Base/HEAD tại bàn giao: da40118de0adbda33c55200d30bd9915019d2619
Upstream: chưa thiết lập
Python: C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe
Legacy, chỉ bảo toàn: D:\Projects\WorkSpaceAI
Legacy branch/HEAD: feat/f2-document-task-management @ 730dc75f57a517adc322ec243fed66eaa47825b9
```

Worktree mới là Git linked worktree; không có managed attachment. Không dựa vào cwd mặc định của chat. Xác minh đúng `--show-toplevel`, branch, HEAD, status và diff thực tế trước khi sửa. Tại bàn giao chỉ có hai tài liệu Q00/Q01 mới cùng thay đổi tài liệu `CHANGELOG.md`, `.skills/codebase_map.md`; giữ chúng. Không checkout/reset/stash/clean để làm sạch hộ người dùng. Nếu trạng thái khác, đọc để hiểu và bảo toàn; không ghi nhầm vào legacy hoặc main.

Đọc theo thứ tự: `AGENTS.md`, `.skills/codebase_map.md`, `CHANGELOG.md`, hai tài liệu trong `docs/f2/`. Áp dụng `C:\Users\ADMIN\.codex\RTK.md`: shell commands luôn bắt đầu bằng `rtk`.

## 3. Allowed Files / Do Not Touch

Được tạo:

- `backend/core/f2_study_schemas.py`
- `tests/test_f2_study_schemas.py`

Được cập nhật tài liệu khi hoàn tất Q01 theo AGENTS.md:

- `.skills/codebase_map.md`: model/fields/public helper thực sự đã triển khai.
- `CHANGELOG.md`: Q01 added/changed, kết quả và giới hạn thực tế.
- Một ghi nhận kết quả Q01 trong `docs/f2/` nếu cần cho bàn giao.

Không sửa `backend/core/schemas.py`, F1/F3 algorithms/services/providers/routes/tests, `backend/main.py`, parser, workspace repository, frontend, package/requirements/lockfiles hoặc database schema. Không tạo `__init__` side-effect/re-export để tự tích hợp runtime. Không đọc/ghi/copy `f2_schemas.py` và `f2_sqlite_repository.py` legacy vào module mới; chúng chứa TaskCandidate/ManagedTask không liên quan.

Không commit/push/merge/reset/clean hoặc xóa code cũ. Không tự tạo PR hoặc gửi thông điệp ra ngoài trong Q01. Chỉ dùng subagent khi có yêu cầu rõ ràng mới; packet này không yêu cầu delegation.

## 4. Input / Output

Input thiết kế: dạng `DocumentChunk` hiện có từ `backend/core/schemas.py`, quyết định MVP và FR2.01–05. Chỉ đọc các interface cần thiết; không tái audit toàn repo.

Output: các Pydantic v2 contracts độc lập, unit tests có negative cases và JSON round-trip, diff và logs. Import module không gọi network, LLM, DB, file I/O hoặc F1/F3 services. `backend/core/` được dùng Pydantic; `backend/algorithms/` tiếp tục 100% stdlib và không cần thay đổi trong Q01.

## 5. Bộ model và invariants cần hiện thực

Tên model giữ theo kế hoạch. Tên field cụ thể dưới đây là thiết kế kỹ thuật đề xuất để implementer hoàn thiện nhất quán, không phải public API đã tồn tại.

| Model | Trách nhiệm / dữ liệu tối thiểu |
| --- | --- |
| `SourceRef` | doc ID, doc version/hash, page, chunk ID, evidence quote và line/span locator. Giữ nguyên nguồn; không tự tạo provenance thiếu. |
| `StudySourceSelection` | Danh sách document IDs không rỗng, format Quiz/Flashcards, requested count mặc định 10. Workspace scope/context nếu cần phải tách khỏi tuyên bố authorization. |
| `QuizQuestion` | ID, question, options có ID ổn định, đúng một correct option ID, explanation và ít nhất một source reference. |
| `QuizSet` | ID, source selection/snapshot, danh sách câu hỏi; nhất quán ID và source scope. |
| `Flashcard` | ID, front không rỗng, back ngắn gọn không rỗng, source references. |
| `FlashcardDeck` | ID, source selection/snapshot và danh sách cards; nhất quán ID và source scope. |

Các helper enums/models cho format/options/validation status được phép trong cùng file nếu cần. Không thêm repository, service, grading engine hoặc frontend DTO trong Q01.

Ràng buộc cấu trúc:

1. Không chấp nhận chuỗi bắt buộc chỉ có whitespace. Chọn chính sách chuẩn hóa rõ ràng cho prose/IDs; giữ nguyên evidence quote gốc và không thay đổi ý nghĩa nguồn.
2. Single-choice: ít nhất hai options khác nhau, option IDs duy nhất, text không rỗng; phát hiện duplicate text sau strip/casefold. Answer key là **một ID duy nhất** thuộc tập options. Reject key thiếu/không tồn tại và shape nhiều đáp án; không dùng bool/coercion để âm thầm nhận dữ liệu sai kiểu.
3. Mặc định count = 10; explicit count là số nguyên dương. Reject 0, âm, bool và số thập phân không nguyên. Không đặt giới hạn max tùy tiện như một yêu cầu đã được nhóm duyệt. Số option cố định 4 vẫn là đề xuất của Q03; chưa khóa 4 trong Q01.
4. Selected doc IDs không rỗng và không chứa ID trống. Reject duplicate/normalize có chủ đích rồi document/test chính sách; không dùng filename thay exact doc ID.
5. SourceRef yêu cầu metadata theo schema đã công bố, page/line hợp lệ và end >= start. Hash/version là dữ liệu provenance, không phải bằng chứng đã đối chiếu live source. Test sai locator/missing metadata. Nếu cần strict SHA-256 syntax, document vì nguồn demo cũ có thể để hash trống; không bù hash giả để hợp thức hóa demo.
6. Question/card source phải thuộc selection của set/deck theo exact document identity; ID item không trùng trong container. Các ràng buộc này không xác minh quyền truy cập workspace ở runtime.
7. Không ép container luôn đủ 10 mục. Count là yêu cầu; service Q02–Q05 xử lý insufficiency/partial result và thông báo phù hợp. Nếu container đại diện kết quả thành công thì không được chứa danh sách rỗng; phản hồi lỗi/no-content thuộc task service/API sau.
8. Pydantic validation và SourceRef hợp lệ **không** có nghĩa đáp án/citation đã VERIFIED. Không nhận cờ provider/client `verified=true` như sự thật đã kiểm chứng. Hạn chế model Q01 ở trạng thái unverified hoặc giữ kết quả kiểm chứng trong kiểu nội bộ cho task Q05; không hứa chống giả mạo bằng enum schema.
9. Giữ answer key trong model nội bộ phục vụ generation/grade. DTO learner không lộ key trước submit/reveal sẽ được thiết kế khi tích hợp Q06/Q08; không serialize nguyên internal model ra API và gọi đó là hoàn thiện practice flow.
10. JSON encode/decode bảo toàn nội dung Unicode, key/source/span/format/count; test round-trip lồng trong set/deck.

Chưa cần helper chuyển `DocumentChunk` ở Q01. Nếu thêm, nó chỉ copy dữ liệu và validate shape, không authenticate/verify chunk; không làm vỡ nguyên tắc import không side effects.

## 6. Acceptance và kiểm thử có ý nghĩa

| AC | Bằng chứng tối thiểu |
| --- | --- |
| AC1 — Default/selection | Quiz/Flashcards hợp lệ, count mặc định 10; reject selection trống, ID trống, format/count sai |
| AC2 — Single answer | Valid MCQ; reject key thiếu/ngoài options/nhiều key, option trống/trùng/ID trùng |
| AC3 — Flashcards | Front/back/source hợp lệ; reject front/back whitespace hoặc source thiếu |
| AC4 — Provenance | Valid SourceRef; reject locator/metadata sai; model hợp lệ vẫn không được xem là verified citation/answer |
| AC5 — Containers | Detect item ID trùng và source ngoài selected scope; không ép đúng 10 items khi nguồn chưa đủ |
| AC6 — Round trip | Unicode nested QuizSet và FlashcardDeck qua JSON round-trip |
| AC7 — Isolation/regression | Module độc lập, không runtime side effects; full verify giữ F1/F3 tests PASS; diff giới hạn allowed files |

Test negative behavior của contracts, không viết test chỉ mirror mọi field/default hoặc test parser/generator chưa có. Dùng fixtures nguồn nhỏ, không PDF/LLM thật và không gửi email.

Baseline Q00: CPython 3.12.14, Pydantic 2.14.2, pytest 9.2.0; `verify.py` exit 0, **30 passed**, AST **40 files**, R2 **PASS**, một warning Starlette/TestClient deprecation. Frontend build PASS. Các số 74/84/104 từ Task Management không phải baseline study.

Lệnh PowerShell (chạy trong đúng worktree):

```powershell
rtk proxy git --no-optional-locks rev-parse --show-toplevel
rtk proxy git --no-optional-locks branch --show-current
rtk proxy git --no-optional-locks status --short --branch
$env:LLM_PROVIDER = 'mock'
$env:EMAIL_DISPATCH_MODE = 'local_mock'
$f2Python = 'C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe'
rtk proxy $f2Python -m pytest tests/test_f2_study_schemas.py -v
rtk proxy $f2Python verify.py
rtk proxy git diff --check
rtk proxy git diff --cached --check
```

Nếu sandbox chặn TestClient loopback, dùng execution approval có giải thích cho đúng lệnh verification; không sửa app/tests để né lỗi môi trường. Không cần cài lại frontend hoặc chạy lại build vì Q01 không thay frontend; chỉ mở rộng kiểm tra nếu diff/lỗi mới yêu cầu.

## 7. Rủi ro và phần để task sau

- Shared repository dùng alias theo doc_name và state toàn cục in-memory; Q02 phải exact-filter và kiểm scope trong F2 adapter, không sửa F1. Schema workspace ID không thay authorization.
- Source quote match không bảo đảm correct answer về nghĩa; Q05 cần phân biệt grounding và answer support, xử lý thiếu/mơ hồ.
- React hiện là preview, Streamlit là hướng tích hợp MVP trong kế hoạch Q08. Q01 không lựa chọn lại/rewrite UI.
- SQLite Q07 triển khai sau MVP Q08, không import task SQLite repository.
- Chưa có SSOT v1.2 đã xác minh; không suy diễn requirement từ bản Task Management cũ. Chỉ yêu cầu thêm tài liệu nếu một quyết định thực sự phụ thuộc vào nó.

## 8. Bàn giao khi kết thúc Q01

Trả branch/base/current SHA, status, danh sách file và diff (kể cả untracked source mới), model/public signatures đã triển khai, AC → tests, lệnh/raw logs/exit codes cho focused tests + verify, findings và giới hạn. Cập nhật changelog/map. Không dùng schema test PASS để tuyên bố answer/citation semantics đã được xác minh hoặc luồng F2 đã chạy end-to-end.

Task tiếp theo là Q02 Source Selection & Content Extraction; giữ Q03/Q04/Q05/Q06/Q08/Q09 đúng phạm vi kế hoạch và Q07 SQLite sau MVP. Chờ chỉ dẫn task tiếp theo; không tự mở rộng từ Q01 sang generator/API/UI.
