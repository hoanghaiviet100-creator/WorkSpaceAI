# Detailed Q&A (2026-11-09)
- prompts.requests_detailed_answer(query: str) -> bool selects dedicated detailed prompt with full explanatory claim paragraphs and no assistant-answer anchoring. Ollama detail output uses a JSON schema (3–5 paragraphs or no claims); verification remains downstream.
- QAService.answer_question elaboration expands short retrieved document sets only within 10 chunks/4500 chars; selected-source constraints retained. Detail output cap 2048, read timeout 120s; normal 1024/60s, shared 4096 context/four threads. Frontend request /chat waits 150s. No API fields/signatures changed.

# Follow-up elaboration (2026-11-09)
- is_detail_followup(query: str) -> bool detects subject-free detail requests. expand_contextual_query skips elaboration-only history turns and anchors to a substantive user topic. answer_question passes the expanded topic to both repository.search and generate_grounded_qa. Source filters/verification remain in place; no schema changes. Runtime/browser histories are not persisted by this fix.

# NVIDIA laptop resource profile (2026-11-09)
- Compose Ollama: gpus all, cpus 4, memory 10g, NUM_PARALLEL/MAX_LOADED_MODELS 1, MAX_QUEUE 4, KEEP_ALIVE 60s, CONTEXT_LENGTH 4096. Provider call_ollama uses num_ctx 4096, num_predict 1024, num_thread 4. No API/schema changes; no power/thermal firmware settings changed.

# Ollama grounding corrections (2026-11-09)
- Router action keywords use word boundaries; bare thư is not email intent.
- LLMProvider.generate_grounded_qa validates Ollama citation structure using the strict model branch; absent citations return no claims. QAService.summarize_document routes Ollama through representative-excerpt generation and verify_citations, like Gemini. Existing signatures/schema unchanged. Quote matching still does not establish semantic entailment.

# Docker deployment (2026-11-09)
- frontend/Dockerfile builds React with pnpm; Nginx serves port 8501 and forwards /api unchanged to app:8000. Backend entrypoint defaults to API only. Compose binds ports to loopback and mounts .workspace_data for document persistence. Ollama models use the existing named volume. Browser UI storage remains origin-specific. No public API/schema changes.

# WorkspaceAI System Codebase Map (v2.5)
> Rapid context reference for AI Agents: Module layout, Pydantic schemas, and public function signatures.

## 1. Architecture & Layer Map

### Restored theme (2026-11-09, 2.9.2)
- User reverted the 2.9.1 palette experiment. `dark-theme.css` and its import are removed. Dark styling again comes from the existing shared/notebook/Kanban styles: neutral black/gray surfaces and orange #E85002 with #FF9A63 accent ink. Light mode and all functions/data remain as before the trial. No API/schema changes.

### Reviewed Kanban (2026-11-09, 2.9.0)
- `Workspace.kanban?: KanbanBoard` is one board, never a list. `Message.kanbanEvent?: {boardId, count, initial}` renders a clickable event in the canonical chat. Both are local UI storage extensions; the 12-table SQL schema and backend APIs are unchanged.
- `kanban-model.ts`: `KanbanColumn{id,title,status}`, `KanbanCard{id,taskId,columnId,title,description,kind,startDate,dueDate,priority,labels,checklist,sourceIds,notes,origin,createdAt,updatedAt}`, `KanbanBoard{id,name,columns,cards,createdAt,updatedAt,initialSuggestionConfirmedAt}`, `KanbanProposal{id,boardId?,name,mode,columns,cards,engine,contextNote,sourceIds}`. Proposal selections are transient component state until confirmation.
- Public pure operations: `workspaceBoard(workspace): KanbanBoard|undefined`, `saveBoard(workspace,board): Workspace`, `selectedProposal(proposal)`, `confirmProposal(workspace,proposal): Workspace`, `moveCard(board,cardId,columnId,beforeId?): KanbanBoard`, `reorderColumn(board,columnId,beforeId?)`, `boardSummary(board)`, `dueState(card,done,today?)`, `explicitDate(text)`, `validDate(value)` and local-day/date/ID/card helpers. Initial confirmation rejects an existing board; appends check board identity, current duplicate titles/task IDs and surviving columns. User edits are retained.
- `saveBoard` synchronizes only linked Tasks, retaining owner/mapped requirement/source fields and unrelated tasks. Deletion archives represented tasks; targeted undo restores the card/task without reverting later edits. `workspaceBoard` reflects title/description/due/status/archived edits made through existing Tasks. New legacy Tasks are offered in the next reviewed suggestion batch.
- `suggestKanban(workspace,demo=false,progress?)` in `kanban-service.ts` is deterministic Offline. Reads existing tasks, selected non-sample source text (scoped `getDocumentPage` when uncached, at most eight source reads), and the last 20 non-sample chat exchanges. Extracts explicit dates only. Demo is explicit, labelled, three columns/eight cards; no model request or credential handling. No-context/source-read failures surface for retry.
- `Kanban.tsx` owns the full state machine, editable preview, actual storage feedback, rich editor, filters, safe column deletion, targeted card undo and native mouse/touch/keyboard movement. `KanbanSummary` integrates with Studio. `NotebookWorkspace` owns expansion state outside hidden panels; Chat events reopen the same board. Existing Plan/Email outputs and Tasks/Requirements/Reconciliation remain accessible.
- `kanban.css` follows existing Be Vietnam Pro/theme tokens. Desktop equal lanes with a readability minimum; tablet 304px lanes; phone full lanes with snap scrolling/indicators and 44px targets. Design/limits: `frontend/KANBAN_DESIGN.md`; 49 frontend tests and 36 isolated browser checks; artifacts under `kanban-v10/`.

### Native source picker (2026-11-09, 2.8.3)
- `Sources.tsx` renders the native file input inside its active Add source modal. `.nb-native-file-picker` places the transparent input over the visible label so trusted pointer/keyboard input opens the chooser directly, without an external hidden control or synthetic click. The native input has a minimum 44px target and a visible focus outline.
- Normal imports accept multiple files. The existing re-upload target opens the same dialog in single-file mode, names the original source and disables link/text alternatives until the dialog closes. The existing `upload(files, replacement?)` flow, input reset, selection, deduplication and error/retry behavior remain unchanged. No API/schema/public signature changes.
- `frontend/tests/browser-file-picker.mjs` launches the existing taste browser helper and `tests/support/picker-server.mjs` on a disposable origin. It exercises native chooser events and generated files only; it does not call a model, send email or change live workspace records. Usage and prerequisites are in `frontend/README.md`; evidence is in `frontend/.taste-skill/file-picker-v9/`.

### Light palette (2026-11-09, 2.8.2)
- `main.tsx` imports `light-theme.css` after the shared notebook styles, followed by `kanban.css`. Every light selector begins with `:root[data-theme="light"]`; it overrides shared light tokens and notebook colors without changing dark mode or component state.
- Light roles: lavender canvas #F0ECF6, panel #FCFBFE, soft #F1ECF7, ink #28232F, secondary #6B6274, peach #F78F67, rust #9A4228, plum #825576. Reference-led ambient fields/card tints and composer edge are limited to light mode. Primary action text stays dark for AA contrast on peach.
- No API/type/function changes. Palette screenshots/contrast and dark regression checks: `frontend/.taste-skill/light-v8/`.

### Chat frame iteration (2026-11-09, 2.8.1; current presentation)
- `Chat.tsx` keeps one composer DOM node and the existing request flow. `.nb-chat-welcome` centers the empty greeting, the same three prompt queries as compact pills, and the larger composer. With messages/pending output, the composer returns to the bottom. The empty-view scroll reset preserves the greeting on short screens; nonempty scroll-to-latest behavior remains.
- `notebook.css` styles the chat reference composition using the existing palette/type and book mark; no new reference modules or API capability. The chat Add source duplicate is removed; source count/selection access stays in the composer and uploads stay in Sources.
- `AppTools({compact?: boolean})` now contains only theme selection. `DevicePreview.tsx` and layout-preview callbacks/state/iframe messages/CSS are removed. Real media-query breakpoints determine desktop/tablet/mobile. Normal localStorage cross-tab synchronization, auth return and ThemeRuntime are preserved.
- Iteration artifacts: `frontend/.taste-skill/chat-v7/`; current usage/design rationale: `frontend/WORKSPACE_DESIGN.md`. The historical preview descriptions below are superseded by this section.

### Notebook workspace (2026-11-09, 2.8.0; current UI)
- `App.tsx` keeps Landing as Home and routes every workspace to `NotebookWorkspace.tsx`: compact header, Sources left, **one canonical chat** center, Studio right. No conversation directory in a workspace. Desktop rails 300/360px, tablet Chat plus switched secondary panel, mobile bottom tabs. Theme/preview/account controls remain available in Settings/header.
- `notebook-model.ts`: `notebookWorkspace(workspace, recoverPending = true): Workspace` merges messages chronologically, retains `legacyThreads`, imports prior Plan/Email outputs into `studioResults`, and recovers interrupted jobs on reload. Initial migration backs up `workspaceai-v2-before-notebook-v1` when quota allows. Storage sync does not interrupt active jobs. `captureChatOutputs(workspace)` snapshots outputs from the existing chat path without creating more sessions.
- `StudioResult`: id/kind/title/timestamps/status/sourceIds/sourceSnapshot/evidenceIds/content/config/draft/suggestions/error/origin/attemptId. These are UI storage extensions, not new SQL tables. `Studio.tsx` owns the two-card tool registry, options forms, newest-first history, retry, rename/delete/export/copy/detail/edit, saved notes, and existing Tasks/Email editors. `studio-service.ts.generateStudio(workspace, config, resultId)` reuses guarded APIs, verifies Plan claims and never sends email.
- `ThemeRuntime` applies the saved theme and device preference independently of the Display popover. Side panels stay mounted when collapsed. Sources ignores an initial library snapshot if a newer local upload/selection/rename/delete has committed.
- Sources adds actual DOCX/PPTX, public link and text imports; processing/error/retry states, search/type/sort/select-all, stable-ID rename and delete. API additions: `POST /api/documents/import-url`, `PATCH /api/documents/{doc_id}`, `GET /api/documents/{doc_id}/pages/{page_number}`. All retain X-Workspace-ID. `DocumentMetadata.source_url` is optional; snapshots persist it.
- `source_formats.py`: zip/XML Office parsing with size bounds; PPTX follows presentation relationship order; DOCX is one extracted text page. Public URL import validates HTTP(S), resolves public addresses and rechecks redirects, strips scripts/styles, limits bytes and rejects private targets. No OCR or original binary viewer. `DocumentInspector` loads actual stored text, checks hash and highlights citation lines; technical metadata is collapsed.
- Document rename retains doc ID/hash/version/selection and updates chunk display names. Repository resolution prefers stable IDs; legacy names must be unambiguous. Reuploading a former filename cannot overwrite its old ID, merge its passages, expand its selection, or delete its sibling version.
- Optional `UserRequest.studio_tool: plan|email` disambiguates tool routing after prompt-injection checks. Plan uses QA verification with request-local `force_offline=True`; no mutation of global engine settings and no Gemini/Ollama calls. Normal Feature 1 and email safeguards remain intact.
- Chat adds numbered source previews, saved notes/feedback, and references to Studio outputs. Existing loading/error/retry and scroll-to-latest behavior remain. `ActionMenu` handles keyboard/outside dismissal; nested dialogs restrict Escape/focus to the topmost dialog.
- Landing removes the header and closing-banner create buttons requested in review; only the central create action remains. UI rationale/wireframes/tokens: `frontend/WORKSPACE_DESIGN.md`. Historical UI sections below describe prior revisions; this section supersedes their multiple-chat behavior.

### Landing Home and retained workspace history (2026-11-08, 2.7.7)
- `App.tsx` imports `Landing.tsx` as its Home entry. The supplied screenshot fixes the landing composition: compact header, authored four-line hero and orange create action, horizontal brand rule, closing brand-gradient action and academic footer. `landing.css` is scoped to `.workspace-landing` and keeps the existing type/palette. The working workspace screens are unchanged.
- `Landing` uses the shared `HomeProps` contract and the existing `create`/`open`/utility handlers. The remaining hero create control opens a validated dialog; How it works opens a workflow-help dialog. Live workspace rows immediately follow the hero CTA and open `open(workspaceId, latestThreadId, "chat")`; an empty workspace can still use App's normal first-thread creation path.
- `home-model.workspaceHistory(workspaces: Workspace[])` returns sorted `{ workspace, thread, timestamp, updated }` copies using the maximum of valid workspace/latest-thread timestamps, leaving original arrays/identities intact. Invalid activity becomes an empty value/dash; missing threads remain undefined. Counts come directly from the retained source/thread arrays.
- `AppTools` accepts optional `compact?: boolean` (default false), used on Landing for the reference's icon-only appearance control; keyboard/outside-dismissal and theme/device controls are retained.
- Checks: 38 frontend contracts, 18 isolated landing interaction checks, production build, and `python verify.py` (47 syntax checks, R2 purity, 63 tests). Reference-specific visual exceptions and screenshots are in `frontend/.taste-skill/landing-v1/`.

### Previous Home dashboard (2026-11-08, 2.7.6; retained source, not the default entry)
- `Home.tsx` now follows the user's three-column reference and the **True-black flat** app direction (seed 1157832561), recorded in `frontend/.taste-skill/home-v5/`; the earlier editorial layout is retained in `home-v4/` as history. A labelled left sidebar, central metrics/Q&A workbench and right task/activity rail replace the centered directory layout. The palette/type are kept. Overview and Conversations are local Home views; search opens history and keeps its existing feature/scope filters, four-row preview and full-history action.
- `HomeOverview.tsx` exposes `HomeMetrics`, `HomeAssistant` and `HomeInsights`. `home-dashboard.css` contains the new responsive geometry; `home.css` retains shared workspace identities, display utilities and conversation/dialog styling. The sidebar folds below 900px, the secondary rail follows the main region below 1000px, and phone widths prioritize the question composer and two-column metrics.
- `dashboardData(workspaces: Workspace[], scope: string | null = null, now = new Date())` computes scoped task/document counts, valid dated open tasks, overdue flags, count-based completion, recent conversations and the last saved Ask exchange. Archived tasks are excluded; zero-task progress is null rather than a fabricated percentage. All displayed totals/bars derive from these rows.
- `App.startFromHome(workspaceId, prompt?)` now stages a prompt in the canonical Ask thread with optional UI-only `Thread.composerDraft`. Chat initializes the input from that field, focuses it and clears the stored draft on explicit submission; Home does not call `/api/chat`. Unscoped Tasks/Email actions select a workspace before opening its actual working view. Saved conversation links still explicitly use `open(workspaceId, threadId, "chat")`.
- `home-model.ts`: `WORKSPACE_COLORS` / `WorkspaceColor` (blue, teal, amber, olive, slate, orange), `assignWorkspaceColors(workspaces: Workspace[]): Workspace[]` balances only missing/invalid identities while preserving existing colors; `workspaceColor(workspace): WorkspaceColor` resolves display identity; `conversationRows(workspaces, scope: string | null = null, mode: Mode | null = null, query = ""): ConversationRow[]` searches accent-insensitively and sorts newest first; `conversationSources(workspace, thread)` reports the last exchange's source records and missing count; `activityLabel(value, now?)` formats Bangkok recency.
- `Workspace.color?: WorkspaceColor` is a UI extension in existing `workspaceai-v2` storage, not an SQL field. `App.tsx` assigns it on migration/read, new workspace creation and cross-window updates. Home and workspace breadcrumb share `data-workspace-color`; record names/order/theme changes do not reshuffle identities. The brand accent is consistently `#E85002`.
- `AppTools.tsx` consolidates theme and desktop phone-preview controls in a keyboard/outside-dismissable Display popover. `home.css` contains scoped Home and identity styles. Existing working panes, document selection, grounding and email safeguards remain intact.
- Checks: 37 frontend contracts (including scoped dashboard/deadline and empty-state cases), production build, `python verify.py` (47 syntax checks, R2 purity, 63 tests). Production visual and isolated interaction records are under `home-v5/`; see its review artifact for viewport coverage and defended warnings.

### Local runtime setup (2026-11-07)
- Current fixes (2.7.4): processed document metadata, indexed passages and file selections persist in ignored `.workspace_data/libraries/{workspaceId}.json`. `backend/repositories/local_library_store.py.LocalLibraryStore(path: Path)` exposes `restore(repository: WorkspaceRepository) -> bool` (complete validation before replacement; index rebuild) and `save(repository: WorkspaceRepository) -> None` (fsync + atomic replace). Original PDF binaries and drafts are not stored here.
- `DocumentService(repository: Optional[WorkspaceRepository] = None, library_path: Optional[Path] = None)` exposes `enable_local_storage(path: Path) -> bool` and `save_library() -> None`. Ingest/selection/deletion serialize mutations and save before responding. Direct instances without a path remain in memory for existing callers/tests. `workspace_context.configure_workspace_storage(root: Path) -> bool` enables persistence at app startup; custom contexts restore their own files lazily. `main.lifespan` restores the default library before seeding, retaining intentionally empty saved libraries.
- `Chat.tsx` receives `active: boolean` from `WorkspaceScreen` and uses layout-time scrolling on conversation entry/new messages plus a pane/content ResizeObserver. Only the chat viewport is scrolled; older messages remain readable without unrelated updates pulling the reader down. `App.open` preserves current workspace selections instead of copying the old answer's file list.
- Runtime validation at 2.7.4: `python verify.py` = AST 47 files, R2 purity, 63 backend tests; frontend contracts then = 29. Live HAHO restart retained both PDFs (451 passages) and the selected subset. Browser checks cover checkbox behavior and returning/reloading at the latest message. Home's 2.7.5 changes increase frontend contracts to 35. All features remain offline; no credential was added.
- Current user preference (2.7.3): **all features offline, saved Gemini key deleted**. The key value was cleared from ignored local `.env` and the owned backend was restarted to discard it from memory. Final runtime: `offline_only=true`, `gemini_configured=false`, `model=null`, all `feature_engines` offline. Preserve this choice unless the user explicitly changes it. Do not print credentials.
- The user tried `gemini-3.5-flash-lite` for Feature 1. Model discovery succeeded but their real questions returned HTTP 403; AI Studio explicitly showed **Free tier unavailable** for their project. Reissuing a key in that same project does not restore free generation. No billing/account changes were made. The disabled integration still restricts Gemini to Feature 1 if explicitly configured in the future.
- `RuntimeStatus` now includes `gemini_scope: "feature1"`, `feature_engines: {qa, tasks, email}` and `model_options`. The key is absent from every status response. `AISettings.tsx` exposes explicit Feature 1 connection and an offline switch; Engine labels/captions follow the current Ask/Tasks/Email mode. Pasted key wrappers are normalized by the backend.
- `LLMProvider.call_gemini(prompt, enforce_json=False, *, feature="qa")` allows only `qa`/`summary`, with active Gemini provider, configured key and offline guard cleared. It makes one request to the configured model and raises safe `GeminiRequestError` messages for quota/access/network/response errors. Chat maps these to HTTP 503 without model switching or synthesized fallback. Strict Gemini claims require model-supplied evidence coordinates and quotes.
- `QAService.summarize_document` uses at most twelve page-spread passages under Gemini, obtains structured claims through `generate_grounded_qa`, aligns and verifies them with the existing R2 algorithm, and returns `summary_scope` (`representative_excerpts` or `all_indexed_passages`). Frontend shows the scope message. Offline/legacy summary behavior is retained; quote verification does not guarantee semantic entailment.
- Previous 2.7.3 checks: `python verify.py` = 45 syntax checks, R2 purity, 54 backend tests; `pnpm test` = 29 frontend contracts; production build passed. Google responses in automated tests are mocked; the user's real generation attempts failed due to project access.
- File-selection fix (2.7.2): React API access applies to every valid workspace ID, replacing the old `midterm`-only gate. All documents/chat/email requests send `X-Workspace-ID`; runtime configuration remains global. No header aliases the legacy `midterm` library.
- `backend/services/workspace_context.py`: `WorkspaceServices(repository, documents, qa, drafts, email, is_default=False)`; `get_workspace_services(workspace_id: Optional[str] = None): WorkspaceServices` validates 1–64 alphanumeric/underscore/hyphen IDs and caches independent in-memory service/repository sets. `resolve_workspace_services(value: object)` preserves direct route-function callers. `backend/api/dependencies.py.workspace_services` reads the header and rejects invalid IDs with HTTP 400. Custom libraries start empty; custom reconciliation does not use demo requirements/tasks. No SQL schema changes.
- `workflow-model.ts.syncWorkspaceLibrary(w: Workspace, serverSources: Source[], replacements: Record<string, string> = {}): Workspace` merges device previews by actual hash or explicit re-upload replacement, keeps matching metadata/page text and reference links, and retains disappeared server entries as unselected **Needs upload** records. `Sources.tsx` provides re-upload processing, scoped automatic/manual sync, upload, deletion and selection.
- Previous 2.7.2 file-selection validation: `python verify.py` = AST 44 files, R2 purity, 38 backend tests; `pnpm test` = 28 frontend tests; production build passed. Actual HAHO browser checks covered individual/all/clear selection and reload. Offline Q&A with one actual PDF returned five cited findings; zero selected sources abstains. The then memory-only library is replaced by 2.7.4 persistence.
- `Start-Workspace.cmd` / `Start-Workspace.ps1 [-Engine offline|auto|gemini|ollama]`: default `auto` honors saved settings; start backend `127.0.0.1:8000` and Vite `127.0.0.1:5174` as hidden processes, validate readiness, store local logs/PIDs under ignored `.workspace_data/runtime/`, and reuse installed dependencies. Node can use the existing Codex runtime if absent from PATH. Explicit `-Engine offline` blocks cloud generation.
- `backend/core/config.py.Settings.offline_only: bool` comes from `WORKSPACE_OFFLINE_ONLY`. Offline launch sets cloud blocking and offline model-loading flags. The user can explicitly connect Gemini for Feature 1 through local setup; this saves `WORKSPACE_OFFLINE_ONLY=false`, `LLM_PROVIDER=gemini` and the selected model/key only when persistence is selected. Launcher email stays mock.
- `backend/services/runtime_service.py.runtime_status(): Dict[str, Any]`: `status`, `engine_mode`, `offline_only`, `gemini_configured`, `model`, `supported_formats`, `gemini_scope`, `feature_engines`, `model_options`; no credential values. `configure_gemini(api_key: Optional[str], save_locally=True, model: Optional[str]=None, enable_feature1=False)` requires explicit opt-in when offline, validates the selected stable model (3.5 Flash-Lite or 3.8 Flash) without generating an answer and atomically persists local settings after validation. `use_offline(save_locally=True)` switches to mock/offline, retaining the saved key for optional later reuse.
- `backend/api/runtime_routes.py`: GET `/api/runtime`; POST `/api/runtime/gemini` with optional `SecretStr api_key`, `save_locally`, a supported model and `enable_feature1`; POST `/api/runtime/offline` with `save_locally`. Mutations share local-client/origin checks; errors never echo credentials. Registered in `backend/main.py`. `LLMProvider.call_gemini` independently enforces feature/offline/provider restrictions and uses `x-goog-api-key` headers.
- `frontend/src/AISettings.tsx`: scoped setup form is isolated from the chat composer through a portal and stopped submit propagation; keys remain only in transient input state and are cleared after successful connection, closing or leaving the view. Query `setup=gemini` opens settings; enabling Feature 1 requires explicit submission. `mode` controls its engine label.
- `Sources.tsx` auto-syncs server metadata on entering each workspace. `Chat.tsx` reports the actual runtime policy in its composer caption. Existing overall design and local workspace data remain intact.
- Gemini validation (2.7.3): `python verify.py` = AST 45 files, R2 purity, 54 backend tests; `pnpm test` = 29 frontend tests. Live model discovery worked but generation was denied by Google; the current local runtime is offline with no key configured. Optional `--cloud-form` only stubs credential submission in an isolated test. As of 2.7.4, indexed documents and selection survive backend restarts.
### Architecture layers
- `backend/core/`: Schemas (`schemas.py`), Configuration (`config.py`), Security Guardrails (`guardrails.py`).
- `backend/algorithms/`: Pure Python Stdlib (R2 deterministic logic: Citation Verifier, Email FSM, Reconciliation).
- `backend/repositories/`: Local in-memory indexing, BM25 + Dense RRF (`workspace_repository.py`), Email staging (`draft_repository.py`).
- `backend/providers/`: Local embeddings (`embedding_provider.py`), LLM interfaces (`llm_provider.py`), Prompt templates (`prompts.py`).
- `backend/services/`: Ingestion (`document_service.py`), Grounded Q&A (`qa_service.py`), Reconciliation (`reconciliation_service.py`), Email (`email_service.py`), Intent routing (`router_service.py`).
- `backend/api/`: FastAPI routers (`chat_routes.py`, `document_routes.py`, `email_routes.py`).
- `frontend/`: Modular Streamlit app (`app.py`, `state.py`, `styles.py`, `components/*`).
- `frontend/src/`: React/TypeScript app sharing the folder with Streamlit. React entry point `main.tsx`; existing Streamlit files are unchanged by the frontend schema alignment.

### React frontend schema and API contracts (2026-11-06)
- `schema.ts`: `DocumentRow`, `DocumentPageRow`, `DocumentChunkRow`, `RequirementRow`, `TaskRow`, `ReconciliationRunRow`, `ReconciledItemRow`, `ChatSessionRow`, `ChatMessageRow`, `CitationClaimRow`, `EmailDraftRow`, `EmailAuditRow`, and `SchemaTables` mirror the 12 SQL tables. Canonical task/engine/citation/email/reconciliation/risk enums are explicit. UI aliases in `data.ts` do not imply extra SQL columns.
- `workflow-model.ts`: `migrateWorkspace(w: Workspace): Workspace` preserves legacy data and normalizes task states, local labels/archive flags, engine preferences and draft attachments; `taskRow(task: Task): TaskRow` exports SQL task fields; `sourceFromServer(row): Source` supports current API metadata aliases; `resolveCitedSource(docId, sources)` permits unique document aliases; `draftPayload`, `recipientAddress`, `validRecipient` and `sha256` define the client review boundary.
- `report-model.ts`: `reportState(state, conflict): ReconciliationState` adapts legacy R2 response names; `appendReport(workspace, report, referenceDate): Workspace` validates and retains a local snapshot of server results. Reconciliation calculations remain in `backend/algorithms/`.
- `api.ts`: `apiFor(workspaceId)` enables every valid ID in API mode; `listDocuments(workspaceId?)`, `uploadDocument(file, workspaceId?): Promise<Source>`, `deleteDocument(id, workspaceId?)`, `selectDocuments(ids, workspaceId?)`, `chatRequest(query, selectedDocIds, history?, recipient?, referenceDate?, workspaceId?)`, `reconcile(referenceDate, workspaceId?)`, `draftFromServer`, `approveAndSend(draft, workspaceId?)`. Workspace IDs become headers, with multipart Content-Type left to fetch. The approval endpoint approves AND dispatches; edited, local, CC or attachment payloads are blocked under its current capabilities.
- `Tasks.tsx` / `Requirements.tsx` / `Reconciliation.tsx`: four canonical task states, local requirement/task CRUD and explicit mapping/progress, server report history. Requirement/task CRUD endpoints are absent; local edits are not sent to the server's reconciliation dataset.
- `Chat.tsx` / `DocumentInspector.tsx`: server-verified findings only from selected server documents; rejected claims remain excluded. Sample excerpts are unverified. Page text is shown only when actually supplied, with version/hash mismatch protection.
- `Email.tsx`: one server recipient, preserved local CC notes, separate attachment selection, content/attachment review invalidation, six SQL states and audit records when supplied. No client-forged HMAC/audit/sent timestamps. Submission locks persist across reloads; current API has no email draft update, attachment staging, audit listing or operation lookup.
- Storage: existing `workspaceai-v2` retained, schema version 3, optional one-time `workspaceai-v2-before-schema-v3` backup; email locks `wai-email-submissions-{workspaceId}`. Legacy simulated delivery keys are not interpreted as server outcomes. Workspaces/members/auth/local labels/archive/CC remain UI extensions.
- API configuration: `VITE_API_ENABLED`, `VITE_API_BASE_URL`; no secret keys in client configuration. Obsolete `VITE_API_WORKSPACE_ID` is ignored. Vite development proxy `/api` → `127.0.0.1:8000`; production needs its own reverse proxy and must forward `X-Workspace-ID`. Server engine switching is not exposed by the existing request contract.
- Checks: `pnpm test` (38 contract/migration/API/Home tests), `pnpm build`. Existing browser harnesses are `tests/browser-schema.mjs` and `tests/browser-feature1.mjs`; the latter forwards workspace headers to its isolated backend and uses the scoped setup form. Browser helper path is configurable through `TASTE_SKILL_CDP`. Root Python verification remains `python verify.py`.

---

## 2. Core Pydantic Schemas (`backend/core/schemas.py`)
- `RouteType(str, Enum)`: `QA_FLOW`, `RECONCILE_FLOW`, `EMAIL_FLOW`, `CLARIFICATION_FLOW`, `REJECTED_SAFEGUARD`
- `EmailState(str, Enum)`: `IDLE`, `AWAITING_CLARIFICATION`, `PENDING_APPROVAL`, `APPROVED`, `SENT`, `FAILED_RETRYABLE`
- `DocumentChunk`: `chunk_id: str, doc_id: str, doc_name: str, page_number: int, start_line: int, end_line: int, section_header: str, text: str, score: float, bm25_score: float, dense_score: float, rrf_score: float, pinpoint_score: float, doc_version: str, doc_hash: str`
- `DocumentMetadata`: `doc_id: str, doc_name: str, file_type: str, page_count: int, chunk_count: int, total_lines: int, file_hash: str, version_id: str, uploaded_at: str, is_selected: bool`
- `RequirementItem` / `RequirementRecord`: `req_id: str, title: str, keywords: List[str], official_deadline: Optional[date], mandatory_flag: bool, source_ref: str`
- `TaskRecord`: `task_id: str, mapped_req_id: Optional[str], title: str, owner: Optional[str], status: str, logged_deadline: Optional[date], completion_pct: float, source_ref: str`
- `DateConflict`: `doc_a: str, date_a: date, doc_b: str, date_b: date`
- `ReconciledItemReport`: `req_id: str, title: str, state: str, risk_level: str, avg_completion: float, days_remaining: Optional[int], owners: List[str], date_conflicts: List[DateConflict], citations: List[str]`
- `ReconciliationSummary`: `coverage_ratio: float, overdue_count: int, conflict_count: int, item_reports: List[ReconciledItemReport]`
- `GeneratedClaim`: `claim_text: str, cited_doc_id: str, cited_page: int, evidence_quote: str, verification_status: str, cited_start_line: Optional[int], cited_end_line: Optional[int], doc_version: Optional[str], doc_hash: Optional[str], match_score: float, matched_span: Optional[str], evidence_span: Optional[Dict[str, Any]]`
- `CitationVerificationResult`: `validated_claims: List[GeneratedClaim], hallucination_flags: List[GeneratedClaim], grounding_score: float`
- `EmailDraftPayload`: `draft_id: str, recipient_email: str, subject: str, body: str, attachment_ids: List[str], citations: List[str], state: EmailState, payload_hash: str`
- `EmailApproveRequest`: `recipient_email: str, subject: str, body: str, user_confirmed: bool`
- `UserRequest`: `query: str, selected_doc_ids: Optional[List[str]], recipient_email: Optional[str], reference_date: date, conversation_history: List[Dict[str, str]]`
- `DocumentSelectRequest`: `selected_doc_ids: List[str]`

---

## 3. Public Function Signatures

### Algorithms (`backend/algorithms/`) — 100% Pure Stdlib
- `citation_verifier.verify_citations(claims: Sequence[Union[CitationClaim, Any]], chunk_lookup: Dict[Any, Any], theta_match: float = 0.75) -> CitationVerificationResult`
- `reconciliation.reconcile_requirements_and_tasks(requirements: List[Any], tasks: List[Any], t_now: date) -> ReconciliationSummary`
- `email_state_machine.compute_draft_hash(draft: Any) -> str`
- `email_state_machine.prepare_draft_for_approval(draft: Any) -> Any`
- `email_state_machine.approve_and_verify_email_send(stored_draft: Any, approved_recipient: str, approved_subject: str, approved_body: str, approved_attachments: List[str], user_confirmed: bool) -> Any`

### Repositories (`backend/repositories/`)
- `workspace_repository.WorkspaceRepository`:
  - `add_document(metadata: DocumentMetadata, chunks: List[DocumentChunk]) -> int`
  - `delete_document(doc_id: str) -> bool`
  - `get_document_by_hash(file_hash: str) -> Optional[DocumentMetadata]`
  - `get_next_version_id(doc_name: str) -> str`
  - `set_selected_documents(doc_ids: List[str]) -> None`
  - `get_selected_doc_ids() -> List[str]`
  - `list_documents() -> List[Dict[str, Any]]`
  - `get_document_chunks(doc_id: str) -> List[DocumentChunk]`
  - `ingest_text_document(doc_id: str, doc_name: str, pages: List[Tuple[int, str]], doc_version: str = "v1", doc_hash: str = "") -> int`
  - `ingest_csv_tasks(doc_id: str, doc_name: str, csv_content: str) -> int`
  - `search(query: str, top_k: int = 5, selected_doc_ids: Optional[List[str]] = None) -> List[DocumentChunk]`
  - `build_page_lookup() -> Dict[Tuple[str, int], Dict[str, Any]]`
  - `seed_demo_workspace() -> None`
- `draft_repository.DraftRepository`:
  - `save(draft: EmailDraftPayload) -> EmailDraftPayload`
  - `get(draft_id: str) -> Optional[EmailDraftPayload]`
  - `list_all() -> List[EmailDraftPayload]`

### Providers (`backend/providers/`)
- `embedding_provider.EmbeddingProvider`:
  - `load_model() -> bool`
  - `embed_texts(texts: List[str]) -> Optional[np.ndarray]`
  - `get_embed_fn() -> Optional[Callable[[List[str]], Optional[np.ndarray]]]`
- `llm_provider.LLMProvider`:
  - `is_ollama_online() -> bool`
  - `is_gemini_configured() -> bool`
  - `call_gemini(prompt: str, enforce_json: bool = False) -> Optional[str]`
  - `call_ollama(prompt: str, enforce_json: bool = False) -> Optional[str]`
  - `synthesize_smart_answer(query: str, chunks: List[DocumentChunk]) -> str`
  - `generate_grounded_qa(query: str, chunks: List[DocumentChunk], conversation_history: Optional[List[Dict[str, str]]] = None) -> List[GeneratedClaim]`
  - `generate_summary(doc_name: str, chunks: List[DocumentChunk]) -> str`
  - `generate_email_draft(query: str, chunks: List[DocumentChunk], recipient_email: Optional[str] = None) -> Tuple[str, str]`
- `prompts`:
  - `format_chunk_for_llm(chunk: DocumentChunk) -> str`
  - `build_qa_prompt(query: str, chunks: List[DocumentChunk], conversation_history: Optional[List[dict]] = None) -> str`
  - `build_summary_prompt(doc_name: str, chunks: List[DocumentChunk]) -> str`
  - `build_email_prompt(query: str, chunks: List[DocumentChunk], recipient_email: Optional[str] = None) -> str`

### Services (`backend/services/`)
- `document_service.DocumentService`:
  - `__init__(repository: Optional[WorkspaceRepository] = None, library_path: Optional[Path] = None)`
  - `enable_local_storage(path: Path) -> bool`, `save_library() -> None`
  - `compute_hash(content_bytes: bytes) -> str`
  - `parse_pdf_pages(filename: str, content_bytes: bytes) -> List[Tuple[int, str]]`
  - `parse_text_pages(content_bytes: bytes) -> List[Tuple[int, str]]`
  - `build_page_chunks(doc_id: str, doc_name: str, page_num: int, page_text: str, doc_version: str, doc_hash: str) -> List[DocumentChunk]`
  - `ingest_file(filename: str, content_bytes: bytes) -> Dict[str, Any]`
  - `format_chunk_with_lines(chunk: DocumentChunk) -> str`
- `qa_service.QAService`:
  - `resolve_summary_target(query: str, repository: WorkspaceRepository, selected_doc_ids: Optional[List[str]] = None) -> Optional[str]`
  - `expand_contextual_query(query: str, history: Optional[List[Dict[str, str]]]) -> str`
  - `align_claim_to_chunks(claim: GeneratedClaim, chunks: List[DocumentChunk]) -> GeneratedClaim`
  - `summarize_document(doc_id: str) -> Dict[str, Any]`
  - `answer_question(query: str, top_k: int = 3, selected_doc_ids: Optional[List[str]] = None, conversation_history: Optional[List[Dict[str, str]]] = None, tau_rel: Optional[float] = None, theta_match: Optional[float] = None) -> Dict[str, Any]`
- `reconciliation_service.ReconciliationService`:
  - `get_default_requirements() -> List[RequirementItem]`
  - `get_default_tasks() -> List[TaskRecord]`
  - `extract_requirements_from_workspace(doc_ids: Optional[List[str]] = None) -> List[RequirementItem]`
  - `reconcile(reference_date: date, requirements: Optional[List[RequirementItem]] = None, tasks: Optional[List[TaskRecord]] = None) -> Dict[str, Any]`
- `email_service.EmailService`:
  - `prepare_draft(query: str, chunks: List[DocumentChunk], recipient_email: str) -> EmailDraftPayload`
  - `send_email(draft_id: str, recipient_email: str, subject: str, body: str, user_confirmed: bool) -> Dict[str, Any]`
- `router_service`:
  - `route_user_request(req: UserRequest) -> Tuple[RouteType, List[str]]`

### Frontend (`frontend/`)
- `state`: `init_state()`, `queue_query(text: str, toast: Optional[str] = None)`, `set_task(idx: int, status: str, pct: float)`, `advance_task(idx: int)`, `reset_chat()`, `reset_workspace()`, `clear_sent_email()`, `add_message(role: str, content: str, data: Any = None)`, `highlight_evidence_in_page(page_text: str, quote: str, matched_span: Optional[str] = None) -> str`
- `styles`: `apply_custom_styles() -> None`
- `components.sidebar_library`: `render_document_library() -> None`, `render_sidebar_settings() -> Tuple[date, str]`
- `components.chat_panel`: `render_chat_panel(recipient_email: str, ref_date: date) -> None`
- `components.evidence_viewer`: `render_evidence_viewer() -> None`
- `components.reconciliation_board`: `render_taskboard(ref: date) -> None`
- `components.email_assistant`: `render_email_review(scope: str) -> None`, `email_dialog() -> None`

