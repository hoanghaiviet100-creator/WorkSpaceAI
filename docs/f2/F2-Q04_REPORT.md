# F2-Q04 — Flashcard Generation

Trạng thái: **DONE trong phạm vi Q04**. Ngày 2026-11-12, Asia/Bangkok. Mapping chính **FR2.04**; dùng contracts Q01 và nguồn Q02. Các SourceRefs tiếp tục UNVERIFIED, không tuyên bố đã hoàn thành Q05 hoặc F2 end-to-end.

## 1. Git và phạm vi thay đổi

```text
Branch: feat/f2-quiz-flashcards
HEAD/base: da40118de0adbda33c55200d30bd9915019d2619
Worktree: C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\f2-quiz-flashcards
Legacy: D:\Projects\WorkSpaceAI
Legacy branch/HEAD: feat/f2-document-task-management @ 730dc75f57a517adc322ec243fed66eaa47825b9
```

Tệp mới:

- `backend/algorithms/f2_flashcard_generation.py`
- `backend/providers/f2_flashcard_provider.py`
- `backend/services/f2_flashcard_service.py`
- `backend/algorithms/f2_definition_extraction.py`
- `backend/providers/f2_study_provider.py`
- `backend/services/f2_generation_support.py`
- `tests/test_f2_flashcard_generation.py`
- Báo cáo này.

Tệp Q03 được refactor: `backend/algorithms/f2_quiz_generation.py`, `backend/providers/f2_quiz_provider.py`, `backend/services/f2_quiz_service.py`. Đã lưu bản trước Q04 ở output/evidence/before và kiểm tra hash khớp audit Q03 trước khi sửa. Refactor tách các cơ chế chung để hai generator dùng cùng nguồn, JSON policy và HTTP behavior; không sửa tests/báo cáo Q03 để làm regression pass.

Cập nhật `.skills/codebase_map.md`, `CHANGELOG.md`. Q01/Q02 source/tests/report, shared parser/repository, F1/F3, frontend, dependency/lockfiles và database giữ nguyên. Không sửa runtime entrypoints hoặc tạo singleton mới.

Không commit, push, merge, reset, clean, stash hoặc thay staging. Code và tài liệu vẫn unstaged/untracked. Audit cuối kiểm tra chỉ đúng các tệp Q04/refactor/tài liệu; legacy branch/HEAD/status/index/staged+unstaged diff và manifest **511 tracked/untracked files** khớp Q00. Ignored files không thuộc manifest đó.

## 2. Hành vi đã triển khai

Interface:

```python
F2FlashcardService(
    provider=None, *, fallback_provider=None, max_back_words=60,
).generate_flashcards(prepared: PreparedStudySources) -> FlashcardGenerationResult
```

- Chỉ nhận kết quả nguồn nội bộ Q02, revalidate selection và SourceRefs, yêu cầu format Flashcards. Raw dict, nguồn ngoài selection, fake verified, version/hash/span không nhất quán bị chặn trước provider.
- Không có nguồn thì không gọi provider. Không fallback sang nguồn ngoài selection hoặc dữ liệu UI toàn cục.
- Provider chỉ trả JSON root `cards`; từng item có đúng `front`, `back`, `source_ids`. Front là prompt/câu hỏi, back là đáp án ngắn.
- Service dùng aliases S1/S2/... để gắn lại **nguyên SourceRef từ snapshot Q02**. Provider không được tự đưa card_id, source_refs, doc/version/hash hoặc cờ verified.
- Validate front/back không rỗng, metadata/extra fields và source_ids theo đúng contracts. JSON sai/root sai/prose/fences/duplicate JSON keys/NaN/Infinity/response quá lớn bị từ chối.
- Gán IDs card/deck tại backend sau khi lọc; IDs card liên tục c1, c2,...; không để provider điều khiển IDs.
- Giữ source_issues của Q02 và generation issues kèm card_index khi phù hợp. Không tạo deck rỗng để giả thành công, không sinh bù để đủ 10 khi thiếu nội dung.

### Offline và độ ngắn của back

Default `DeterministicFlashcardProvider` dùng các định nghĩa literal không mơ hồ. Một định nghĩa đã đủ để tạo một card, không cần distractors như Quiz. Front có dạng “{term} là gì?”, back lấy definition body đã gộp soft-wrap/whitespace; evidence_quote trong SourceRef vẫn nguyên văn.

Duplicate/conflicting definitions và aliases có cùng definition body bị lọc theo cùng chính sách literal đã có ở Q03. Adapter không giả lập hiểu/summarize arbitrary fact/example/procedure. Nếu không có định nghĩa dùng được thì trả insufficient.

Để hiện thực back ngắn gọn, Q04 dùng **max_back_words=60 mặc định, có thể cấu hình**, đếm từ bằng whitespace. Đây là chính sách cục bộ của generation, không phải giới hạn sản phẩm đã được người dùng chốt và không thêm restriction vào schema Q01. Service kiểm back của mọi provider; offline adapter cũng bỏ definition quá dài. Không cắt cụt đáp án vì có thể làm sai nghĩa. Khi override giới hạn, caller nên cấu hình cùng giá trị cho service và prompt Ollama.

### Dedup và mâu thuẫn

Front/back được so theo gộp whitespace + casefold:

- Cùng front và cùng back: giữ bản đầu, ghi DUPLICATE_CARD.
- Cùng front nhưng back khác: bỏ **tất cả** candidates của front đó, ghi CONFLICTING_CARD; không tự chọn một đáp án.
- Kiểm tra toàn bộ response trước khi áp count limit, nên một conflict xuất hiện sau khi đã đủ count vẫn loại bản trước.
- Sau lọc mới giữ tối đa requested_count và gán card IDs. Excess/shortage đều có issue rõ ràng.

Đây là phát hiện trùng/mâu thuẫn literal, không phải semantic contradiction detection; Q05 còn phải kiểm chứng nội dung và bằng chứng.

### Ollama và fallback

`OllamaFlashcardProvider(base_url, model, *, transport=None, max_back_words=60)` dùng transport chung: `/api/generate`, `format=json`, `stream=False`, read timeout 60s/connect 2s, không redirects/retries, body cap 1,000,000 bytes. Prompt yêu cầu cards/front/back/source_ids, giới hạn back, không bịa khi thiếu nguồn.

Nguồn/attributes được HTML-escape và đóng khung `<untrusted_document_data>` với nhãn dòng. Timeout, unavailable, invalid/incomplete/oversized outer response đều có typed error. Adapter mới **chỉ được kiểm thử bằng HTTP giả lập**, chưa chạy model thật hoặc đo chất lượng corpus.

Fallback chỉ khi caller cấu hình và primary báo PROVIDER_TIMEOUT hoặc PROVIDER_UNAVAILABLE; ghi FALLBACK_USED và provider_name thực tế. Không dùng fallback để che malformed JSON hoặc invalid cards. Default không phát sinh network/email/DB.

### Kết quả

`FlashcardGenerationResult` frozen giữ workspace_id, selection, deck, provider_name, issues, source_issues, failed; `.status`/`.message` được suy ra:

| Status | Ý nghĩa |
| --- | --- |
| COMPLETE | Đủ count và không issues; chỉ nói về cấu trúc/count, không phải semantic verification |
| PARTIAL | Có deck nhưng thiếu cards hoặc có source/generation/fallback warnings |
| INSUFFICIENT_CONTENT | Không có nguồn hoặc provider trả [] vì không tạo được cards phù hợp; deck=None |
| ERROR | Provider/JSON lỗi hoặc mọi card đều invalid/conflicting/quá dài; deck=None |

## 3. Refactor chung và tương thích Quiz

| Helper mới | Trách nhiệm |
| --- | --- |
| `f2_definition_extraction.extract_unambiguous_definitions` | Thuật toán parsing/dedup definitions trước đây nằm trong Quiz; thuần stdlib, không I/O |
| `f2_study_provider.StudyEvidence`, `StudyProviderError` | Kiểu dữ liệu/exception chung; QuizEvidence/QuizProviderError vẫn import được qua aliases cũ |
| `format_study_evidence`, `OllamaStudyProvider` | Evidence framing và HTTP JSON transport dùng cho cả hai generator |
| `prepare_generation_snapshot` | Revalidate snapshot với required_format; không authenticate caller hoặc re-read live repository |
| `parse_generation_items` | Strict JSON root/items parsing có byte cap và duplicate-key/nonstandard-constant rejection |
| `resolve_source_ids` | Map aliases chính xác về SourceRefs backend đang giữ |

Q03 public imports, constructor/method signatures và error codes vẫn có. Transport error wording được tổng quát từ Quiz sang “học liệu”. Type evidence/error công khai của Quiz hiện là alias của shared type, không phải một class độc lập mới. Q03 algorithm/provider/service thực sự có thay đổi source; không tuyên bố byte-identical. **60 tests Quiz cũ không sửa và vẫn PASS**, rồi tiếp tục PASS trong full suite.

## 4. Acceptance và kết quả kiểm thử

| Nhóm acceptance | Bằng chứng trong tests/test_f2_flashcard_generation.py |
| --- | --- |
| Count/front/back/provenance | Default 10 cards từ 12 definitions; override count; một definition tạo một card; raw quote giữ nguyên, refs UNVERIFIED |
| Nội dung ngắn/thiếu | Boundary 60 words, configurable cap, loại back dài không cắt, nguồn rỗng/non-definition/ambiguous trả partial hoặc insufficient |
| Structured output/source boundary | Blank/type sai/missing fields, IDs lạ/trùng, forged card ID/hash/refs/verified, malformed/ambiguous/oversized JSON bị chặn |
| Dedup/conflict | Case/whitespace duplicates; same-front conflicting backs loại cả bản đầu; conflict sau count limit vẫn được kiểm tra; IDs sau lọc liên tục |
| Input snapshot | Dict/wrong format, unsafe copied selection/ref, foreign doc, conflicting hash/version, fake verified/span/kind sai bị chặn trước provider |
| Integration | DocumentService thật → Q02 từ hai tài liệu → 10 cards; independent source snapshots, JSON round-trip và frozen result |
| Prompt/HTTP/fallback | Escaping markup/attributes và max_back_words; mocked Ollama success/timeout/connect/HTTP/malformed/incomplete/oversized; fallback rõ, không che JSON sai |
| R2/regression | Flashcard + shared definition algorithms chỉ stdlib, không external I/O; 60 Quiz tests giữ nguyên |

Đã chạy:

| Lệnh/check | Kết quả thực tế |
| --- | --- |
| `python -m pytest tests/test_f2_quiz_generation.py -v` sau refactor | **60 passed**, exit 0; 1.30s theo pytest |
| `python -m pytest tests/test_f2_flashcard_generation.py -v` | **72 passed**, exit 0; 1.00s theo pytest |
| `python verify.py` | **298 passed**, exit 0; 4.16s theo pytest |
| AST qua verify.py | **56 Python files PASS** |
| R2 gate + subprocess algorithms tests | **PASS** |
| Scope/preservation audit | PASS; không staged changes/commit mới; Q01/Q02 source/tests/report và Q03 tests/report giữ nguyên; legacy 511 hashes/index/diffs khớp |

298 = 30 baseline F1/F3/pipeline + 81 Q01 + 55 Q02 + 60 Q03 + 72 Q04. Một Starlette/TestClient deprecation warning vẫn tồn tại từ baseline. Không sửa dependencies/F1/F3 để xử lý warning. Không build lại frontend vì không có thay đổi frontend/dependencies.

Runtime dùng CPython 3.12.14, pytest 9.2.0; LLM_PROVIDER=mock, EMAIL_DISPATCH_MODE=local_mock. Ollama requests là MockTransport; không gọi live model hoặc gửi email. Full verify chạy ngoài sandbox do TestClient cần loopback. Tự review đã thực hiện; chưa có independent review hoặc user/browser E2E.

Raw command/cwd/env/exit codes và logs:

```text
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q04-2026-11-12\evidence\baseline\quiz-regression.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q04-2026-11-12\evidence\baseline\quiz-regression.json
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q04-2026-11-12\evidence\baseline\focused.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q04-2026-11-12\evidence\baseline\focused.json
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q04-2026-11-12\evidence\baseline\verify.log
C:\Users\ADMIN\Documents\ChatGPT\WorkspaceAI (Computational Thinking)\output\f2-q04-2026-11-12\evidence\baseline\verify.json
```

Diff riêng Q04 gồm new files lẫn 3 Q03 refactors và map/changelog, snapshot trước sửa, hashes/audit/status/worktrees/legacy preservation ở cùng evidence/. Không sửa báo cáo lịch sử Q00–Q03 hoặc TEAM HANDOFF Q00–Q02; báo cáo này ghi hiện trạng Q04.

## 5. Giới hạn còn tồn tại

- Cards là bản sinh nội bộ, SourceRefs UNVERIFIED. Cấu trúc/quote hợp lệ không chứng minh đáp án đúng hoặc được nguồn hỗ trợ về nghĩa.
- Offline chỉ xử lý định nghĩa literal; back extraction không phải abstractive summarization. 60 words là policy đếm whitespace, không đo semantic completeness hoặc readability.
- Ollama mới có mocked transport tests, chưa có accuracy/latency benchmark với model/tài liệu thật.
- PreparedStudySources là trusted-caller contract, chưa authenticate hoặc giải quyết quyền workspace. Không đọc lại raw bytes/live source; snapshots có thể stale sau Q02. Metadata integrity/freshness vẫn cần gate ở task sau.
- Framing/lọc JSON không chứng minh chống được mọi prompt injection hoặc mọi phát biểu sai. Conflicting-card filter chỉ so literal, không phát hiện mọi paraphrase mâu thuẫn.
- Chưa có flip/navigation/practice state, study API/UI, persistence, spaced repetition hoặc release evaluation. Không dùng 298 tests để tuyên bố toàn bộ F2 chạy end-to-end.

## 6. Bàn giao F2-Q05 — Content Validation & Grounding

Q05 chưa triển khai trong lần này. Giữ cùng worktree/branch và mọi thay đổi Q00–Q04 chưa commit. Baseline lúc bàn giao: **298 tests PASS**, AST 56 files, R2 PASS.

- Goal: kiểm tra QuizSet/FlashcardDeck trước khi phát hành học liệu; map FR2.02–FR2.04 theo kế hoạch.
- Tệp đã đề xuất: `backend/algorithms/f2_study_validation.py` (pure stdlib), `backend/services/f2_study_validation_service.py`, `tests/test_f2_study_validation.py`; thêm result contract riêng nếu cần và ghi rõ scope.
- Phân biệt structural validation, quote/source validity và answer/content support. Không coi correct option xuất hiện trong quote, hoặc quote match, là proof cho mọi ngữ nghĩa của câu hỏi.
- Negative cases cần có: wrong answer key với quote thật, unsupported back, fabricated explanation, wrong/stale/foreign doc/version/hash, wrong page/chunk/span, quote không tồn tại, nội dung mâu thuẫn và prompt injection.
- SourceRef Q01 chỉ cho UNVERIFIED. Kết quả kiểm chứng nên có envelope/trạng thái riêng; không nhận cờ provider/client để tự chuyển verified. Các trường hợp không chứng minh được support cần abstain/ambiguous/review-required thay vì false VERIFIED.
- Caller phải cấp source truth/context đáng tin để kiểm freshness/scope. Không sửa F1/F3 hoặc coi client workspace ID là authorization đã hoàn thành.
- Dùng các helper chung F2 khi phù hợp, giữ 60 Quiz và 72 Flashcard tests cùng contracts/source-layer tests. Chạy focused tests và full verify, lưu AC/log/diff trước bước tiếp.
- Q06 interaction và Q08 API/UI còn ở task sau; Q07 SQLite sau MVP, Q09 evaluation/release. Manual E2E của người dùng tiếp tục để cuối chuỗi như đã chốt.
