# WorkspaceAI F2-Q06 — Practice Interaction

Ngày thực hiện: 2026-11-12. Phạm vi: service/contracts cho **FR2.05**, nộp đáp án Quiz và xem kết quả, hoặc lật Flashcard để xem back. Kết nối Q05 validation vào practice; chưa đăng ký API/UI. Manual E2E tiếp tục để cuối chuỗi như đã chốt.

## 1. Branch/worktree và phạm vi

```text
Branch: feat/f2-quiz-flashcards
Worktree: C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards
HEAD / origin/main: da40118de0adbda33c55200d30bd9915019d2619
New commits: 0
Legacy: D:\Projects\WorkSpaceAI — feat/f2-document-task-management
```

Tệp mới Q06:

| Tệp | Chức năng |
| --- | --- |
| `backend/algorithms/f2_quiz_grading.py` | Single-choice grading, pure stdlib, không I/O |
| `backend/core/f2_practice_schemas.py` | Submission contracts và learner views trước/sau submit/flip |
| `backend/repositories/f2_practice_repository.py` | In-memory session storage, frozen snapshots, process-local lock |
| `backend/services/f2_practice_service.py` | Scope/Q05 gates, Quiz submission/result và Flashcard interaction |
| `tests/test_f2_practice.py` | 75 automated cases |
| `docs/f2/F2-Q06_REPORT.md` | Báo cáo và bàn giao tích hợp |

Cập nhật thêm `.skills/codebase_map.md`, `CHANGELOG.md`. Q01–Q05 source/tests/reports và tài liệu Q00 giữ nguyên byte theo snapshot trước Q06. F1/F3, frontend và dependencies không sửa. Final scope/preservation audit PASS: chỉ hai tracked docs thay đổi, không staged changes/commit mới; legacy branch/HEAD/index/staged/unstaged diffs và 511 non-ignored tracked/untracked file hashes khớp Q00. Không reset/clean/stash/xóa code cũ/commit/push/merge.

## 2. Quiz interaction đã hoàn thành

```python
service = F2PracticeService(source_repository, sessions=InMemoryPracticeRepository())
view = service.start_quiz(quiz, context=backend_context)
view = service.get_quiz(session_id, context=backend_context)
result = service.submit_quiz(session_id, submission, context=backend_context)
result = service.get_quiz_result(session_id, context=backend_context)
```

`PracticeAccessContext(learner_id, sources: SourceAccessContext)` phải do backend resolver cung cấp. Không có auth implementation mới và không coi learner/workspace ID trong request body là quyền truy cập. Context được reconstruct ở boundary; session gắn cả learner và workspace. Session không tồn tại, khác learner/workspace hoặc sai loại Quiz/Flashcard đều trả `SESSION_NOT_FOUND` trước đọc nguồn.

Quiz start tạo UUID session và copy/revalidate resource nội bộ. `QuizPracticeView` chỉ có session/set ID, status, requested_count, actual_count và questions/options. **Không trả correct_option_id, explanation, source_refs/evidence_quote, resource/source digests hoặc internal resource.** Quotes cũng bị ẩn vì có thể chứa trực tiếp đáp án.

`QuizSubmission` chỉ nhận ordered list/tuple các `QuizAnswer(question_id, option_id)`, mỗi question tối đa một lựa chọn. IDs exact/case-sensitive, strict nonblank strings. Không nhận score, key, verified hoặc validation receipt từ client. Service revalidate cả unsafe copied submission rồi kiểm tra IDs thuộc đúng question trong session.

Các lựa chọn MVP đã thực hiện:

- Một lần submit kết thúc attempt. Submit lại cùng câu trả lời (kể cả đổi thứ tự) trả cùng kết quả sau fresh validation; không chấm thành attempt mới. Submit khác sau đó báo `ALREADY_SUBMITTED`. Làm lại bằng một session mới.
- Cho phép nộp thiếu câu hoặc `answers=[]` một cách tường minh. Câu không trả lời có selected_option_id=None và tính sai; không tự chọn hộ, không tạo câu mới.
- Điểm bằng `100 * correct_count / actual_question_count`, làm tròn 2 số thập phân. Không chia theo mặc định 10 nếu chỉ có 3 câu hợp lệ; không điểm âm hoặc trọng số.
- Trước submit, `get_quiz_result` báo `NOT_SUBMITTED`. Sau submit mới có `QuizPracticeResult`: total/answered/correct count, score_percent và feedback theo thứ tự câu hỏi ban đầu.
- Feedback có lựa chọn đã nộp, key, is_correct, explanation và SourceRefs của từng câu. SourceRefs vẫn **UNVERIFIED** theo hợp đồng Q01; Q05 quyết định nội bộ về extractive support, không sửa cờ provenance này.

Grading algorithm nhận tuples IDs/key đã được backend giữ, không gọi LLM, repository hoặc I/O. Grade phản ánh key đã qua Q05, không tự chứng minh tính đúng đắn của tài liệu bên ngoài.

## 3. Flashcard interaction đã hoàn thành

```python
front = service.start_flashcards(deck, context=backend_context)
view = service.get_flashcard(session_id, context=backend_context)
view = service.flip_flashcard(session_id, card_id=current_card_id, context=backend_context)
front = service.move_flashcard(session_id, "next", card_id=current_card_id, context=backend_context)
front = service.move_flashcard(session_id, "previous", card_id=current_card_id, context=backend_context)
```

- Start tại thẻ đầu, `current_index=0`, mặt trước. `FlashcardFrontView` chỉ mang session/deck/count/index/card ID/front/side; không có key `back` hoặc source refs/quotes trong JSON.
- Flip chuyển front↔back. Chỉ `FlashcardBackView` có back và nguồn của **thẻ hiện tại**; không gửi các back còn lại cùng deck.
- Next/previous theo actual cards, không wrap ở đầu/cuối. Chuyển thẻ luôn reset về front, kể cả quay lại thẻ từng xem; không lộ back trong navigation response.
- Flip/move yêu cầu ID thẻ hiện tại. View cũ gửi ID thẻ khác bị `CARD_MISMATCH`, không lật nhầm thẻ. Direction sai hoặc vượt biên không đổi trạng thái hiện tại.

## 4. Q05 gates, binding và lưu trạng thái

Mỗi start/read/action **thành công** gọi Q05 với backend source scope hiện tại. Practice không nhận serialized receipt/cờ VERIFIED của client. Q05 `REVIEW_REQUIRED` hoặc `REJECTED` làm `RESOURCE_NOT_READY`; không khởi tạo session hoặc trả/reveal nội dung tương ứng.

Session giữ resource_digest và source_snapshot_digest từ Q05 lúc start. Mọi action/read sau đối chiếu resource digest và current selected-source digest với bản gốc:

- Resource thay đổi: `RESOURCE_CHANGED`.
- Nguồn vẫn hỗ trợ item nhưng selected prepared snapshot thay đổi: `SOURCE_CHANGED`; bắt đầu lại từ học liệu/nguồn hiện tại.
- Nguồn không còn hợp lệ, thiếu/quyền bị thu hồi hoặc Q05 không sẵn sàng: `RESOURCE_NOT_READY`.

Không bỏ qua gate ở retry cùng submission hoặc đọc kết quả đã nộp. Source change/read/access failure không ghi submission, không lật/chuyển thẻ. Input/state errors không kèm đáp án nội bộ trong thông báo lỗi.

Frozen session records giữ Quiz/Deck snapshots riêng và submission/reveal/index; mọi learner response được dựng bằng allowlist DTO, không serialize session. Repository có RLock; service giữ lock trong read→check→update để hai submit đồng thời không ghi đè attempt. Test dùng hai service instances cùng injected repository để xác nhận chỉ một conflicting submission thành công.

Đây là **in-memory, process-local** storage, không global singleton hoặc SQLite. Service khác chỉ thấy sessions khi được inject cùng repository. Restart mất sessions; chưa TTL/eviction, multi-worker coordination hoặc durable audit. Lock của sessions không khóa source repository; Q05 vẫn có giới hạn hai lần đọc/không transaction, không bảo đảm freshness sau return. Source digest chỉ bao phủ prepared passages/issues/selection/workspace, không tính lại hash raw file.

## 5. Kết quả kiểm thử thực tế

| Nhóm acceptance | Bằng chứng trong tests/test_f2_practice.py |
| --- | --- |
| Learner boundary | JSON không chứa key/explanation/quote/back/digest trước submit/flip; kết quả chưa nộp bị chặn; frozen nested DTOs và round-trip |
| Quiz scoring/state | All correct/all wrong, partial/empty submission, actual count thay requested 10, rounded score, question order, idempotent reorder retry, final attempt và new attempt |
| Input/state safety | Unknown/case-mismatched IDs, multi-answer/duplicate/forged score/verified, unsafe copies; invalid submit không đổi trạng thái |
| Scope/Q05 | Wrong learner/workspace/type/session/context, denied/revoked permission, review-required/rejected/forged resources, original-model snapshot độc lập |
| Freshness/binding | Get/submit/result/flip/move đều chặn stale sources; uncited source digest changes; resource tamper; idempotent retry vẫn kiểm nguồn |
| Flashcard | Front/back toggle, sources chỉ sau flip, previous/next/reset, count/boundaries/single card, stale current-card IDs |
| Concurrency/storage | Two-service conflicting submissions chỉ một thành công, riêng repository thì không tự thấy session |
| Integration/R2 | Real two-document TXT ingestion → Q02 → Q03/Q04 → Q05 → practice; grading imports chỉ stdlib, không network/email |

Lệnh được thực chạy qua RTK proxy, Python:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\tmp\workspaceai-audit-venv\Scripts\python.exe
```

| Lệnh/check | Kết quả |
| --- | --- |
| `python -m pytest tests/test_f2_practice.py -v` lần đầu | 69 passed, exit 0; 2.58s theo pytest |
| Cùng lệnh sau thêm boundary cases, focused-final | **75 passed**, exit 0; 2.07s theo pytest |
| `python verify.py` | **451 passed, 1 warning**, exit 0; 7.40s theo pytest |
| AST syntax | **65 Python files PASS** |
| R2 gate + subprocess grading isolation | **PASS** |
| Scope/diff/legacy preservation audit | **PASS** |

451 = 30 baseline F1/F3/pipeline + 81 Q01 + 55 Q02 + 60 Q03 + 72 Q04 + 78 Q05 + 75 Q06. Các tests Q01–Q05 giữ nguyên và thực sự được chạy lại trong full suite. CPython 3.12.14, pytest 9.2.0, LLM_PROVIDER=mock, EMAIL_DISPATCH_MODE=local_mock, CI=true. Full verify chạy với loopback cục bộ cho TestClient. Không gọi live Ollama/gửi email/DB.

Starlette/TestClient httpx deprecation warning có từ baseline vẫn tồn tại; không sửa dependencies/F1/F3. Không build lại frontend vì không sửa frontend. Đã tự review, chưa independent review hoặc browser/user E2E. Các tests này không chứng minh UI sản phẩm đã tích hợp.

Evidence ngoài checkout:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q06-2026-11-12\evidence\
  baseline\focused.log / focused.json
  baseline\focused-final.log / focused-final.json
  baseline\verify.log / verify.json
  before\codebase_map.md / CHANGELOG.md
  before-files-sha256.json
  q06-only.patch
  final-audit.json
  legacy-preservation.json
  status.txt
  worktrees.txt
```

## 6. Những gì chưa hoàn thành

- Chưa có study HTTP routes, runtime service wiring hoặc UI cho chọn nguồn/sinh học liệu/practice; người dùng chưa thể test F2 mới qua trình duyệt. Q06 là internal service flow, không tuyên bố MVP sản phẩm đã hoàn thành.
- Chưa có backend auth/workspace/learner resolver. Context hiện là trusted caller contract; API sau không được dựng authority trực tiếp từ client IDs.
- In-memory sessions chưa có durability, TTL/capacity management, multi-worker state hoặc idempotency keys cho Flashcard toggles. `card_id` chặn thao tác trên thẻ khác, không phải revision token chống mọi stale request khi quay lại cùng thẻ.
- Giữ giới hạn Q05: chỉ extractive definition support, known injection/literal ambiguity checks, metadata/chunks source truth và point-in-time rechecks. Chưa có live model/corpus evaluation hay general semantic verifier.
- Chưa có SQLite, spaced repetition, editable answer review hoặc history dashboard. SQLite tiếp tục sau MVP, không đưa Task Management schema cũ vào F2 mới.
- User manual E2E để cuối chuỗi; warning baseline chưa xử lý.

## 7. Task Context Packet — Bước tiếp theo Q08 API/UI integration

Q08 chưa thực hiện trong lần này. Theo quyết định SQLite sau luồng MVP, tiếp theo là nối luồng API/UI; Q07 persistence tiếp tục trì hoãn. Không tự triển khai Q07 trong Q06.

Giữ cùng branch/worktree và toàn bộ Q00–Q06 chưa commit. Baseline: **451 tests PASS**, AST 65, R2 PASS. F1/F3/legacy giữ nguyên; không commit/push/merge/reset/clean/stash. Đọc interfaces Q02–Q06 trong map và các report khi cần, không đưa legacy Task Management vào học liệu.

Chuỗi service hiện có để tích hợp:

1. Backend resolve source permissions và learner identity; chọn exact document IDs thuộc workspace. Không tin `workspace_id/learner_id/allowed_doc_ids` do request body tự khai.
2. Q02 `F2SourceService.prepare_sources` → Q03 `generate_quiz` hoặc Q04 `generate_flashcards`. Giữ status/issues/actual count và thông báo thiếu nguồn, không bù mặc định 10 bằng nội dung bịa.
3. Q06 `start_quiz/start_flashcards` tự gọi Q05; chỉ trả learner projection nếu validation ready. Reuse một explicit session repository trong runtime process; không tạo repository mới mỗi request.
4. Quiz get/submit/result đi qua Q06. Client chỉ gửi question/option IDs; không trả internal QuizSet, session, receipt hoặc quotes trước submit. Flashcard read/flip/move trả đúng `FlashcardFrontView | FlashcardBackView`; dùng union response để không làm mất back khi đã flip hoặc vô tình trả hidden deck.
5. Đưa error codes thành thông báo/recovery rõ: chưa nộp, đã nộp, stale source/resource, missing session, invalid answer/card/direction. Phải đi qua current gates cả khi xem lại kết quả.

UI cần select một/nhiều uploaded sources và Quiz/Flashcards, mặc định 10, partial/insufficient/error/review feedback, Quiz submit/reveal và Flashcard flip/previous/next. Giữ F1/F3. Chọn frontend thực tế sau khảo sát integration points; chưa có quyết định đổi framework trong Q06.

Validation tiếp theo: API tests kiểm learner projection/permissions/errors/state, frontend build nếu sửa frontend, full verify và manual end-to-end ở cuối chuỗi. Q09 evaluation/release còn sau; Q07 SQLite chỉ sau MVP theo quyết định hiện tại.
