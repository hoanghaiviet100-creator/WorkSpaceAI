# WorkspaceAI — Changelog & Roadmap

Tất cả các thay đổi và nâng cấp quan trọng của dự án **WorkspaceAI (CSC10014 Track C - Intelligent Document Workspace)** được ghi nhận tại đây theo chuẩn [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased] — 2026-11-13 — F2 Structured Quiz & Interactive Draft Preview
### Added
- Typed LLM Quiz wire contract and shared JSON Schema for prompt, Gemini response and backend validation; server still owns question IDs/source refs. Require 2–4 distinct options, one key, explanation and source aliases.
- Explicit UNVERIFIED_DRAFT preview DTOs and `F2StudyDraftService.preview_quiz`: real-source rechecks on render/submit/result, proposed-answer comparison with existing grading, no Q06 session or verification flag.
- Quiz draft radio form, submit, proposed-answer feedback/explanation/citations, retry and return to author review. No answers rendered in the preview form before submission; source failures/rejected content block preview.
- 44 new backend/HTTP/AppTest cases and `docs/f2/F2_STRUCTURED_QUIZ.md` for the actual contract, UI flow and evidence.
### Changed
- Source-content Quiz prompt asks for complete natural questions and explicit subjects/functions, removes cloze priority, asks to skip missing context and preserves source/Math-solving boundaries. Flashcard prompt and old definition mode retained.
- Q03 validates each parsed item with the typed contract; existing strict JSON/provenance/partial-result behavior retained. Hot reload upgrades review service without clearing documents/key widgets.
### Verification and boundaries
- Focused-final: 262 passed. Full verify: 653 passed, AST82, R2 PASS; one existing Starlette/TestClient warning. Initial focused run found incorrect array-schema keywords; fixed field constraint ordering, then focused and full suites passed. Failure log retained.
- Real cloud calls simulated by MockTransport; AppTest exercises actual ingestion/generation/review/form/submission. Browser verifies updated empty/config state only; no agent-driven use of user PDF/key or claim of measured live question quality.
- F1/F3, Q01/Q05/Q06 and legacy preserved; no dependency/auth/API route/persistence change, stage/commit/push/merge/reset/clean/deletion. Semantic certification remains limited; unverified preview compares against AI proposals. SQLite and specialized Math/Physics solving remain deferred.

## [Unreleased] — 2026-11-13 — F2 Source Inspection & Broader Content Review
### Added
- Read-only extracted-text preview with actual character/page/passage/category counts and PDF/encoding/symbol warnings, using existing provenance/scope checks. No OCR or parser changes.
- Source-content prompt wrapper for Gemini/NVIDIA NIM/Ollama, including facts, rules, conditions, examples and procedures. Retains original definition mode and offline generator; no count padding or math solving.
- Pure-stdlib full-quote cloze checks alongside definition validation, retaining REVIEW_REQUIRED for general/paraphrased/unproven items.
- Author draft review with item-level reasons and current citations; explicit independently verified subset for Q06 practice. Full draft retained; no flag bypass or cached source content shown when current source checks fail.
- 58 tests for inspection, mocked cloud protocol, conservative validation, subset freshness and UI. Guide/evidence in `docs/f2/F2_SOURCE_CONTENT_REPORT.md`.
### Changed
- UI defaults AI to `Nội dung tài liệu`, separates no usable source / empty model output / API failure, preserves non-ready resources as author drafts. HTTP errors show status numbers without bodies/keys.
- Receipt permits `EXTRACTIVE_STUDY_V2`; original definition method and Q01 reference status remain compatible. Runtime hot reload retains repository/password widgets and uses updated verifier.
### Verification and boundaries
- Focused 158 passed; full `verify.py`: 609 passed, AST78, R2 PASS. One existing Starlette/TestClient deprecation warning. Cloud tests use MockTransport; no agent-driven real API call or evaluation of user PDFs.
- Browser verified updated local UI/default broader mode. Previous server was no longer listening; restarted hidden on 127.0.0.1:8512, so user must re-upload/re-enter session-only data. No persistence added.
- F1/F3 and legacy Task Management preserved; no staging, commit, push, merge, reset, clean or deletion. General semantic certification, specialized Math/Physics solving and OCR remain unimplemented; SQLite after MVP.

## [Unreleased] — 2026-11-12 — F2 NVIDIA NIM UI integration
### Added
- `backend/providers/f2_nvidia_nim_provider.py`: isolated NVIDIA-hosted Chat Completions adapters for Quiz/Flashcards. Header Bearer auth, bounded non-streamed requests, explicit errors/pending response handling, no redirect/retry/poll or silent fallback.
- `backend/providers/f2_definition_prompts.py`: existing Gemini definition policy shared with NIM. Gemini delegates to the helper with unchanged prompt content/HTTP behavior; Q05 stays unchanged.
- Separate NVIDIA API key/model controls in the local UI, server NVIDIA_API_KEY/NVIDIA_NIM_MODEL fallback and explicit NVIDIA source-transmission notice. Gemini credentials are not reused for NVIDIA.
- `tests/test_f2_nvidia_nim_provider.py`: 48 protocol, source-scope, error, Q05 and UI tests using simulated HTTP only. `docs/f2/F2_NVIDIA_NIM.md`: real-key usage, Google-key location, evidence and current limits; older guides link to it.
### Verification and boundaries
- Focused: 48 passed. Full `verify.py`: 551 passed, AST73 files, R2 PASS; previous 503 tests unchanged, including 43 Gemini cases. Browser NIM configuration surface verified. No live NVIDIA request/key/quota/model accuracy test.
- Q00–Q06 code/tests/reports, F1/F3 and legacy Task Management preserved. No auth/API/persistence/dependency/staging/commit/push/merge changes. NIM asks for JSON by prompt; format and content must still pass existing strict service/Q05 checks.

## [Unreleased] — 2026-11-12 — F2 Gemini/Ollama UI integration
### Added
- Separate `backend/providers/f2_gemini_provider.py`: real Gemini generateContent HTTP adapters for Quiz/Flashcards, authenticated by header with structured JSON output, bounded responses/timeouts, explicit errors and no silent fallback. Prompts stay within current extractive definition validation policy.
- `tests/test_f2_ai_providers.py`: 43 protocol/security/error and service/UI integration cases using simulated HTTP only. `docs/f2/F2_AI_PROVIDERS.md`: real-key usage, selected source transmission, model configuration, evidence and limits.
### Changed
- Temporary UI selects Offline/Gemini/Ollama, accepts a masked session Gemini key or server environment key, shows requested model and actual generation errors. Existing Ollama adapters are selectable without shared provider edits. Missing Gemini key disables generation; configured key is not presented as validated.
- Previous manual UI guide links to the new provider instructions while retaining its original point-in-time evidence.
### Verification and boundaries
- Focused: 43 passed. Final full `verify.py`: 503 passed, AST 70 files, R2 PASS; original 460 tests unchanged. Browser configuration surface verified. No live Gemini/key/quota or Ollama model evaluation; no real key was present at implementation start.
- Q01–Q06 code/tests/reports, F1/F3/shared settings/provider and legacy Task Management preserved; no dependency/SQLite/API/auth/commit/push/merge/staging changes. Successful Gemini HTTP output still needs unchanged Q05 support before practice.

## [Unreleased] — 2026-11-12 — F2 temporary manual UI
### Added
- Separate `frontend/f2_manual_app.py` and `frontend/components/f2_manual_panel.py`: local Streamlit UI calling existing ingestion/Q02–Q06 for real documents, generation, validation, Quiz submission/results and Flashcard navigation/flip. Starts with no documents or prepared results; no synthetic learning output or new backend functionality.
- `tests/test_f2_manual_ui.py`: 9 real-service AppTest integration cases. `docs/f2/F2_MANUAL_UI.md`: access/restart instructions, actual checks and limits.
### Verification and boundaries
- Final focused tests: 9 passed; full `verify.py`: 460 passed, AST 68 files, R2 PASS. Browser initial UI/layout and local server health verified; no automated browser file-picker upload or live Ollama evaluation. An initial AppTest fixture selection failure was corrected; logs retained outside checkout.
- Q00–Q06 source/tests/reports, F1/F3 and legacy Task Management preserved. This temporary local UI does not complete Q08 API/auth integration. No SQLite, dependency changes, staging, commit/push/merge or removal of previous code.

## [Unreleased] — 2026-11-12 — F2-Q06 Practice Interaction
### Added
- `backend/algorithms/f2_quiz_grading.py`: pure-stdlib single-choice scoring by actual question count; track correct/incorrect/unanswered answers, reject unknown IDs and repeated selections.
- `backend/core/f2_practice_schemas.py`: explicit frozen learner DTOs for Quiz questions/results and Flashcard front/back. Before submit/flip, omit keys, explanations, source quotes, hidden backs and internal validation digests.
- `backend/repositories/f2_practice_repository.py`: explicit process-local in-memory sessions with immutable resource snapshots and a reentrant transaction lock. No SQLite or global singleton.
- `backend/services/f2_practice_service.py`: learner/workspace-scoped Quiz start/read/submit/result and Flashcard start/read/flip/previous/next. Rerun Q05 at each successful read/action and pin original resource/source digests; fail without state changes on denied/stale/invalid inputs. Idempotent identical Quiz submissions, final submitted attempts and safe card navigation/reveal boundaries.
- `tests/test_f2_practice.py`: 75 cases for hidden-answer serialization, score/count/partial attempts, invalid and forged input, access/freshness gates, immutable snapshots, concurrent conflicting submissions and real two-document flows.
- `docs/f2/F2-Q06_REPORT.md`: measured results, MVP interaction decisions, evidence and API/UI handoff.
### Verification and boundaries
- Focused: 75 passed. Full `verify.py`: 451 passed, AST 65 files, R2 PASS; existing Starlette/TestClient warning remains.
- Q01–Q05 source/tests/reports, F1/F3 and legacy Task Management preserved. No API/UI registration, auth resolver, SQLite, live model/manual browser evaluation, commit/push/merge or staging changes. Sessions disappear on process restart and do not coordinate multiple workers; SQLite remains after the MVP flow.

## [Unreleased] — 2026-11-12 — F2-Q05 Content Validation & Grounding
### Added
- `backend/algorithms/f2_study_validation.py`: pure-stdlib source-relative support checks for offline Quiz/Flashcard definition templates. Check key, full explanation/back, source-derived options, literal ambiguity and citation relevance separately from quote existence; abstain on unsupported or general semantic forms.
- `backend/core/f2_validation_schemas.py`: immutable internal per-item/source/support results and overall VERIFIED/REVIEW_REQUIRED/REJECTED receipt with derived release_ready. Q01 references keep UNVERIFIED; provider/client flags do not become validation truth.
- `backend/services/f2_study_validation_service.py`: structural revalidation and backend context checks, live Q02 source re-read, exact reference matching, known-injection rejection, second source snapshot comparison, duplicate/count warnings, and resource/source SHA-256 bindings. Any rejection or unresolved review prevents automatic release of the set/deck.
- `tests/test_f2_study_validation.py`: 78 cases including wrong key with a true quote, unsupported explanations/answers, forged/stale/foreign sources, exact anchors/quotes, source changes/read failures, ambiguity/injection, internal receipt binding and real two-document generation-to-validation flows.
- `docs/f2/F2-Q05_REPORT.md`: actual implementation, test evidence, limits and Q06 practice handoff.
### Verification and boundaries
- Focused: 78 passed. Full `verify.py`: 376 passed, AST 60 files, R2 PASS; existing Starlette/TestClient warning remains.
- Q01–Q04 source/tests and F1/F3 unchanged; legacy Task Management preserved. No runtime/API/UI registration, general-purpose semantic judge, auth resolver, grading, SQLite, live model evaluation, commit/push/merge or staging changes. Receipts are source-relative, point-in-time internal results; they do not prove external factual correctness or ongoing freshness.

## [Unreleased] — 2026-11-12 — F2-Q04 Flashcard Generation
### Added
- `backend/algorithms/f2_flashcard_generation.py`, `backend/providers/f2_flashcard_provider.py`, `backend/services/f2_flashcard_service.py`: definition-based offline generation plus explicit Ollama adapter, short front/back cards, exact source mapping, count limits, partial/insufficient/error results and optional reported fallback.
- Configurable local max_back_words=60 policy: omit long backs without truncation. Deduplicate normalized prompts and remove all same-prompt candidates with conflicting literal answers, including conflicts appearing after the requested count.
- `tests/test_f2_flashcard_generation.py`: 72 cases including real two-document ingestion through Q02, source/JSON trust boundaries, length policy, duplicates/conflicts, timeout/fallback, prompt framing and stdlib isolation.
- `docs/f2/F2-Q04_REPORT.md`: measured implementation, scope/refactor record, test evidence and Q05 handoff.
### Changed
- Extract common definition parsing, evidence framing/Ollama transport and snapshot/JSON/source-ID validation into `f2_definition_extraction.py`, `f2_study_provider.py`, `f2_generation_support.py`.
- Q03 Quiz algorithm/provider/service delegate shared mechanics; public Quiz names remain available, with evidence/error aliases to common types. Transport error wording now refers to study resources. Q03 tests/report remain unchanged and all 60 regression tests pass.
### Verification and boundaries
- Flashcards focused: 72 passed. Quiz regression: 60 passed. Full verify.py: 298 passed, AST 56 files, R2 PASS; existing Starlette/TestClient warning remains.
- Q01/Q02, F1/F3 and legacy Task Management preserved. No new runtime registration, auth/freshness resolver, semantic proof, grading, study API/UI, SQLite or commit/push/merge. Ollama is tested with simulated HTTP, not a live model/corpus.

## [Unreleased] — 2026-11-12 — F2-Q03 Quiz Generation
### Added
- `backend/algorithms/f2_quiz_generation.py`: pure-stdlib offline MCQs from distinct, unambiguous definitions with source-derived options and no count padding.
- `backend/providers/f2_quiz_provider.py`: deterministic default, isolated Ollama JSON adapter, escaped/line-labelled untrusted source prompt, finite HTTP timeouts and bounded response size. No QA/email provider edits.
- `backend/services/f2_quiz_service.py`: Q02 snapshot revalidation, source-ID-to-reference mapping controlled by backend, strict structured output parsing, invalid/duplicate rejection, count limits, partial/insufficient/error results and explicit optional fallback reporting.
- `tests/test_f2_quiz_generation.py`: 60 cases including real ingestion/Q02-to-Quiz integration, source mapping, malformed/forged outputs, escaped prompt framing and simulated Ollama success/failure/timeout.
- `docs/f2/F2-Q03_REPORT.md`: implementation, measured checks, limits and Q04 handoff.
### Verification and boundaries
- Focused tests: 60 passed. Full verify.py: 226 passed, AST 49 files, R2 PASS; existing Starlette/TestClient deprecation warning remains.
- Ollama transport is implemented and tested with MockTransport, not a live model/corpus evaluation. Offline generation only handles explicit definitions; insufficient content is disclosed. Generated references remain UNVERIFIED until later semantic validation.
- No grading, study API/UI, authentication, SQLite, commits/pushes/merges or staging changes. F1/F3, prior Q01/Q02 source/tests and legacy Task Management remain preserved.

## [Unreleased] — 2026-11-11 — F2-Q02 Source Selection & Content Extraction
### Added
- Pure-stdlib `backend/algorithms/f2_source_extraction.py` for extractive definitions, factual prose, examples and ordered procedures, preserving quotes/relative line spans and filtering common headers, decorative text and numeric-only noise.
- `backend/services/f2_source_service.py`: explicit backend access context, exact document selection, stored metadata/chunk provenance checks, immutable passages, overlap deduplication, recovery messages and source-change detection. No shared repository/parser changes.
- `tests/test_f2_source_service.py`: 55 cases including real DocumentService ingestion, same-name version isolation, sparse physical pages, long-document overlap, stale/missing provenance, denied scope, unusable text and stdlib purity.
- `docs/f2/F2-Q02_REPORT.md`: implementation, requirement/test mapping, limits and Q03 handoff.
### Verification and boundaries
- Focused tests: 55 passed. Full `verify.py`: 166 passed, AST 45 files passed, R2 gate passed; existing Starlette/TestClient deprecation warning remains.
- Prepared source spans remain UNVERIFIED and do not guarantee enough supported questions/cards for the requested count. Authentication, generators, semantic validation, API/UI and SQLite remain later work. User manual testing is deferred until the F2-Q0x sequence is complete; automated tests continue per task.
- F1/F3, prior Q01 contracts/tests and legacy Task Management work are retained; no commit/push/merge or staging changes.

## [Unreleased] — 2026-11-11 — F2-Q01 Data Contracts
### Added
- Isolated `backend/core/f2_study_schemas.py`: StudyFormat, SourceRef, StudySourceSelection, QuizOption, QuizQuestion, QuizSet, Flashcard and FlashcardDeck.
- Frozen nested contracts with strict positive counts/locators, single-choice answer-key consistency, unique options/items, exact selected source IDs, version/hash snapshot consistency and Unicode JSON round-trip support. Default requested count is 10; shorter nonempty results remain valid.
- `tests/test_f2_study_schemas.py`: 81 cases covering valid multi-source contracts, malformed inputs, unverified provenance, immutable snapshots, unsafe-copy revalidation and import isolation.
- `docs/f2/F2-Q01_REPORT.md`: model decisions, AC/test mapping, measured verification, limitations and Q02 handoff.
### Verification and boundaries
- Focused tests: 81 passed. Full `verify.py`: 111 passed, AST 42 files passed, R2 stdlib gate passed; existing Starlette/TestClient deprecation warning remains.
- Contracts validate structure only; no generation, semantic grounding, grading, routes, frontend or persistence integration. F1/F3 and the legacy Task Management checkout remain unchanged. No commit/push/merge.

## [Unreleased] — 2026-11-11 — F2-Q00 preparation (documentation only)
### Added
- `docs/f2/F2-Q00_REPORT.md`: frozen Quiz/Flashcards MVP scope, FR2.01–FR2.05 mapping, repository interfaces, isolated branch/worktree, preservation evidence and measured baseline.
- `docs/f2/F2-Q01_TASK_CONTEXT_PACKET.md`: bounded Data Contracts handoff for `f2_study_schemas.py`; no study runtime implemented yet.
### Verification
- Baseline at `da40118`: 30 tests passed, AST 40 files passed, R2 stdlib gate passed; React TypeScript/Vite build passed.
- Legacy F2 Task Management checkout retained with identical branch, HEAD, index, staged/unstaged diffs and 511 tracked/untracked file hashes.

## [Unreleased] Roadmap
- [ ] Tích hợp bộ OCR đa phương thức cục bộ (Surya / PaddleOCR) cho PDF dạng ảnh quét hoàn toàn offline.
- [ ] Mở rộng Graph RAG: Trích xuất Knowledge Graph liên tài liệu (Entity - Relationship) tăng cường cho đối soát nhiều tầng.
- [ ] Hỗ trợ hàng đợi bất đồng bộ phân tán (Celery / Redis) khi ingest tài liệu dung lượng lớn (> 500 trang).

---

## [2.7.0] - 2026-11-10 — Feature 3: Context-Aware Email Reporting & Cryptographic FSM Send Gate
### Added
- **100% Pure-Stdlib Finite State Machine (`backend/algorithms/email_state_machine.py`)**:
  - Khởi tạo 5 trạng thái FSM chuẩn theo Báo cáo Computational Thinking: `DRAFT`, `APPROVED`, `SENT`, `FAILED`, `DELIVERY_UNKNOWN`.
  - Hàm kiểm tra định dạng email chuẩn RFC-5322 độc lập (`validate_rfc5322_email`).
  - Hàm băm mật mã SHA-256 bảo chứng toàn vẹn tuple lõi `(recipients, subject, body)` chuẩn hóa (`compute_draft_hash`).
  - Cổng duyệt ảnh chụp trạng thái có xác nhận người dùng (`approve_snapshot`), phát hiện sửa đổi và khóa mã băm SHA-256.
  - Cổng xác minh tiền phát tán (`verify_and_lock_for_send`), bảo đảm không gửi lặp (duplicate-send rejection) và phát hiện can thiệp nội dung trái phép (tamper detection).
- **Mô hình Dữ liệu & Schemas (`backend/core/schemas.py`)**:
  - `EmailFSMState`: Enum 5 trạng thái FSM.
  - `EmailDraftRecord`: Pydantic model ánh xạ 100% bảng `EmailDraft` trong Database Schema (`id: UUID`, `workspace_id: UUID`, `recipients`, `subject`, `body`, `fsm_state`, `sha256_digest`, `audit_timestamp`, `citations`).
  - `CreateDraftRequest`, `ApproveDraftRequest`: Schemas tiếp nhận yêu cầu API.
- **Tầng Lưu trữ Nháp & Đối soát (`backend/repositories/draft_repository.py`)**:
  - Hỗ trợ lưu trữ in-memory đầy đủ CRUD (`save`, `get`, `list_by_workspace`, `list_all`, `delete`, `clear`).
  - Tự động sinh khóa chính `UUID` (chuẩn `uuid.uuid4`) và cập nhật nhãn thời gian đối soát `audit_timestamp` UTC.
- **Dịch vụ Email Phân luồng Nghiệp vụ (`backend/services/email_service.py`)**:
  - `create_draft`: Khởi tạo bản nháp với trạng thái ban đầu `DRAFT`.
  - `approve_draft_snapshot`: Phê duyệt snapshot, ghi nhận mã SHA-256 digest và chuyển trạng thái sang `APPROVED`.
  - `dispatch_email`: Xác thực điều kiện tiên quyết trước khi gửi; xử lý chế độ Mock Mode và gửi thực qua Gmail SMTP (STARTTLS port 587); tự động bắt lỗi `SMTPAuthenticationError` (`FAILED`), `socket.timeout` / `SMTPServerDisconnected` (`DELIVERY_UNKNOWN` - không tự động retry theo NFR-04).
- **FastAPI REST Endpoints (`backend/api/email_routes.py`)**:
  - `POST /api/email/draft`: Tạo mới bản nháp email.
  - `POST /api/email/{draft_id}/approve`: Duyệt snapshot và khóa mã băm.
  - `POST /api/email/{draft_id}/send`: Gửi email và cập nhật biên lai kết quả.
  - `GET /api/email/audit-log`: Truy vấn lịch sử đối soát và trạng thái gửi theo workspace.
- **Bộ Kiểm thử Tự động Toàn diện (`tests/test_feature3_email_reporting.py`)**:
  - 10 test case bao phủ 100% luồng FSM, tính cô lập stdlib, chống can thiệp SHA-256, chống gửi trùng lặp, giả lập lỗi SMTP timeout và API workflow (nâng tổng số test case hệ thống lên 30/30 PASSED).

---

## [2.6.1] - 2026-11-03 — Dynamic Natural Language Target Resolution & Robust Gemini Live Fallback
### Added
- **Natural Language Summary Target Resolution (`resolve_summary_target` trong `qa_service.py`)**:
  - Bóc tách mục tiêu tóm tắt từ câu hỏi tự nhiên: hỗ trợ tên file bỏ đuôi mở rộng (stem matching như `team_8_proposal` khớp `Team_8_Proposal.pdf`), chuẩn hóa dấu cách và gạch dưới (`team 8 proposal` khớp `Team_8_Proposal`).
  - Tự động ưu tiên tài liệu đang được tick chọn trong Document Library (`selected_doc_ids`) cho các câu hỏi tổng quan ("tóm tắt tài liệu này", "tóm tắt file vừa chọn").
  - Bổ sung bài kiểm thử `test_13_resolve_summary_target_stem_and_selection` và `test_14_frontend_state_initialization` (20/20 tests PASSED).

### Fixed
- **Khắc phục Lỗi NameError `settings` trong `frontend/state.py`**: Bổ sung `from backend.core.config import settings` và tham số mặc định cho `ollama_online()`, giúp Streamlit khởi chạy mượt mà ngay lần đầu.
- **Khắc phục Lỗi Tóm tắt Nhầm File (`Project_Brief.pdf`)**: Giải quyết triệt để lỗi người dùng yêu cầu *"Tóm tắt file Team_8_proposal ấy"* nhưng hệ thống lại tóm tắt `Project_Brief.pdf` do không tìm thấy đuôi `.pdf` trong câu hỏi và mặc định lấy file đầu tiên.
- **Tự động Kích hoạt AI Engine trong Streamlit (`frontend/state.py`)**: Sửa lỗi giao diện luôn mặc định ở chế độ `"offline"` (Mock Engine). Giờ đây tự động phát hiện `GEMINI_API_KEY` để chọn ngay `"gemini"`, hoặc nhận diện Ollama đang chạy để chọn `"ollama"`.
- **Khắc phục Lỗi 404 Google Gemini API (`backend/providers/llm_provider.py`)**: Chuyển sang mô hình chính thức hoạt động ổn định `gemini-flash-lite-latest` kèm cơ chế multi-model fallback tự động.
- **Cải tiến Trả lời khi không trúng Intent Tóm tắt**: Không còn in thô mã định dạng chunk khi ở chế độ offline, hỗ trợ câu trả lời tự nhiên, có cấu trúc rõ ràng.

---


## [2.6.0] - 2026-11-03 — NotebookLM-Grade Evidence Q&A & Complete Document Summarization
### Added
- **Tóm tắt Tài liệu Toàn diện chuẩn NotebookLM (`summarize_document`)**: Tạo bản tóm tắt phân cấp 4 phần chuyên nghiệp (Executive Briefing, Core Themes kèm nhãn nguồn trang, Quantitative Metrics & Deadlines, Actionable Takeaways) và sinh trích dẫn trích lục đa trang cho phép click soi chiếu tức thì.
- **Tô sáng Trích dẫn Nhiều dòng (Multi-line Citation Highlighting)**: Cải tiến `highlight_evidence_in_page()` xử lý span trích dẫn trải dài qua nhiều dòng vật lý mà không làm rách thẻ HTML.
- **Fuzzy Doc ID & Extension Resolver**: `citation_verifier.py` và `workspace_repository.py` hỗ trợ đối soát linh hoạt tên file không phân biệt hoa thường và tự động bù đuôi `.pdf`/`.txt`.
- **Adaptive Top-K & Page Diversity**: Tự động tăng `top_k = 5` khi câu hỏi mang tính tổng quan, bao quát đa dạng các trang khác nhau thay vì dồn cục vào 1 trang.
- **Mở rộng Bộ Kiểm Thử (18/18 Tests PASSED)**: Bổ sung `test_10_multiline_evidence_highlighting`, `test_11_notebooklm_comprehensive_document_summary`, `test_12_flexible_doc_id_matching`.

### Fixed
- **Khắc phục Lỗi Xếp hạng Pinpoint Reranker**: Áp dụng Relevance Gate và sắp xếp theo `(x.score, x.pinpoint_score, x.rrf_score)` để đảm bảo các chunk có liên quan từ vựng/ngữ nghĩa luôn được ưu tiên, ngăn chặn chunk rác chiếm top chỉ vì vô tình chứa số.
- **Khử trùng lặp dòng gối đầu trong `build_page_lookup()`**: Tự động deduplicate các dòng overlap 2 dòng giữa các chunk kề nhau khi ghép nối toàn văn trang gốc cho Evidence Viewer.
- **Ngăn chặn Hiện tượng Trôi Chủ đề (Topic Drift) trong `expand_contextual_query()`**: Bỏ nhầm các từ hỏi (*khi nào, ở đâu*) ra khỏi danh sách đại từ tham chiếu, chỉ mở rộng ngữ cảnh khi câu hỏi thực sự chứa đại từ anaphoric (*nó, đó, ở trên, còn...*) hoặc là câu cụt.
- **Granular Claim Statement Parsing trong `llm_provider.py`**: Gán từng câu khẳng định cụ thể cho từng trích dẫn trong mảng `citations`, khắc phục tình trạng 1 trích dẫn sai làm báo cờ đỏ toàn bộ câu trả lời.

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
