# F2-Q02 — Source Selection & Content Extraction

Trạng thái: **DONE trong phạm vi Q02**. Ngày 2026-11-11, Asia/Bangkok. Người dùng sẽ kiểm thử thủ công toàn bộ sau khi hoàn tất chuỗi F2-Q0x; kiểm thử tự động vẫn thực hiện theo từng task.

## 1. Phạm vi và Git

Q02 hiện thực **FR2.01** (chỉ các nguồn đã chọn trong phạm vi được phép) và **FR2.02** (nhận diện nội dung sử dụng được, bảo toàn nguồn, thông báo khi thiếu nội dung). Không tạo câu hỏi/flashcard hoặc sửa F1/F3.

```text
Branch: feat/f2-quiz-flashcards
HEAD/base: da40118de0adbda33c55200d30bd9915019d2619
Worktree: C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards
Legacy: D:\Projects\WorkSpaceAI
Legacy branch/HEAD: feat/f2-document-task-management @ 730dc75f57a517adc322ec243fed66eaa47825b9
```

Tệp mới của Q02:

- `backend/services/f2_source_service.py`
- `backend/algorithms/f2_source_extraction.py`
- `tests/test_f2_source_service.py`
- Báo cáo này.

Đã cập nhật `.skills/codebase_map.md`, `CHANGELOG.md`. Bổ sung tệp algorithm ngoài hai tệp service/test đã nêu trong handoff để tuân thủ ranh giới repo: thuật toán nhận diện tất định chỉ dùng stdlib, không đưa Pydantic hoặc I/O vào `backend/algorithms/`.

Giữ nguyên code, tests và báo cáo Q01; shared schemas, parser/repository, F1/F3, frontend, dependencies và database không sửa. Không commit, push, merge, reset, clean, stash hoặc thay staging. Code/docs mới tiếp tục unstaged/untracked cho review.

## 2. Hành vi đã có

### Đầu vào có phạm vi rõ ràng

`F2SourceService(repository).prepare_sources(selection, *, context)` nhận `StudySourceSelection` của Q01 và `SourceAccessContext(workspace_id, allowed_doc_ids)` do backend cấp. Repository bắt buộc được inject, không fallback về singleton hoặc mọi tài liệu đang tick chọn.

Danh sách được phép là frozenset exact doc IDs; nguồn không được phép bị từ chối **trước khi đọc repository**. Context không xác thực người dùng; khi tích hợp Q08, backend phải tự giải quyết quyền workspace và không lấy allowed_doc_ids từ request body.

### Chọn đúng tài liệu và snapshot

- Đọc stored `repository.documents` theo exact ID. Không dùng `list_documents()` vì method này có thể tự dựng metadata từ orphan chunks.
- Revalidate/copy metadata và chunk models; đối chiếu doc ID/name, version/hash, chunk count và locator. Hash/version phải tồn tại thật trong repository; không tự bù hash.
- Shared `get_document_chunks` nhận cả doc-name/case aliases. F2 lọc lại exact chunk.doc_id trước khi kiểm tra/sử dụng nội dung, tránh trộn các phiên bản cùng tên file.
- Kiểm số dòng text tương ứng span và phát hiện overlap có nội dung mâu thuẫn. Cùng một trích đoạn/vị trí ở overlap chỉ trả một lần; thứ tự ổn định theo selection, page/line/chunk.
- Đọc lại metadata trước khi trả để bắt version/hash/metadata thay đổi hoặc nguồn bị xóa giữa chừng. Không coi UI `is_selected` là selection của request và không tuyên bố đây là transaction atomic.

Metadata sai/thiếu/mâu thuẫn tạo `SourcePreparationError` có code và hướng phục hồi. Tài liệu có text không dùng được tạo content issue rõ ràng, cho phép trả phần nội dung dùng được từ các nguồn còn lại.

### Nhận diện nội dung có tính trích xuất

`extract_study_spans(text)` là hàm thuần stdlib, trả tuple `ExtractedStudySpan(kind, text, start_line, end_line)`:

- `definition`: term–definition qua dấu hai chấm, dash hoặc cue như is/means/là.
- `fact`: đoạn văn có dấu câu hoặc thông tin số cùng từ ngữ, loại bỏ các dãy số đơn thuần.
- `example`: ví dụ có cue tiếng Anh/Việt.
- `procedure`: nhóm tối thiểu hai numbered steps/Bước/Step.

Các dòng soft-wrap được giữ cùng đơn vị; blank lines, heading/decorative/page/TOC noise thông dụng phân tách hoặc bị loại. Quote là substring nguyên văn, giữ Unicode, khoảng trắng và CRLF. Line span tương đối được chuyển sang page/line thật trong chunk để tạo `SourceRef` Q01; không viết lại PDF parser.

Mỗi `StudySourcePassage` giữ kind và SourceRef bất biến; `.text` là evidence_quote. SourceRef tiếp tục **UNVERIFIED**. Phân loại mẫu văn bản không đồng nghĩa đã xác minh sự thật hoặc đáp án.

### Kết quả và phục hồi

| Status của PreparedStudySources | Ý nghĩa |
| --- | --- |
| READY | Có trích đoạn sử dụng được, không có content issue; chưa bảo đảm đủ 10 câu/card đúng |
| PARTIAL | Có nội dung sử dụng được nhưng một phần nguồn/đoạn bị bỏ qua, có cảnh báo |
| INSUFFICIENT_CONTENT | Không có trích đoạn sử dụng được; hướng dẫn thêm/chọn nguồn khác có text layer |

Kết quả giữ workspace ID, selection/count/format gốc và tuple passages/issues. Không dùng số passages làm số câu hỏi có thể tạo; việc đáp ứng count=10 và thông báo số mục thực tế thuộc generators/validation sau.

Issue codes: `NO_USABLE_CONTENT`, `SUSPICIOUS_SOURCE_CONTENT`. Error codes: `INVALID_SELECTION`, `INVALID_CONTEXT`, `FORBIDDEN_SOURCE`, `SOURCE_NOT_FOUND`, `INVALID_PROVENANCE`, `SOURCE_INCONSISTENT`, `SOURCE_READ_FAILED`, `SOURCE_CHANGED`.

Các pattern injection đã biết được bỏ qua qua guardrail hiện có; service không gọi LLM/network/email/DB. Đây là lọc heuristic, không phải tuyên bố chặn mọi prompt injection. Q03/Q04 vẫn phải xem toàn bộ nguồn là dữ liệu không tin cậy và đóng khung prompt đúng quy tắc repo.

## 3. Acceptance → tests

| Mục tiêu | Bằng chứng trong tests/test_f2_source_service.py |
| --- | --- |
| Một/nhiều nguồn, cả hai format | Multi-document preparation giữ count mặc định 10 và snapshot độc lập |
| Exact ID và scope | Denied request không đọc repo; unknown/case/name aliases bị từ chối; orphan metadata fallback không được dùng; foreign alias chunks bị loại |
| Không trộn version | Test với DocumentService thật ingest hai phiên bản cùng tên; chỉ lấy đúng doc/version/hash đã chọn |
| Nội dung thiếu | Empty/whitespace/header-only/scanned-with-no-chunks/TOC/numeric noise → insufficient; good+empty source → partial |
| Mẫu học liệu | English/Vietnamese definitions, examples, procedures; CRLF/Unicode quote nguyên văn và line offsets chính xác |
| Provenance | Thiếu/sai hash/version/metadata/count/locator, duplicate chunk ID, conflict ở overlap đều bị chặn |
| Vòng đời nguồn | Version thay đổi/xóa khi đọc → SOURCE_CHANGED; thay is_selected không thay request; repository read failure có typed error |
| Snapshot | Sửa repository sau khi trả không làm đổi passage; kết quả frozen; chuẩn bị không sửa repository |
| Tài liệu dài và page gaps | DocumentService thật ingest 30 concepts qua nhiều chunks, trả 30 vị trí không trùng; blank pages bị parser bỏ qua vẫn giữ physical page number |
| R2/R7 | Subprocess import/execute thuật toán không tải third-party hoặc phát sinh external I/O; known instructions bị bỏ qua, không dispatch network/email |

## 4. Kết quả kiểm thử

| Kiểm tra | Kết quả thực tế |
| --- | --- |
| Focused pytest Q02 | **55 passed**, exit 0; 1.00s theo pytest |
| Full python verify.py | **166 passed**, exit 0; 3.51s theo pytest |
| AST qua verify.py | **45 Python files PASS** |
| R2 gate và test riêng thuật toán mới | **PASS** |
| F1/F3/pipeline regression | Toàn bộ 30 baseline tests PASS |
| Q01 regression | Toàn bộ 81 contracts tests PASS |
| Scope/diff audit | PASS; chỉ 4 tệp Q02 mới và map/changelog; Q01 source/tests/report không đổi |
| Legacy preservation | PASS; branch/HEAD/index/status/staged+unstaged diff và 511 tracked/untracked file hashes khớp snapshot Q00 |

Một warning Starlette/TestClient deprecation đã có từ baseline. Không cập nhật dependency hoặc sửa F1/F3 để xử lý warning. Full verify chạy với mock LLM/email, ngoài sandbox cho loopback TestClient. Không gửi email hoặc gọi LLM thật. Không chạy lại frontend build vì không thay frontend/dependencies.

Raw logs, command/cwd/environment và exit codes:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q02-2026-11-11\evidence\baseline\focused.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q02-2026-11-11\evidence\baseline\focused.json
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q02-2026-11-11\evidence\baseline\verify.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q02-2026-11-11\evidence\baseline\verify.json
```

Diff riêng Q02 (kể cả untracked), status, hashes và preservation audit ở cùng `evidence/`. Đã tự review, chưa có independent review bởi người/agent khác. Người dùng chưa cần chạy kiểm thử thủ công ở Q02.

## 5. Giới hạn thực tế

- Nhận diện là heuristic trích xuất, không hiểu đầy đủ mọi bảng/công thức hoặc mọi cách diễn đạt. Phân loại FACT không chứng minh nội dung đúng; kiểm chứng nghĩa/answer key thuộc Q05, đánh giá corpus thật thuộc Q09.
- Context là trusted-caller contract, chưa có auth/resolver workspace ở runtime. Không coi client workspace ID là quyền truy cập. Shared services package có initializer sẵn có; Q02 không sửa initializer hoặc đăng ký singleton mới.
- Hash được đối chiếu giữa stored metadata/chunks, không đọc lại file bytes hoặc chứng minh SHA-256 từ text đã trích. Hash/version không còn phù hợp phải được xử lý tại source truth và Q05 trước khi phát hành học liệu.
- Metadata recheck chỉ phát hiện các thay đổi quan sát được trong lời gọi; không khóa repository, không bảo đảm nguồn không thay đổi sau khi trả. Snapshot được giữ nguyên cho bước sau.
- Provenance cũ không khớp line count hoặc thiếu stored metadata bị từ chối, không tự sửa parser/repository F1. Với trang rỗng bị parser bỏ qua, page_count là số trang trích được, nên không dùng nó làm upper bound của physical page number.
- Nguồn chỉ có ảnh không được OCR ở Q02. Test integration dùng TXT qua parser/chunker thật; không phải benchmark PDF/LLM thực hoặc UI E2E.
- Chưa có generators, grading, study API/UI hay SQLite. Không dùng kết quả tests để tuyên bố hoàn thành F2 end-to-end.

## 6. Bàn giao Q03 — Quiz Generation

Q03 chưa thực hiện trong lần này. Tiếp tục ở cùng worktree/branch và giữ mọi thay đổi Q00–Q02 chưa commit.

- Goal/FR: sinh single-choice Quiz từ PreparedStudySources, map FR2.03; requested_count mặc định 10 từ selection.
- Theo kế hoạch: `backend/services/f2_quiz_service.py`, `tests/test_f2_quiz_generation.py`. Có thể thêm study provider/prompt module riêng nếu cần để giữ nguyên provider QA/email; ghi rõ mọi tệp bổ sung và giữ layered boundaries.
- Input: kết quả F2SourceService, không nhận client chunks tùy ý; insufficient sources không gọi generator. PARTIAL phải giữ cảnh báo nguồn cho caller.
- Output: QuizSet/QuizQuestion/QuizOption của Q01, provenance nằm trong snapshot Q02. Không để LLM tự đổi selected doc IDs/version/hash hoặc tự gắn VERIFIED.
- Bắt đầu bằng adapter deterministic/mock để kiểm thử, sau đó adapter LLM rõ timeout/structured output khi phù hợp. Không dùng F1 answer_question để thay quiz generator.
- Validate key nằm trong options, text/options không trùng, source references đúng snapshot và thiếu nội dung không bị bịa để đủ 10. Số options không được nhóm khóa là 4; contracts hiện yêu cầu >=2, một key.
- Dữ liệu nguồn luôn là untrusted data khi tạo prompt; escape/frame phù hợp. Provider timeout/invalid JSON/unsupported items phải có error hoặc abstention/partial path rõ.
- Giữ structural validation và semantic grounding riêng; Q05 mới xử lý answer support, không ghi nhãn VERIFIED dựa vào JSON hợp lệ.
- Tests: success/default count, key/options/source sai, source thiếu, malformed/timeout provider, dedup và snapshot/prompt boundaries; full verify giữ 166 tests hiện tại PASS.
- Q04 Flashcards, Q05 validation, Q06 practice, Q08 integration, Q09 evaluation tiếp theo; Q07 SQLite sau MVP. Kiểm thử thủ công tổng thể của người dùng để cuối chuỗi như đã yêu cầu.
