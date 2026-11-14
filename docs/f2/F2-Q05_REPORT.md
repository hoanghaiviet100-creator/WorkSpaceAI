# WorkspaceAI F2-Q05 — Content Validation & Grounding

Ngày thực hiện: 2026-11-12. Phạm vi: kiểm tra học liệu nội bộ cho FR2.02–FR2.04, tiếp nối Q01 contracts, Q02 sources, Q03 Quiz và Q04 Flashcards. Đây là validation service riêng; chưa nối vào runtime/API/UI hoặc practice flow.

## 1. Branch/worktree và phạm vi thay đổi

```text
Branch: feat/f2-quiz-flashcards
Worktree: C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards
HEAD / origin/main: da40118de0adbda33c55200d30bd9915019d2619
New commits: 0
Legacy: D:\Projects\WorkSpaceAI, branch feat/f2-document-task-management
```

Tệp mới Q05:

| Tệp | Trách nhiệm |
| --- | --- |
| `backend/core/f2_validation_schemas.py` | Internal immutable validation receipt và per-item/source/support statuses |
| `backend/algorithms/f2_study_validation.py` | Pure-stdlib extractive support checks, không I/O |
| `backend/services/f2_study_validation_service.py` | Structural/scope/current-source validation và điều phối support checks |
| `tests/test_f2_study_validation.py` | 78 automated cases |
| `docs/f2/F2-Q05_REPORT.md` | Báo cáo và Task Context Packet Q06 |

Chỉ sửa thêm `.skills/codebase_map.md` và `CHANGELOG.md`. Không sửa Q01–Q04 source/tests/reports, shared F1/F3, frontend, dependencies hoặc báo cáo nhóm. Các file F2 mới vẫn chưa được Git track; không stage/commit/push/merge/reset/clean/stash/xóa code cũ.

Final audit so trạng thái/diffs/index/branch/HEAD và 511 file hashes tracked/untracked không ignored của legacy với snapshot Q00. Scope check và preservation check PASS; không tuyên bố đã kiểm tra mọi ignored file. Evidence nằm ngoài checkout, đường dẫn ở mục 5.

## 2. Cổng kiểm chứng đã triển khai

Public service:

```python
F2StudyValidationService(repository).validate_quiz(
    quiz: QuizSet, *, workspace_id: str, context: SourceAccessContext
) -> StudyValidationResult

F2StudyValidationService(repository).validate_flashcards(
    deck: FlashcardDeck, *, workspace_id: str, context: SourceAccessContext
) -> StudyValidationResult

study_resource_digest(resource: QuizSet | FlashcardDeck) -> str
```

Caller phải cấp repository và access context đã được backend giải quyết. Workspace ID của request không thay thế authorization. Context bị thiếu/sai hoặc workspace mismatch gây `StudyValidationError` trước đọc nguồn. Context được dựng lại để kiểm tra kể cả frozen dataclass bị sửa qua đường bypass. Chưa có auth/workspace resolver mới.

Các lớp kiểm tra độc lập:

1. **Structure**: revalidate toàn bộ Q01 resource và nested models, kể cả unsafe `model_copy(update=...)`. Extra root `verified`, SourceRef giả VERIFIED, missing key/invalid option/foreign ref ngoài selection hoặc locator/hash malformed bị từ chối. Không đọc repository khi cấu trúc sai.
2. **Current source**: gọi lại Q02 `prepare_sources` trên selection hiện tại. Q02 từ chối denied IDs trước repository access và dùng exact stored metadata/chunks, không dựa tên file alias. Mỗi SourceRef của item phải là một passage hiện tại khớp đầy đủ doc ID/version/hash/page/chunk/line range/**nguyên văn quote**. Không dùng fuzzy quote matching hoặc chỉ tìm substring ở chỗ khác. Ref stale/không tồn tại làm source FAILED; support chưa được kiểm tra.
3. **Content support**: sau khi source MATCHED, kiểm tra đáp án/nội dung theo quy tắc ở mục 3. Quote match và từ khóa đáp án xuất hiện trong quote không tự tạo proof.
4. **Recheck**: chuẩn bị lại toàn bộ nguồn đã chọn trước return và so digest của Q02 snapshot, kể cả nguồn không được item trích dẫn. Thay đổi quan sát được hoặc lỗi đọc làm toàn bộ receipt không đủ điều kiện release. Đây là hai lần đọc, không phải transaction hay khóa nguồn.

Known prompt-injection patterns của guardrails hiện tại được dùng lại: suspicious source chunks bị Q02 bỏ/cảnh báo; suspicious item text bị REJECTED. Không sửa guardrails chung. Mọi source warning, kể cả nguồn được chọn nhưng không có usable content, ngăn automatic release của toàn bộ resource.

Resource nhập trực tiếp qua Q01 có prompt trùng/conflicting hoặc vượt requested_count cũng cần review. Không tự bỏ item sai để biến một set lỗi thành thành công; kết quả kiểm tra giữ thứ tự và ID mọi item. Resource ít hơn requested_count vẫn có thể được kiểm chứng nếu mọi item được hỗ trợ; caller phải giữ thông báo thiếu count của Q03/Q04, không bù nội dung.

## 3. Quy tắc support và trạng thái

Algorithm nhận các cặp `(source_id, quote)` độc lập với Pydantic/repository. Chỉ chuẩn hóa whitespace; giữ case, punctuation, negation, units và qualifiers trong nội dung. Có thêm kiểm tra case-sensitive body conflicts (ví dụ `mM`/`MM`) mà generation dedup casefold có thể gộp.

| Dạng | Điều kiện automatic support |
| --- | --- |
| Quiz | Mẫu chính xác `Khái niệm nào được mô tả sau đây?` + toàn bộ definition body; key là term của body trong cited source; các options là terms rõ ràng trong nguồn đã chọn; explanation khớp `Theo đoạn nguồn, {term}: {body}` |
| Flashcard | Front đúng `{term} là gì?`; back khớp toàn bộ definition body của term trong cited source |
| Cả hai | Định nghĩa không có literal ambiguity/conflict trên toàn bộ selected evidence; mọi citation có liên quan trực tiếp; không có duplicate options sau chuẩn hóa whitespace |

Wrong Quiz key trên mẫu nhận diện được bị REJECTED kể cả term sai có xuất hiện trong quote thật. Unsupported explanations/backs, shortened answers làm mất qualifier, paraphrases và general question forms trả REVIEW_REQUIRED. Không dùng lexical overlap hay LLM self-judgment để tự xác minh các trường hợp này. Literal identical-definition aliases và same-term different-body sources cần review; không tự chọn một nguồn làm đúng.

Kết quả riêng trong `f2_validation_schemas.py`:

- `StudyValidationIssue(code, message, severity)`.
- `StudyItemValidation(item_id, source_status, support_status, issues)` phân biệt MATCHED/FAILED/NOT_CHECKED và SUPPORTED/REVIEW_REQUIRED/REJECTED/NOT_CHECKED.
- `StudyValidationResult(workspace_id, study_format, resource_id, resource_digest, source_snapshot_digest, method, structure_status, items, issues)`; models frozen, extra-forbidden, nested revalidation.

| Overall status | Ý nghĩa và điều kiện sử dụng |
| --- | --- |
| VERIFIED | Structure hợp lệ, mọi source MATCHED và mọi support SUPPORTED, không issues, có resource/source digests. `release_ready=True` |
| REVIEW_REQUIRED | Chưa chứng minh được support hoặc còn warning/duplicate/count issue. `release_ready=False` |
| REJECTED | Structure/source/key/injection lỗi, hoặc nguồn thay đổi/đọc thất bại. `release_ready=False` |

`method=EXTRACTIVE_DEFINITION_V1`: VERIFIED chỉ chứng minh correspondence với định nghĩa trong nguồn đã chọn theo mẫu này. Không khẳng định tài liệu đúng sự thật bên ngoài, không phải arbitrary semantic entailment. Q01 **SourceRef.verification_status vẫn UNVERIFIED**; không sửa hợp đồng cũ để nhận cờ provider/client VERIFIED.

Resource SHA-256 băm canonical JSON đã revalidate, gồm selection, items, answer key/explanation và references. Source SHA-256 băm workspace/selection cùng Q02 passages/kinds/refs/issues. Không có chữ ký hoặc secret: receipt/digest là binding nội bộ tại thời điểm kiểm tra, **không phải token đáng tin khi client gửi lại**. Không chấp nhận receipt do provider/client dựng làm nguồn xác nhận. Phải đối chiếu đúng resource và kiểm chứng lại khi dùng sau thay đổi; chưa có persistence/locking/expiration flow.

## 4. Acceptance và kết quả kiểm thử

| Nhóm | Bằng chứng trong tests/test_f2_study_validation.py |
| --- | --- |
| Positive source-to-study flow | Q02 → Q03/Q04 → Q05; giữ nguyên SourceRefs UNVERIFIED; real two-document TXT ingestion cho cả hai format |
| Content độc lập citation | Wrong key dù term có trong quote; negated/general question; fabricated/unsupported explanation/back; shortened qualifier, case-sensitive units và invented distractor |
| Source identity/location | Wrong version/hash/page/chunk/span, nonexistent/changed/whitespace-modified quote; foreign selection/ref; stale resource sau consistent repository update |
| Structure/trust | Unsafe nested copies, forged verified flags, wrong resource type, invalid context/workspace, denied source trước reads |
| Freshness/fail closed | Nguồn/chunks thiếu, metadata/chunk mismatch, read errors, thay đổi text/version/delete/read failure trong lần đọc thứ hai |
| Ambiguity/injection | Uncited same-term conflict/identical-definition alias, known injection trong item/source, irrelevant citations, duplicate/conflicting prompts/options, selected source warning |
| Receipts/architecture | JSON round-trip/frozen nested result, digest binding và changed uncited evidence, pure stdlib AST/import isolation, không network/email |

Lệnh thực chạy qua RTK proxy, với Python trong audit venv:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe
```

| Lệnh/check | Kết quả thực tế |
| --- | --- |
| `python -m pytest tests/test_f2_study_validation.py -v` đầu tiên | 70 passed, exit 0; 2.40s theo pytest |
| Cùng lệnh sau bổ sung edge cases, log focused-final | **78 passed**, exit 0; 1.97s theo pytest |
| `python verify.py` | **376 passed, 1 warning**, exit 0; 10.37s theo pytest |
| AST syntax qua verify.py | **60 Python files PASS** |
| R2 stdlib gate + algorithm isolation test | **PASS** |
| Scope/preservation/diff checks | **PASS**, không staged changes hoặc commit mới |

376 = 30 baseline F1/F3/pipeline + 81 Q01 + 55 Q02 + 60 Q03 + 72 Q04 + 78 Q05. Những tests Q01–Q04 không chỉnh sửa và đều được chạy trong full suite. CPython 3.12.14, pytest 9.2.0; LLM_PROVIDER=mock, EMAIL_DISPATCH_MODE=local_mock, CI=true. Full verify dùng quyền chạy ngoài môi trường giới hạn để TestClient có loopback cục bộ.

Một Starlette/TestClient httpx deprecation warning đã có từ baseline vẫn tồn tại; không sửa dependency để xử lý. Không gọi Ollama thật hoặc gửi email. Không build lại frontend vì không sửa frontend/dependencies. Chưa có user/browser E2E; giữ manual test cuối chuỗi F2-Q0x như đã chốt. Đã tự review implementation, không có independent reviewer.

## 5. Evidence và findings còn tồn tại

Command/cwd/environment overrides/exit codes, raw logs, Q05-only review patch, scope status và preservation hashes:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q05-2026-11-12\evidence\
  baseline\focused.log / focused.json
  baseline\focused-final.log / focused-final.json
  baseline\verify.log / verify.json
  before\codebase_map.md / CHANGELOG.md
  q05-only.patch
  final-audit.json
  legacy-preservation.json
  status.txt
  worktrees.txt
```

Giới hạn thực tế:

- Auto verification chỉ hỗ trợ extractive definition templates. Chưa có general semantic verifier hoặc model/corpus accuracy/latency evaluation; LLM paraphrases có thể đúng nhưng vẫn bị giữ review.
- Literal ambiguity checks và các known injection regex không phát hiện mọi semantic contradiction/synonym hoặc mọi prompt injection. Source-relative support không chứng minh tính đúng đắn bên ngoài của tài liệu.
- Source truth là stored metadata/chunks qua Q02; không đọc raw file bytes để tự tính lại doc_hash. Source digest bao phủ prepared passages/issues, không phải toàn bộ raw files hoặc mọi dòng bị extraction bỏ qua.
- Ref phải là exact current Q02 passage. Một trích dẫn tương đương ở overlap chunk khác, subset span hay quote đã normalize vẫn có thể bị từ chối để tránh nới nguồn chứng cứ.
- Hai lần đọc chỉ phát hiện thay đổi quan sát được trong quá trình kiểm tra; không có atomic transaction, chống ABA, lock hoặc bảo đảm freshness sau return. Receipt cần kiểm lại tại thời điểm dùng.
- Service/gate chưa tự được Q03/Q04 gọi và chưa có release/practice API/UI. Chưa tạo review workflow cho người dùng. Full tests PASS không có nghĩa toàn bộ F2 đã chạy end-to-end.
- Auth/workspace resolver, Quiz submit/reveal/grade và Flashcard flip/navigation, SQLite sau MVP, integration và release evaluation vẫn ở các task tiếp theo.

## 6. Task Context Packet — F2-Q06 Practice Interaction

Q06 chưa triển khai trong lần này. Bắt đầu từ cùng branch/worktree trên, giữ mọi thay đổi Q00–Q05 chưa commit. Baseline: **376 tests PASS**, AST 60 files, R2 PASS. Không sửa F1/F3 hoặc legacy Task Management; không commit/push/merge/reset/clean/stash.

Mục tiêu theo FR2.05: nộp câu trả lời Quiz và xem đáp án đúng, hoặc lật Flashcard để xem back. Giữ Quiz single-choice; mặc định requested_count=10 nhưng thực hành trên actual valid item count, không bù items thiếu. SQLite vẫn sau luồng MVP.

Interfaces cần dùng:

- Q01 `QuizSet`, `QuizQuestion`, `FlashcardDeck`, `Flashcard`; các Quiz models nội bộ có answer key và explanation.
- Q03 `QuizGenerationResult` và Q04 `FlashcardGenerationResult`: phân biệt complete/partial/insufficient/error, giữ thông báo count/source issues.
- Q05 `F2StudyValidationService.validate_quiz/validate_flashcards` với trusted backend context; chỉ tiếp tục practice cho resource đủ điều kiện. Bind đúng `resource_digest`, kiểm lại nguồn ở thời điểm dùng; không nhận client receipt/status làm proof.
- Tạo learner projection riêng cho Quiz trước submit (không lộ correct_option_id/explanation) và Flashcard trước flip (không lộ back). Không serialize thẳng internal resource ra learner API. Backend giữ answer key/source snapshot để xử lý reveal/grade.

Phạm vi tiếp theo: contracts và service interaction/submit/reveal/flip theo kế hoạch Q06; tách state/algorithms thuần khỏi orchestration, chọn in-memory khi cần cho MVP. API/UI tích hợp ở Q08, persistence Q07 sau MVP; không tự mở rộng sang spaced repetition/review dashboard.

Tests Q06 cần xác minh valid/invalid question/option IDs, answer-key/reveal boundary, score theo actual question count nếu có grading, trạng thái trước/sau submit hoặc flip, resource/source mismatch và review/rejected validation không được bỏ qua. Chạy focused + full verify, cập nhật map/changelog/report và lưu evidence mới. Manual E2E tiếp tục để cuối chuỗi.
