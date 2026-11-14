# F2-Q01 — Data Contracts

Trạng thái: **DONE — phạm vi contracts và tests**. Ngày 2026-11-11, Asia/Bangkok.

## 1. Kết quả và Git

Đã hiện thực contracts độc lập cho F2 Document-Based Quiz & Flashcard Generation theo [packet Q01](F2-Q01_TASK_CONTEXT_PACKET.md). Mapping chính: FR2.01, FR2.03, FR2.04; provenance hỗ trợ FR2.02/FR2.05. Giữ Quiz một đáp án đúng, mặc định yêu cầu 10 mục và SQLite sau MVP.

```text
Branch: feat/f2-quiz-flashcards
Base/HEAD: da40118de0adbda33c55200d30bd9915019d2619
Worktree: C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards
Legacy: D:\Projects\WorkSpaceAI
Legacy branch/HEAD: feat/f2-document-task-management @ 730dc75f57a517adc322ec243fed66eaa47825b9
```

HEAD/base không đổi. Không có commit, push, merge, reset, clean, stash, PR hoặc thay đổi staging. Giữ các tài liệu Q00 đang có. F1/F3, source parser/repository, frontend, requirements/lockfiles và database không bị sửa.

Tệp của Q01:

- Mới: `backend/core/f2_study_schemas.py`, `tests/test_f2_study_schemas.py`, báo cáo này.
- Cập nhật: `.skills/codebase_map.md`, `CHANGELOG.md`.
- Hai tài liệu Q00/Q01 packet có từ Q00 được giữ nguyên như snapshot bàn giao; trạng thái READY trong packet là trạng thái lúc tạo packet, không thay thế báo cáo kết quả này.

Code/docs mới hiện unstaged/untracked để review. Toàn bộ nội dung diff, kể cả source untracked và phần docs riêng Q01 so với tài liệu Q00, được lưu ngoài repo trong `output/f2-q01-2026-11-11/evidence/q01-only.patch` của thư mục workspace cha.

## 2. Contracts thực sự đã triển khai

Tất cả nằm trong `backend/core/f2_study_schemas.py`. Không thêm public function/helper chuyển DocumentChunk; không đăng ký vào runtime.

| Model | Fields |
| --- | --- |
| `StudyFormat` | `QUIZ='quiz'`, `FLASHCARDS='flashcards'` |
| `SourceRef` | doc_id, doc_version, doc_hash, page_number, chunk_id, start_line, end_line, evidence_quote, verification_status |
| `StudySourceSelection` | selected_doc_ids, study_format, requested_count=10 |
| `QuizOption` | option_id, text |
| `QuizQuestion` | question_id, question, options, correct_option_id, explanation, source_refs |
| `QuizSet` | quiz_set_id, selection, questions |
| `Flashcard` | card_id, front, back, source_refs |
| `FlashcardDeck` | deck_id, selection, cards |

Các quyết định kỹ thuật:

- **Cấu trúc bất biến:** models `frozen=True`, collections nhận list/tuple có thứ tự và lưu tuple; forbid extra fields; revalidate nested instances khi đi qua validation boundary. Input dict/list bên ngoài không làm đổi snapshot sau khi tạo model.
- **Định danh chính xác:** không strip/casefold doc/option/item IDs; reject surrounding whitespace và duplicate ID. Hai IDs khác case được xem là hai IDs khác nhau; không resolve tên file hoặc quyền workspace trong schema.
- **Nội dung:** reject chuỗi bắt buộc rỗng/whitespace; giữ nguyên prose và evidence quote, bao gồm Unicode, newline và khoảng trắng gốc.
- **Count/locator:** strict integer dương, không nhận bool, numeric strings hoặc float; mặc định count=10; không áp maximum mới.
- **MCQ:** >=2 options, option IDs duy nhất; text không trùng sau strip/casefold; một correct_option_id bắt buộc thuộc options; explanation/source refs không rỗng. Không khóa số option là 4 vì chưa có quyết định đó.
- **Provenance:** page và line bắt đầu từ 1, span inclusive và end >= start; doc/hash/version/chunk/quote bắt buộc. Hash yêu cầu 64 ký tự hex thường, phù hợp SHA-256 hexdigest; đây chỉ là kiểm tra cú pháp. Nguồn demo có hash rỗng phải được source layer giải quyết, không tạo hash giả.
- **Containers:** không rỗng; format đúng loại; item IDs duy nhất; mọi ref phải thuộc exact selected_doc_ids; mỗi doc_id có một version/hash snapshot nhất quán trong kết quả. Source refs chính là snapshot gắn với từng item; không khẳng định đã đối chiếu live documents.
- **Kết quả ngắn hơn yêu cầu:** hợp lệ, ví dụ một câu/card trong request mặc định 10. Service sau này phải xử lý/thông báo thiếu nội dung; schema không tự sinh thêm mục.
- **Không tự VERIFIED:** SourceRef chỉ cho `UNVERIFIED`; cờ `verified` hoặc trạng thái VERIFIED từ provider bị reject. Kiểm tra cấu trúc không chứng minh câu trả lời đúng về nghĩa.

## 3. Acceptance → bằng chứng tests

Các test nằm trong `tests/test_f2_study_schemas.py`; tổng 81 ca sau parameterization.

| AC trong packet | Test chính / hành vi đã kiểm tra |
| --- | --- |
| AC1 selection/default | `test_selection_defaults_to_ten_and_preserves_exact_multi_source_ids`; invalid/coerced counts; source scope/format sai |
| AC2 single answer | `test_question_rejects_invalid_key_options_or_content`; thiếu key/source; 3 options hợp lệ, không khóa 4 |
| AC3 flashcards | `test_flashcard_rejects_missing_content_or_provenance`; front/back/source sai |
| AC4 provenance | malformed/missing metadata, quote round-trip, provider không tự label VERIFIED |
| AC5 containers | empty/duplicate item IDs/wrong format/foreign source/case alias/version conflict/hash conflict; multi-document snapshot |
| AC6 JSON | nested QuizSet và FlashcardDeck round-trip giữ nội dung Unicode, source/span/key/count |
| AC7 isolation | mutable input không sửa được snapshot; nested mutation bị chặn; unsafe copied instances bị revalidate; import không thêm services/repositories/providers/API hoặc gây file write/socket/DB/subprocess |

## 4. Kiểm thử thực tế

| Lệnh/check | Kết quả |
| --- | --- |
| `python -m pytest tests/test_f2_study_schemas.py -v` | Exit 0; **81 passed**, 0.86s theo pytest |
| `python verify.py` | Exit 0; **111 passed**, 1 warning, 3.52s theo pytest |
| AST qua verify.py | **42 Python files PASS** |
| R2 stdlib purity qua verify.py | **PASS** |
| Git diff/check và scope audit | PASS; chỉ tệp cho phép của Q01 + tài liệu Q00 có sẵn; không staged changes |
| Legacy preservation | PASS so với snapshot Q00: branch/HEAD/index/status/diffs và SHA-256 của 511 tracked/untracked files giữ nguyên |

111 = 81 Q01 + 30 baseline F1/F3/pipeline. Một warning Starlette/TestClient deprecation đã có ở Q00. Không sửa dependency để xử lý warning trong task contracts.

Runtime tái sử dụng: CPython 3.12.14, Pydantic 2.14.2, pytest 9.2.0. LLM_PROVIDER=mock, EMAIL_DISPATCH_MODE=local_mock; không gọi LLM thật/gửi email. Full verify chạy ngoài sandbox vì TestClient cần loopback. Không chạy lại frontend build do không thay frontend/dependencies; build PASS của Q00 vẫn là baseline tương ứng.

Logs và command/exit-code metadata:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q01-2026-11-11\evidence\baseline\focused.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q01-2026-11-11\evidence\baseline\focused.json
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q01-2026-11-11\evidence\baseline\verify.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q01-2026-11-11\evidence\baseline\verify.json
```

Git/legacy audit và full diff nằm trong cùng `evidence/`. Đã tự review thay đổi theo packet; chưa có independent review bởi người/agent khác.

## 5. Giới hạn và phần ngoài Q01

- Chưa có source service, generator, grounding/answer semantic verifier, grading, study API/UI hoặc SQLite. Không dùng 111 tests để tuyên bố F2 end-to-end đã hoạt động.
- `SourceRef` không authenticate doc ID, hash/version hoặc quyền workspace; Q02/Q05 phải đối chiếu nguồn thật.
- Internal `QuizQuestion` chứa answer key. Q06/Q08 phải tạo learner DTO/projection phù hợp, không trả nguyên internal model trước submit/reveal.
- Pydantic `model_construct`/`model_copy(update=...)` cố ý có thể bỏ qua validation; chỉ dùng cho dữ liệu trusted. Nested instances được revalidate khi vào container nhưng code tương lai vẫn phải đi qua `model_validate`/constructor ở trust boundaries.
- `backend.core.__init__` đang import shared config/schemas và có hành vi load config có sẵn. Q01 không sửa initializer. Test import cô lập hành vi mới của study module sau khi core package đã khởi tạo, không tuyên bố cả package chỉ import Pydantic hoặc không hề đọc config.

## 6. Bàn giao Q02 — Source Selection & Content Extraction

Task tiếp theo là **Q02**, chưa tự triển khai trong lần này.

- Goal: dùng selected document IDs để lấy/check nội dung thật từ Document Layer hiện tại, bảo toàn provenance và phát hiện thiếu nội dung theo FR2.01/FR2.02.
- Tệp theo kế hoạch: `backend/services/f2_source_service.py`, `tests/test_f2_source_service.py`; cập nhật map/changelog/report khi hoàn thành. Không sửa F1/F3/shared repository/parser hoặc frontend.
- Inputs: StudySourceSelection + repository/context phía backend. Không coi client-supplied chunks hoặc workspace ID là authorization đã được xác minh.
- Kiểm scope bằng exact doc ID và metadata/version/hash; shared get_document_chunks/search hỗ trợ doc_name alias nên phải lọc rõ ở F2 adapter. Không fallback sang mọi nguồn khi selection rỗng/không hợp lệ.
- Output: các đoạn/khái niệm/sự kiện/định nghĩa/quy trình dùng được, kèm SourceRef đầy đủ. Không đủ nội dung hoặc thiếu metadata thật thì trả lý do rõ để thêm/chọn nguồn khác; không bịa hash/version hoặc kéo tài liệu ngoài selection.
- Tests: một/nhiều nguồn, ID không tồn tại, alias/case không đúng, nguồn ngoài scope, nguồn rỗng/scanned/unusable, provenance/version/hash thiếu hoặc mâu thuẫn, đủ nội dung; rồi chạy full verify giữ 111 tests hiện tại PASS.
- Q03/Q04 generator và Q05 semantic validation vẫn ở task sau. SQLite Q07 tiếp tục sau luồng MVP/Q08.
