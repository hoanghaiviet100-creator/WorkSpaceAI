## [2.9.7] - 2026-11-09 — Detailed source-grounded explanations
- Detailed Q&A has a dedicated prompt: explanations belong in visible verified claim paragraphs, not only the discarded answer field. Do not anchor generation to the old assistant wording; resolved user topic remains. Structured Ollama detail output allows 3–5 explanatory paragraphs or an empty evidence response.
- Elaborations can read an entire short retrieved document set when within 10 chunks/4500 characters, still respecting selected sources. Longer libraries retain bounded retrieval.
- Detail calls allow up to 2048 output tokens/120s; normal calls remain 1024/60s. Context stays 4096, four CPU threads, one concurrent model request. Frontend chat wait 150s, other calls 60s. Longer calls may increase active GPU time, not hardware power limits.
- Validation: production images built; Docker verify.py passed 94 tests, 50 syntax checks and purity gate; 49 frontend tests passed. Live supplied socket follow-up expanded from a 529-character prior answer to 738 characters in three explanatory paragraphs, 23s; two bad citations were rejected. This is evidence of improvement on one case, not a guarantee of exhaustive detail or semantic correctness. Model unloaded after test.

## [2.9.6] - 2026-11-09 — Follow-up elaboration context
- Recognize subject-free requests such as “mô tả một cách chi tiết”; skip prior elaboration-only turns to find the substantive user topic. New explicitly named topics are preserved.
- Send the resolved topic to both retrieval and model generation; stop overweighting vague current wording during retrieval. No schema changes or relaxation of source selection/citation checks.
- Validation: verify.py in Docker passed 50 syntax checks, purity gate and 91 tests (8 follow-up regressions). Live request with the screenshot wording plus supplied socket conversation context returned five claims passing citation matching and no rejected claims. Actual preceding browser conversation was not read; this is a representative reproduction. Sampled GPU temperature during the short call was 73 C; no load loop run.

## [2.9.5] - 2026-11-09 — NVIDIA laptop Ollama profile
- Enabled GPU access for Ollama, four CPU cores, 10 GB container memory, one loaded model/parallel request, queue four, 60s idle unload. Provider context 4096, output at most 1024 tokens, four CPU threads. No hardware power/thermal settings changed.
- Local runtime switched from qwen2.5:1.5b to qwen2.5:7b Q4_K_M after successful 4.7 GB download; smaller model retained for rollback.
- Validation: Docker build and verify.py passed (50 syntax checks, purity gate, 83 tests). Live socket-document query returned two verified citations, no rejected citations, 55.1s cold request; Ollama ps reported 100% GPU and 4096 context. Sampled GPU temperatures 58–59 C during first 24s, ~6.5 GB total VRAM; post-request 57 C. No full-run peak/CPU/mainboard measurements or hardware safety guarantee. Model explicitly unloaded after short test.

## [2.9.4] - 2026-11-09 — Ollama grounding and routing corrections
- Match action keywords at word boundaries; document questions about thư viện/sendall/iterable no longer trigger email or reconciliation by substring.
- Ollama structured Q&A now requires explicit valid citation fields; missing/malformed citations cannot be replaced with invented source coordinates. Ollama summaries now use the citation verifier rather than pre-marking summaries as verified.
- Validation: Docker verify.py passed 50 syntax checks, purity gate and 83 tests (9 new regressions). Live socket-document query changed from erroneous recipient-email clarification to QA; model invented excerpt was rejected. Qwen 1.5B still has quality limitations; quote verification does not prove semantic entailment. No model upgrade performed.

## [2.9.3] - 2026-11-09 — React Docker deployment
- Added multi-stage React build and Nginx /api proxy; backend defaults to API only. UI localhost:8501, API localhost:8001; all published ports loopback-only.
- Persist backend libraries through .workspace_data bind mount; retain Ollama named volume. Exclude browser build caches and frontend environment files from context. Document origin-specific browser storage and safe shutdown.
- Validation: Docker images built; compose started; UI HTTP 200 and proxied runtime ready. python verify.py in Docker passed 49 syntax checks, purity gate and 74 tests. Existing environment remains offline-only; no Ollama models installed. Local Python lacks test dependencies.

# WorkspaceAI — Changelog & Roadmap

Tất cả các thay đổi và nâng cấp quan trọng của dự án **WorkspaceAI (CSC10014 Track C - Intelligent Document Workspace)** được ghi nhận tại đây theo chuẩn [Keep a Changelog](https://keepachangelog.com/).

---

## [2.9.2] - 2026-11-09 — Restored previous palette
### Reverted
- At the user's request, removed the trial `dark-theme.css` override and its import. Restored the pre-trial neutral black/gray dark surfaces and orange accent across all components, including Home and Kanban. Light mode, geometry, behavior, stored records and Offline settings are retained.
- Restored the current color documentation; the 2.9.1 entry records the discarded experiment only.
### Validation
- Production build and `python verify.py` (49 syntax checks, R2 purity, 74 backend tests) pass. Restore snapshots are compared to the pre-trial palette/layout under `frontend/.taste-skill/dark-v11/restored/`.

---

## [2.9.1] - 2026-11-09 — Reference component palette on black
### Changed
- Added `frontend/src/dark-theme.css`, imported after all component styles and scoped exclusively to `data-theme="dark"`. Kept the overall page/notebook frame black and the chat/expanded board near-black, per the user's clarification. Components use the supplied #2D3250 / #424769 / #676F9D family with #F9B17A peach actions.
- Applied consistent roles to Sources, Studio, source selection, chat input/user bubbles, Kanban, forms/dialogs, Home and sign-in preview. Strengthened secondary text/control tones for contrast; kept semantic warning/error/success and stable workspace identity colors meaningful. Home's dark banner/rule now use the same component palette.
- Retained Be Vietnam Pro, all geometry/interactions, data and Offline configuration. Light-theme selectors/tokens are unchanged; no API/schema/dependency changes.
### Validation
- Production build, 49 frontend tests and `python verify.py` (49 syntax checks, R2 purity, 74 backend tests) pass. Palette source lint: 0 FAIL / 0 WARN. Before/after production captures, dark/light layout comparisons and nine AA contrast pairs are recorded under `frontend/.taste-skill/dark-v11/`.

---

## [2.9.0] - 2026-11-09 — One reviewed Kanban per workspace
### Added
- Studio Kanban summary with per-column counts, nearest open deadline, completion progress and an expanded workspace board. One board object per workspace; no board directory or second-board action.
- Empty → generating/error/retry → editable preview → explicit confirmation. Preview supports column/card selection, rename, edit and removal. Additional suggestions append reviewed cards only, reject duplicates and never overwrite edited cards. Confirmation adds a clickable event to the one shared conversation.
- Quick cards with Enter; native mouse drag, touch-handle drag and keyboard movement; column reorder/add/rename/safe deletion; card detail with task/event kind, dates, soft labels, priority, checklist, sources and notes. Duplicate, delete with targeted undo, search and three filters are available. Changes persist with actual saved/unsaved feedback.
- Explicit eight-card sample preview and deterministic Offline suggestions from selected document text, existing tasks and recent non-sample conversation. Loading/error states are real; no cloud model is enabled. Dates need an explicit day/month/year and are checked before use.
### Integration
- Board cards retain task IDs and synchronize title, description, deadline, status and completion with existing Tasks while preserving owner/requirement fields. Removed cards archive their corresponding task for undo. Board metadata remains a UI extension in existing workspace storage; no SQL schema/API changes.
- Preserved Sources, shared chat, Plan/Email tools, existing result history, Requirements/Reconciliation and theme behavior. Expanded board adapts to desktop, tablet horizontal scrolling and single-lane mobile with indicators. Task creation/update remains under user control.
### Validation
- Production build, 49 frontend contracts, 36 isolated Kanban browser checks, 16 native file chooser regression checks, and `python verify.py` (49 syntax checks, R2 purity, 74 backend tests) pass. Browser checks include native pointer drag, touch drag, keyboard movement, safe column deletion, undo, persistence, previews and scoped source reads; no model/email calls.
- UX analysis, ASCII wireframes, design tokens, usage and remaining backend limitations: `frontend/KANBAN_DESIGN.md`. Screenshots, raw style inspection and documented existing-theme exceptions: `frontend/.taste-skill/kanban-v10/`.

---

## [2.8.3] - 2026-11-09 — Native source file chooser
### Fixed
- Replaced the hidden file input outside the upload dialog and its programmatic click with a native file control inside the active dialog. Pointer and keyboard activation now reach the file chooser directly; appearance and document processing are unchanged.
- Original-file re-upload uses the same dialog, identifies the source to restore and restricts selection to one file. Normal imports retain multiple-file selection. Cancellation, choosing the same file again and retrying an upload remain supported.
### Validation
- Added `frontend/tests/browser-file-picker.mjs` with an isolated fixture server: 16 checks cover actual native chooser events, keyboard activation, uploads, cancellation, re-upload, retry, source selection, both themes and 320/390px phone targets. The integrated browser also opened the chooser and uploaded two generated files on a disposable origin.
- Production build, 42 frontend tests and `python verify.py` (49 syntax checks, R2 purity, 74 backend tests) pass. Evidence: `frontend/.taste-skill/file-picker-v9/`. No backend, model configuration or user workspace data changes in this fix.

---

## [2.8.2] - 2026-11-09 — Reference light palette
### Changed
- Added `light-theme.css`, scoped entirely to `data-theme="light"`: near-white lavender surfaces, a gentle rose/lavender chat field, peach/coral primary actions, warm citation/selection accents, muted plum secondary icons and a peach/pink composer edge. Shared light tokens also cover dialogs, Home and its existing brand banner.
- Kept all layouts, typography, functions, records and dark-mode colors unchanged. No new modules, dependencies or API behavior.
### Validation
- TypeScript/Vite production build, 42 frontend tests and `python verify.py` (49 Python syntax checks, R2 purity, 74 backend tests) pass. Isolated browser measurements cover six light viewports, unchanged dark tokens, Home/dialog consistency and nine AA text color pairs; details in `frontend/.taste-skill/light-v8/`.

---

## [2.8.1] - 2026-11-09 — Focused chat composition and automatic responsive layout
### Changed
- Restyled the chat frame from the supplied visual reference: centered empty-state greeting and existing prompt pills, a spacious rounded composer and orange send action. Retained Be Vietnam Pro, the orange/neutral palette, one workspace conversation, Sources and the two Studio tools. Added none of the reference's AI Agent/Report/Workflow/Recommended modules.
- Populated conversations keep the input at the bottom. Empty chat starts at its greeting even in a short viewport, while existing conversations retain latest-message scrolling. Source selection, citations, notes, Plan and Email behavior are unchanged.
### Removed
- Removed the duplicate Add source button from the chat intro; the Sources panel remains the upload entry.
- Removed Desktop/Phone preview controls, the device-preview modal/component, preview iframe messaging/state and their CSS. Layout now follows the real viewport breakpoints; theme controls and cross-tab workspace storage synchronization remain.
### Validation
- Production TypeScript/Vite build, 42 frontend contracts, `python verify.py` (49 syntax checks, R2 purity, 74 backend tests), and 61 production browser checks pass. App inspector: 0 FAIL on its standard light/dark presets. Responsive/functional screenshots and defended warnings: `frontend/.taste-skill/chat-v7/`.

---

## [2.8.0] - 2026-11-09 — One-conversation notebook workspace
### Changed
- Workspace now uses Sources / shared Chat / Studio with a compact renameable header, independent scrolling, collapsible sides, tablet secondary-panel switching and mobile bottom navigation. Retained orange/neutral branding and the bundled Be Vietnam Pro; added quiet light/dark pane surfaces and keyboard/touch states.
- Merged old conversations chronologically into one canonical conversation per workspace. Preserved original sessions and pre-migration backup; imported prior Plan/Email results into persistent Studio snapshots. Opening legacy links never creates another conversation.
- Studio has exactly Plan and Email tools, configuration forms, actual asynchronous states, error/retry, newest-first output history, detail/edit/copy/export/rename/delete and references in the shared transcript. Existing Tasks/Requirements/Reconciliation and guarded Email editors remain accessible. Creating an Email never dispatches it.
- Guarded library reads against stale responses after new uploads; collapsed panels keep uploads/generation mounted. Saved light/dark preferences apply on workspace deep links before opening Display.
- Sources supports upload/drop, public URL/text imports, search/type/sort, checkbox selection, rename/delete menus and readable empty/error states. Sample/preview sources clearly require original upload before use. Citation chips preview the stored quote and open highlighted extracted lines; saved notes and feedback persist.
- Removed the two reviewed New workspace buttons from the Landing header and closing banner. Kept the hero create action and workspace history.
### Backend support
- Added bounded DOCX/PPTX extraction, public HTTP(S) imports with private-address/redirect checks, stable-ID rename and extracted-page endpoints. Optional source URL persists with library metadata. No algorithm or schema-table changes.
- Fixed ID/filename alias collisions after rename: page lookup, selection, retrieval and delete stay scoped to the intended document; reusing a former filename cannot overwrite the original document.
- Explicit Studio routing remains behind existing guards. Plan forces deterministic Offline processing per request, including when Feature 1 is configured for Gemini. No new dependency or cloud engine activation.
### Documentation and validation
- Updated frontend startup/usage README, added `frontend/WORKSPACE_DESIGN.md` (UX analysis, three wireframes, tokens, decisions, limits and next steps) and current codebase map.
- Validation: 74 backend tests / R2 purity / 49 Python syntax checks; 42 frontend contracts; production build; 49 production browser checks. App inspection has 0 FAIL in both themes (defended warnings documented). Records and screenshots: `frontend/.taste-skill/workspace-v6/`.

---

## [2.7.7] - 2026-11-08 — Landing reference and saved workspace history
### Changed
- Made `Landing.tsx` the Home entry, following the user's new supplied screenshot: compact product navigation, four-line hero, orange create action, horizontal brand rule, gradient closing action and academic footer. Retained the existing brand colors, local typeface and working workspace screens.
- Added the actual workspace history immediately below the hero create action. Every retained workspace is shown with its stable identity, source/conversation counts and latest real activity. A row opens that workspace's latest conversation in Chat.
- All three New workspace buttons share the existing create flow. How it works opens factual workflow help; compact appearance controls and the existing sign-in preview remain available. Header/history/banner stack for phone screens.

### Added
- `workspaceHistory(workspaces)` orders copies of records by actual workspace/conversation timestamps, preserves stored order and handles missing dates/threads. One regression covers ordering, destination and missing metadata.

### Validation
- 38 frontend contracts, TypeScript/production build and 18 isolated landing browser checks pass. `python verify.py`: 47 syntax checks, R2 purity and 63 backend tests pass.
- Reference exceptions, screenshots and final visual measurements are recorded under `frontend/.taste-skill/landing-v1/`. No user workspace was removed or test workspace added to the live profile; browser creation checks use an isolated origin/profile. Offline settings remain unchanged.

---

## [2.7.6] - 2026-11-08 — Reference-led Home dashboard
### Changed
- Reorganized Home around the user's supplied reference: labelled left navigation and workspace directory, four compact metrics above a central research workbench, and a right rail for task deadlines, workspace completion and recent conversations. Kept the existing orange/neutral palette, bundled typeface, stored workspace identities and working screens.
- Overview and Conversations are separate Home views. Global search opens the existing searchable history; scoping recalculates the metrics, saved answer and context rail together. Unscoped task/email actions ask which workspace to open.
- Home shows an excerpt of an actual saved response and explicitly labels sample conversations. A typed question creates a new chat with an unsent `Thread.composerDraft`; Chat restores that text and clears the saved draft on explicit submission. Home never submits an AI request automatically.
- Mobile folds navigation into the workspace menu, uses two metric columns and puts the question composer before the saved-answer preview. The secondary rail follows the main region on tablet/phone.

### Added
- `HomeOverview.tsx`, scoped `home-dashboard.css` and `dashboardData(workspaces, scope?, now?)`. Counts and progress exclude archived tasks; deadline alerts exclude completed, missing and invalid dates and use the Bangkok calendar day.
- Two frontend regressions for scoped counts/deadlines and empty-state honesty. Updated the Vietnamese frontend README with the current Home flow; its Windows startup instructions remain intact.

### Validation
- `python verify.py`: 47 Python syntax checks, R2 purity and 63 backend tests pass. Frontend contracts: 37 pass; TypeScript and production build pass.
- Production screenshots, responsive/browser checks and the reference/decision record are in `frontend/.taste-skill/home-v5/`. No new dependency, database change or cloud engine activation.

---

## [2.7.5] - 2026-11-07 — A focused research home
### Changed
- Rebuilt Home using the taste-skill app workflow and the **Editorial greeting** direction (seed 1484780849): a centred 1100px/12-column open plane, restrained tonal surfaces, bundled Be Vietnam Pro and a single create action. Removed the promotional gradient banner and duplicated grouped-history columns.
- Desktop has a workspace directory and chronological conversation list. Workspace selection scopes the list; **Open workspace** opens its working view. Every conversation resumes its exact chat, including Tasks/Email conversations whose last visited view was a board/editor.
- The overview shows four recent conversations with an explicit full-history action. Titles get the main reading width, workspace/feature metadata sit underneath, and a source trail names files from the last exchange rather than today's file selection. Search supports Vietnamese without accents; scope, feature counts and empty/reset states use actual records.
- Replaced the crowded theme/preview toolbar with one accessible **Display** control. Phone preview remains available on desktop; phones expose theme controls without a nested device preview. Kept the existing account flow.
- Unified the brand accent to `#E85002` in both themes. Workspace identity is separate from task status and uses stable, locally persisted colors throughout Home and the active workspace breadcrumb.

### Added
- Optional UI-only `Workspace.color`, balanced assignment from six named colors, preserved across reload, new-workspace creation, theme changes and device-preview synchronization. No SQL or API contract changes.
- Keyboard-operable conversation menus, explicit delete confirmation, responsive workspace selection, source-file tooltips and 320px layout/touch refinements.
- Six frontend regressions cover stable/balanced colors, chronological history, combined Vietnamese search/filtering, historical source trails and Bangkok recency labels.

### Validation
- `python verify.py`: 47 syntax checks, R2 purity and 63 backend tests pass. Frontend contracts: 35 pass; TypeScript and production build pass.
- Skill production inspection covers light/dark at 1440/768/390px; real-user browser checks additionally cover 320px, 5 distinct retained workspace colors, all 15 conversations, filters/reset, menus/cancel, create-form validation, device preview and resuming the exact chat. Design rationale, screenshots and findings are in `frontend/.taste-skill/home-v4/`.
- Uploaded evidence and selections remain durable; the local runtime remains offline. Existing sample conversations are retained, and Home does not invent AI verification or new activity dates.

---

## [2.7.4] - 2026-11-07 — Retain uploaded evidence and reopen the latest chat
### Fixed
- Uploaded document metadata, indexed text, citation coordinates, versions and selected-file states now survive backend restarts through per-workspace local snapshots. The earlier memory-only library left visible uploads disabled as **Needs upload** after relaunching the app.
- Opening a previous conversation no longer overwrites the current workspace selection with the files used in its last answer.
- Conversations open at their latest message on initial load, thread changes and returning from Tasks/Email. Scrolling targets the chat pane directly and follows font/composer layout changes while the reader is at the bottom, without pulling them away from older answers.

### Added
- Atomic, validated local library storage under ignored `.workspace_data/libraries/`. Search indexes rebuild from restored passages; clearing selections and deleting the last file remain persistent. Default sample data is seeded only when no saved library exists.
- Nine backend regression cases cover restart/retrieval, selection, CSV versions/deduplication, deletion, interrupted writes, invalid snapshots and workspace isolation. Raw PDF binaries and email drafts are not added to library snapshots.

### Validation
- `python verify.py`: 47 Python syntax checks, R2 stdlib purity and all 63 backend tests pass. Frontend contracts: 29 pass; TypeScript and production build pass.
- Restored both original HAHO PDFs by verified content hashes. Live restart retained 451 passages and the selected subset; browser checks cover individual/all/clear selection, reload, navigation and latest-message positioning. Runtime remains offline-only with no Gemini key configured.

---

## [2.7.3] - 2026-11-06 — Gemini for Feature 1 only
### Added
- Feature 1 setup in the existing Engine modal: masked API key input, explicit model choice (default `gemini-3.5-flash-lite`, optional `gemini-3.8-flash`), optional local persistence and **Use Offline**. The local setup request explicitly enables document Q&A/summaries; model discovery does not generate content or establish free-quota eligibility.
- Runtime status reports `gemini_scope`, per-feature engines and model options without credentials. Local-only `POST /api/runtime/offline` switches generation off immediately and can retain that choice for the next launch.
- Sixteen regression cases cover scoped calls, selected-file evidence, validated summary citations, zero-call Tasks/Email/empty selection, quota/access errors, model pinning, explicit activation, offline switching and pasted-key normalization. All Google responses in these tests are mocked.

### Changed
- Gemini sends one generation request to the selected model. Quota, access and network errors produce a clear chat error; they do not switch models or silently substitute an offline answer.
- Gemini Q&A requires explicit claim/quote/page/line data. Gemini summaries use at most twelve representative passages and run generated claims through the existing citation verifier, excluding unsupported claims. This verifies source quotations; it is not a proof of semantic correctness or full-document coverage.
- Engine labels follow the active feature: Ask uses its configured engine; Tasks/Email show local processing when Gemini is active. Summary scope appears above returned findings.
- The launcher defaults to `auto`, honoring the saved offline/Gemini choice. `-Engine offline` remains an explicit override. Keys stay outside frontend assets, browser storage and source control.
- Key entry accepts surrounding quotes or a pasted `GEMINI_API_KEY=` assignment; malformed entries receive instructions to copy the complete value without exposing it.

### Validation
- `python verify.py`: syntax checks for 45 Python files, R2 stdlib purity gate and all 54 backend tests pass. Frontend contract tests: 29 pass; production build passes.
- Applied locally while restoring the two original HAHO PDFs and workspace selection states. Model discovery accepted the user-entered key, but their live questions returned HTTP 403; AI Studio explicitly shows **Free tier unavailable** for the project. Discovery success does not establish generation access. No billing changes were made.
- At the user's subsequent request, restored all features to offline-only, cleared the saved API key from local configuration and restarted the owned backend to discard its in-memory credential. Final runtime reports `gemini_configured=false`, no active model, and all three feature engines offline. Document files/selections were restored; the disabled Gemini integration remains available for a future eligible project.

---

## [2.7.2] - 2026-11-06 — File selection in every workspace
### Fixed
- Removed the frontend connection gate that restricted real document processing to the sample `midterm` workspace. Custom workspaces now ingest uploads and support individual selection, select-all, clear and selected-document Q&A.
- Document, chat and email requests carry `X-Workspace-ID`. The backend keeps independent document/search/selection and email-draft repositories for each workspace; no-header clients retain the original default library. Custom reconciliation no longer returns the sample workspace's requirements.
- Previously staged previews merge with processed server files by content hash, preserving file metadata, requirement/evidence links and draft attachment references without duplicating rows. Matching names alone never replace different file bytes. Missing server documents remain visible as **Needs upload**, with a **Re-upload to process** action.
- Preserved the existing layout, themes and offline-only policy. Updated the launcher and environment example to remove the obsolete single-workspace binding.

### Validation
- `python verify.py`: 44 Python syntax checks, R2 stdlib purity gate and all 38 backend tests pass, including six workspace-isolation tests.
- Frontend: 28 contract/migration/API tests pass; TypeScript and production build pass.
- Verified the real HAHO workspace in the browser: both original PDFs are processed, individual/bulk/clear selection works, and selection survives a reload. Local API verification returns five cited findings from only the selected PDF and abstains when no sources are selected. No external AI requests were made.

---

## [2.7.1] - 2026-11-06 — Working local document lookup and offline-only setup
### Added
- Windows launchers `Start-Workspace.cmd` / `Start-Workspace.ps1` start the real FastAPI backend and React frontend locally, with hidden service processes, readiness checks and local logs. Offline is the default engine; an existing service must report the offline guard before the launcher declares success.
- `GET /api/runtime` reports the active engine without exposing secrets. Optional local Gemini setup validates available models, saves only on user submission and uses API-key headers rather than query strings.
- `WORKSPACE_OFFLINE_ONLY` rejects cloud configuration and stops Gemini generation before network access. This workspace is configured offline-only; no Google billing or API-key setup is required.
- Engine settings in Chat show **Offline**, explain document lookup and preserve unsent questions. The settings modal uses a portal with isolated form submission. Runtime settings sync to the composer caption.
- Automatic server-library sync and an end-to-end test that uploads an actual TXT file to a real isolated FastAPI server, asks about it, checks citations, and checks abstention with no selected files.

### Validation
- `python verify.py`: 41 Python files pass syntax, the R2 stdlib purity gate passes, and all 32 backend tests pass, including cloud-request blocking and credential handling.
- Frontend contract tests: 23 passing; production build passing.
- Offline browser integration: 17 checks passing in both themes from 320px to 1440px. No external AI calls or real emails were used in verification.

---

## [2.7.0] - 2026-11-06 — React frontend schema alignment
### Added
- Explicit TypeScript contracts for all 12 tables in `database/schema.sql`, with adapters separating UI preferences from SQL fields.
- Requirements management inside the existing Tasks view: document/source reference, official deadline, mandatory flag, keywords, linked tasks and requirement/task JSON export.
- Reconciliation view with server calculation, reference date, requirement coverage, risk, owners, date conflicts and locally retained run history. Existing Python result names are translated to SQL enums; no R2 calculations moved into JavaScript.
- Optional integration with the existing document, chat and email routes, enabled through frontend environment configuration and a development `/api` proxy. The single backend library is bound explicitly to one local workspace.
- Citation metadata/verification details and original numbered text lines when present; local TXT/MD/CSV previews include content hashes, size and versioning.
- Email attachment selection, full SHA-256 review snapshots, server state/audit presentation and persistent locks for pending/uncertain submissions.

### Changed
- Tasks now use `TODO`, `IN_PROGRESS`, `REVIEW`, `DONE`, with requirement mapping, completion percentage and source references. Previous workflow labels and archive data are retained as local metadata.
- Session engine preferences are separate from action routing; live engines remain server-managed under the current API contract.
- New uploads match backend formats: text PDF, TXT, MD and CSV. Existing sample records remain available for reference; live answers use selected server documents.
- Existing browser records are migrated in place with a one-time backup when storage permits. The orange/black/white identity, Be Vietnam Pro, navigation, chat geometry and responsive shell are retained.

### Fixed
- Sample passages no longer imply server verification. Live findings exclude rejected and out-of-scope claims and show grounding scores only when returned by the server.
- Local review no longer fabricates approval, HMAC, audit history or successful email delivery. Mock dispatch is labeled explicitly, while unknown delivery outcomes block automatic retries.
- Requirements/tasks edits, unsupported CC/attachment sending, original-page retrieval and server audit/status lookup are described according to actual API availability.

### Validation
- Frontend contract/migration/API tests: 23 passing; TypeScript and production build passing.
- Root `python verify.py`: 38 Python syntax checks, R2 stdlib purity gate and all 20 backend tests passing in an isolated verification environment with mock email and offline AI.
- Browser interaction checks: 42 standalone and 45 mock-API checks, covering both themes at 1440/768/390/320px. No real emails were sent.
- App inspections: no failures in either theme; the existing compact metadata type scale is retained to respect the requested design.

---

## [Unreleased] Roadmap
- [ ] Tích hợp bộ OCR đa phương thức cục bộ (Surya / PaddleOCR) cho PDF dạng ảnh quét hoàn toàn offline.
- [ ] Mở rộng Graph RAG: Trích xuất Knowledge Graph liên tài liệu (Entity - Relationship) tăng cường cho đối soát nhiều tầng.
- [ ] Hỗ trợ hàng đợi bất đồng bộ phân tán (Celery / Redis) khi ingest tài liệu dung lượng lớn (> 500 trang).

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

