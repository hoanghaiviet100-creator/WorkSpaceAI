# WorkspaceAI System Codebase Map (v2.5)
> Rapid context reference for AI Agents: Module layout, Pydantic schemas, and public function signatures.

## F2 structured Quiz and interactive draft preview — 2026-11-13 (current)
- Supersedes Quiz cloze-priority prompt and text-only draft limits below. The existing JSON pipeline now has a shared typed wire contract and an explicit interactive draft path; no semantic-verification bypass or Q06 change.
- New `backend/core/f2_quiz_payload.py`: frozen/extra-forbidden `LLMQuizQuestion(question,options:tuple[QuizOption,...],correct_option_id,explanation,source_ids:tuple[str,...])`, 2–4 distinct options/IDs, one existing key, nonblank strict strings and unique exact source aliases. `LLMQuizPayload(questions:tuple[LLMQuizQuestion,...])` permits an empty array. `quiz_response_schema()->dict` inlines Pydantic refs and removes titles; returns fresh simple JSON Schema shared by prompt and Gemini responseJsonSchema. Array minItems/maxItems are derived from field constraints. No model-supplied question ID/provenance/verified flag.
- `build_quiz_prompt` includes this schema, JSON-only instructions and correct empty-root format. Q03 uses strict JSON envelope parser then `LLMQuizQuestion.model_validate` per item before assigning server IDs/mapping current source aliases. Preserves partial results, malformed/duplicate JSON rejection, source membership, counts and no fallback in UI. Other Q01 contracts unchanged.
- `build_source_content_prompt(...,'quiz')` now asks for self-contained natural questions, comprehension/comparison/source-grounded application, named subjects/functions, sensible distractors, source-backed explanation and exact JSON. No cloze priority in this mode; tells model to skip unresolved subjects rather than guess. This is prompt policy, not proof of actual question quality. Flashcard prompt and old definition mode remain available; no Math/Physics solving.
- New `backend/core/f2_quiz_preview_schemas.py`: `DraftQuizPreview(status='UNVERIFIED_DRAFT',quiz_set_id,requested_count,actual_count,questions:tuple[LearnerQuizQuestion,...],result:DraftQuizResult|None=None)`; before submit no key/explanation/source refs. `DraftQuizResult(total_count,answered_count,matching_count,match_percent,items:tuple[DraftQuizFeedback,...])`; feedback has question_id/selected_option_id/proposed_option_id/matches_proposed/explanation/source_refs. These report matches to AI proposals, not verified scores.
- `F2StudyDraftService.preview_quiz(resource:QuizSet,*,context:SourceAccessContext,submission:QuizSubmission|None=None)->DraftQuizPreview`: fresh review/source reads on each render/submit/result; block rejected content, global warnings, unmatched/unavailable sources and detected deferred math requests. Review-only semantics may be previewed under the unverified label. Uses existing stdlib grading to compare selections; never creates a Q06 session or marks a resource VERIFIED. Reject unknown/repeated choices. Q06 still refuses non-ready natural-question resources.
- Manual UI adds `Làm thử Quiz nháp (chưa kiểm chứng)` -> radio form -> `Nộp bản nháp` -> proposed-answer comparison/explanation/citations, retry and back-to-review. Hides author answer panel during preview, separates unverified comparison from checked practice, rechecks stale sources. New generation resets preview. Hot reload upgrades the review service without resetting the repository/key widgets. No demo data or eager cloud calls.
- New tests: 37 backend/protocol + 7 AppTest; focused-final 262 passed. Full verify: 653 passed (609 prior +44), AST82, R2 PASS; existing Starlette warning remains. All previous test files unchanged. HTTP MockTransport only; browser empty/config state updated via Rerun, no real-key generation. Guide/schema/manual steps/evidence: `docs/f2/F2_STRUCTURED_QUIZ.md`. General semantic judge, actual PDF/model quality evaluation, full API/auth, SQLite and Math/Physics solving remain pending/deferred.

## F2 source content, inspection and draft review — 2026-11-13
- Supersedes definition-only UI/validation limits below; historical task reports remain point-in-time. F1/F3, Q01 contracts, Q03/Q04 generation parsing and Q06 practice APIs stay unchanged.
- `F2SourceService.inspect_sources(selection: StudySourceSelection, *, context: SourceAccessContext) -> SourceInspection`: read-only exact-scoped preview using Q02 metadata/chunk validation, overlap-aware passage/line counts, injection exclusion and final metadata check. Frozen `SourceChunkPreview(chunk_id,page_number,start_line,end_line,text,excluded_as_suspicious)`; `SourceDocumentPreview(doc_id,doc_name,doc_version,doc_hash,page_numbers,text_character_count,usable_passage_count,category_counts,chunks,warnings)`; `SourceInspection(workspace_id,selection,documents)`. All collections are tuples. Actual extracted text is shown literally; warnings cover short/no eligible text, replacement/private-use characters, symbol density and PDF formula/image limitations. No OCR or formula correctness claim.
- `backend/providers/f2_source_content_provider.py`: `build_source_content_prompt(evidence: tuple[StudyEvidence,...], requested_count: int, study_format: str)->str`; `SourceContentProvider(adapter,study_format).generate(evidence,requested_count)->str`. Explicit wrapper over existing Gemini/NIM/Ollama transport, preserves adapter name and JSON/HTTP protocol. Source facts/rules/conditions/examples/procedures and natural questions allowed, qualifiers/units preserved, no padding or math solver. Old definition mode selectable; offline unchanged.
- `backend/algorithms/f2_content_support.py`: pure stdlib `validate_quiz_content_support(question,options,correct_option_id,explanation,cited_sources,all_sources)` and `validate_flashcard_content_support(front,back,cited_sources,all_sources) -> ContentSupportDecision`. Keeps old definition checks; additionally proves full-quote single-blank clozes with >=4 context words, exact restored quote(s), literal ambiguity checks across selected sources and exact Quiz explanation. Wrong recognized key rejects; general/paraphrased questions and detected calculation/proof requests stay REVIEW_REQUIRED. Source-relative correspondence, not a semantic judge or external factual proof.
- Q05 calls these checks without weakening identity/access/freshness/injection gates. `StudyValidationResult.method` accepts `EXTRACTIVE_STUDY_V2` for cloze-bearing resources as well as default `EXTRACTIVE_DEFINITION_V1`. Q01 SourceRefs remain UNVERIFIED; learner projections unchanged.
- `backend/services/f2_study_draft_service.py`: `StudyDraftError(code,message)`; frozen `StudyDraftReview(resource: QuizSet|FlashcardDeck,validation: StudyValidationResult).verified_item_ids -> tuple[str,...]`; `F2StudyDraftService(repository).review(resource,*,context:SourceAccessContext)->StudyDraftReview`; `.verified_subset(resource,*,context)->QuizSet|FlashcardDeck`. Revalidate each time; no client receipt/approval flag accepted. Only MATCHED/SUPPORTED items without item/global issues can be explicitly selected for practice. Subset keeps requested_count, selection, order/IDs and full original draft; Q06 validates independently again.
- UI: opt-in preview; AI default `Nội dung tài liệu` / optional old definition mode; source/API/empty-output diagnostics, safe vendor HTTP status. Author drafts show proposed answers/reasons and citations only for currently MATCHED sources, separate from learner practice. Explicit verified-subset action reports count; no VERIFIED bypass. Runtime v2 migration retains repository/password widgets and previous practice object, uses updated verifier. Preview closes on generation. No seeded data or API calls on configuration.
- New tests: 45 backend/protocol + 13 AppTest. Focused 158 passed including 100 old UI/provider tests; full `verify.py` 609 passed, AST78, R2 PASS, one existing Starlette/TestClient warning. MockTransport only for cloud tests. Local UI/default broader mode verified in browser; no real-key generation/corpus evaluation by agent. Old server absent; restarted hidden on loopback :8512 (new session). Guide: `docs/f2/F2_SOURCE_CONTENT_REPORT.md`. Math/Physics solving deferred, SQLite after MVP.

## F2 NVIDIA NIM integration — 2026-11-12
- `backend/providers/f2_nvidia_nim_provider.py`: `DEFAULT_NVIDIA_NIM_MODEL='meta/llama-3.3-70b-instruct'`; `NvidiaNimStudyProvider(api_key, model=DEFAULT_NVIDIA_NIM_MODEL, *, transport=None).generate_from_prompt(prompt)->str`, name='nvidia_nim'. `NvidiaNimQuizProvider.generate(evidence, requested_count)` / `NvidiaNimFlashcardProvider.generate(evidence, requested_count)` implement existing service protocols. Fixed NVIDIA-hosted HTTPS chat/completions endpoint, Bearer auth header, non-streamed documented fields, max_tokens=4096, temperature=.1, read60/connect2, 1MB response cap, no redirect/retry/poll/proxy env/fallback. Only one complete assistant text choice with finish_reason='stop'; reject filtering/refusal/tool calls/truncation/invalid content. Sanitized typed errors include auth/quota/model/pending202/unavailable.
- `backend/providers/f2_definition_prompts.py`: `build_definition_quiz_prompt(evidence, requested_count)->str` and `build_definition_flashcard_prompt(evidence, requested_count)->str`. Extract Gemini's exact Q05 policy into shared prompts; Gemini now delegates to the helpers, with the same prompt text and HTTP behavior. No Q01–Q06 source/schema/validation changes. JSON output is requested by prompt for NIM, not assumed to be server-enforced JSON mode; existing strict parsers reject fenced/malformed/forged outputs.
- Local UI selects Offline/Gemini/NVIDIA NIM/Ollama. NVIDIA API key is a distinct masked session widget or NVIDIA_API_KEY env fallback; model from NVIDIA_NIM_MODEL or the adapter default. No Gemini key inherited, no eager request on selection/configuration, no key written to file. Explicit generation sends only Q02-selected passages to NVIDIA; missing key disables creation. Provider/model label remains selected adapter/requested model, not proof of valid credentials or resolved version.
- `tests/test_f2_nvidia_nim_provider.py`: 48 simulated-HTTP plus real-service/AppTest cases for protocol, credential isolation, errors/pending/caps/refusals/tools, selected-content scope, Q05 rejection and no fake offline success. Final full verify: 551 passed, AST73 files, R2 PASS; all prior 503 tests unchanged, including 43 Gemini regression cases. Browser NIM selection, masked empty key, expected model and disabled create button verified. No live NVIDIA/key/quota/model evaluation performed.
- New guide `docs/f2/F2_NVIDIA_NIM.md`; current-state pointers in older UI/provider guides. Gemini source refactor is intentional; no shared F1/F3/settings/dependency/persistence edits or full Q08 API/auth claim. Manual real-key testing is next; SQLite remains after MVP.

## F2 AI provider integration — 2026-11-12
- New `backend/providers/f2_gemini_provider.py`: `DEFAULT_GEMINI_STUDY_MODEL='gemini-3.5-flash-lite'`; `GeminiStudyProvider(api_key, model=DEFAULT_GEMINI_STUDY_MODEL, *, transport=None).generate_from_prompt(prompt, study_format)->str`, name='gemini'. `GeminiQuizProvider.generate(evidence, requested_count)` and `GeminiFlashcardProvider.generate(evidence, requested_count)` implement existing generation protocols. Fixed Google HTTPS generateContent origin; header auth, model-path validation, no redirects/retries/proxy env, read 60s/connect 2s, 1,000,000-byte response cap, JSON Schema wire shapes, exactly one completed STOP candidate; thoughts ignored, text parts joined. Typed/sanitized missing config/auth/quota/model/block/incomplete/invalid/unavailable errors, no response body/key in error messages.
- Gemini prompts reuse existing escaped evidence framing and add exact definition-template instructions compatible with unchanged Q05; no precomputed questions passed off as AI output. Q01/Q02 source mapping and Q05/Q06 gates remain authoritative. General/paraphrased/unsupported answers can be blocked even after a successful API response.
- Existing local UI now selects Offline(default)/Gemini/Ollama. Gemini key from masked session widget or existing server GEMINI_API_KEY; GEMINI_MODEL override or new adapter default, editable model input. No key written to files; selected source passages sent to Google only on explicit generation. Existing Ollama adapters use server base URL and editable model name. No fallback configured; provider/model request label describes selection, not a successful connection or a resolved model version. Generation failures/source shortages remain visible.
- Modified only UI entrypoint/panel, map/changelog and a current-state pointer in the prior manual guide; new adapter/tests/guide. No Q01–Q06 code/tests/reports, F1/F3/shared config/provider/dependencies/persistence changes. No backend study routes/auth integration or Q08 completion claim.
- `tests/test_f2_ai_providers.py`: 43 cases with explicitly simulated Gemini HTTP and real ingestion→generation→Q05/Q06/UI paths, including invalid key/quota/redirect/caps/truncation, wrong support rejected and no hidden offline fallback. Full verify final: 503 passed (460 prior +43), AST 70 files, R2 PASS. Browser selected Gemini and showed masked key/config; no live Gemini request, real-key/quota validation or Ollama health/generation evaluation performed. See `docs/f2/F2_AI_PROVIDERS.md` for usage, sources, evidence and actual limitations.

## F2 temporary manual UI — 2026-11-12 (not Q08 completion)
- `frontend/f2_manual_app.py`: separate Streamlit entrypoint, run on 127.0.0.1:8512. `frontend/components/f2_manual_panel.py` exposes `render_controls()` and `render_practice()`; only thin calls to existing DocumentService and Q02–Q06. Per-browser in-memory repository/practice service and server-created local identity; no seed/sample documents, prebuilt questions, fake scores, new backend behavior or validation bypass.
- Real PDF/text-layer, TXT/MD upload → explicit ingestion/source selection → existing default deterministic Quiz/Flashcard generation → Q06 start (includes Q05 gate) → Quiz submit/results or Flashcard flip/previous/next. Actual generation warnings/shortages/errors retained. Original keys/quotes/backs are not rendered before submit/flip; source validation reruns through Q06. No Ollama selection or live model evaluation added.
- Q00–Q06 backend/source/tests/reports and F1/F3 remain unchanged. This is an isolated local manual interface, not full study API/auth/production runtime integration; no SQLite or persistence. See `docs/f2/F2_MANUAL_UI.md` for opening/restarting and test limits.
- `tests/test_f2_manual_ui.py`: 9 AppTest integration cases over real existing services, including actual score/reveal/flip, no seeded success, shortage/unusable/injection/stale sources and per-session isolation. Final full verify: 460 passed (prior 451 + 9), AST 68 files, R2 PASS. Browser empty-state/layout and local health verified; browser file-picker upload was not automated.

## F2-Q06 — 2026-11-12 Quiz submit/results and Flashcard interaction
- Pure stdlib `backend/algorithms/f2_quiz_grading.py`: `grade_single_choice(questions: Sequence[tuple[str, Sequence[str], str]], answers: Sequence[tuple[str,str]]) -> QuizGrade`; questions are (question_id, option_ids, correct_option_id). Frozen `GradedAnswer(question_id, selected_option_id, correct_option_id, is_correct)` and `QuizGrade(items)` with total_count/answered_count/correct_count/score_percent (actual item count, 2 decimals). Omitted answers are unanswered/incorrect; duplicate/unknown IDs or malformed keys raise `QuizGradingError(code,message)`.
- New core `backend/core/f2_practice_schemas.py`, all frozen/extra-forbidden with nested revalidation: `QuizAnswer(question_id, option_id)`; `QuizSubmission(answers=())`, unique question IDs, ordered lists/tuples only. `LearnerQuizQuestion(question_id, question, options)` and `QuizPracticeView(session_id, quiz_set_id, status: IN_PROGRESS|SUBMITTED, requested_count, actual_count, questions)` never carry keys, explanations, source refs/quotes or internal digests. `QuizQuestionFeedback(question_id, selected_option_id, correct_option_id, is_correct, explanation, source_refs)` and `QuizPracticeResult(session_id, quiz_set_id, total_count, answered_count, correct_count, score_percent, items)` are post-submit projections.
- `FlashcardFrontView(session_id, deck_id, requested_count, actual_count, current_index, card_id, front, side='front')`; `FlashcardBackView` adds back/source_refs and side='back'. current_index is zero-based. Only the current card is projected; front serialization has no back or source quote, including after flipping back or navigating.
- `backend/repositories/f2_practice_repository.py`: frozen internal `QuizPracticeSession(session_id, workspace_id, learner_id, quiz, resource_digest, source_snapshot_digest, submission=None)` and `FlashcardPracticeSession(session_id, workspace_id, learner_id, deck, resource_digest, source_snapshot_digest, current_index=0, revealed=False)`. `InMemoryPracticeRepository.transaction()/get(session_id)/create(session)/replace(session)` use one reentrant process-local lock; the service holds it through read/check/update. No persistence, singleton, TTL, multi-worker coordination or lock on independent source storage.
- `backend/services/f2_practice_service.py`: frozen `PracticeAccessContext(learner_id, sources: SourceAccessContext)` is server-resolved identity/scope, not auth. `PracticeError(code,message)`. `F2PracticeService(repository: StudySourceRepository, *, sessions: InMemoryPracticeRepository|None=None)` owns or reuses explicit sessions.
- Public methods, all requiring keyword `context: PracticeAccessContext`: `start_quiz(quiz)->QuizPracticeView`, `get_quiz(session_id)->QuizPracticeView`, `submit_quiz(session_id, submission: QuizSubmission)->QuizPracticeResult`, `get_quiz_result(session_id)->QuizPracticeResult`; `start_flashcards(deck)->FlashcardFrontView`, `get_flashcard(session_id)->FlashcardFrontView|FlashcardBackView`, `flip_flashcard(session_id, *, card_id)->FlashcardFrontView|FlashcardBackView`, `move_flashcard(session_id, direction, *, card_id)->FlashcardFrontView`. Directions are next/previous; no wrap, reveal resets on move, expected current card ID blocks stale-view actions.
- Every successful read/action reruns Q05 with current backend scope and pins both resource/source digests. Non-ready, changed resources/sources or revoked permission block response/state update. Other learner/workspace/type sessions return generic SESSION_NOT_FOUND before source reads. Client validation receipts are never accepted. Results are unavailable before submit; identical/reordered retries are idempotent, a different resubmission is blocked, and retry practice uses a new session. Empty/partial submission is allowed explicitly, omitted answers score zero; no bonus/negative weighting.
- Verification: 75 focused tests; full `verify.py` 451 passed, AST 65 files, R2 PASS. Q01–Q05 source/tests/reports and F1/F3 unchanged. Real two-document ingestion→generation→Q05→practice tested for both formats; no live model/browser E2E. API/UI still Q08; SQLite Q07 stays after MVP. See `docs/f2/F2-Q06_REPORT.md` for decisions, logs, limits and next-task packet.

## F2-Q05 — 2026-11-12 Content validation and source grounding
- New core `backend/core/f2_validation_schemas.py`: frozen, extra-forbidden `StudyValidationIssue(code, message, severity: REVIEW_REQUIRED|REJECTED)`, `StudyItemValidation(item_id, source_status: MATCHED|FAILED|NOT_CHECKED, support_status: SUPPORTED|REVIEW_REQUIRED|REJECTED|NOT_CHECKED, issues=())`, and `StudyValidationResult(workspace_id, study_format, resource_id=None, resource_digest=None, source_snapshot_digest=None, method='EXTRACTIVE_DEFINITION_V1', structure_status: VALID|INVALID, items=(), issues=())`. Derived `.status` VERIFIED/REVIEW_REQUIRED/REJECTED, `.release_ready`, Vietnamese `.message`. Internal receipts are service output, never client authority; Q01 SourceRefs remain UNVERIFIED.
- Pure stdlib `backend/algorithms/f2_study_validation.py`: frozen `ContentSupportDecision(status, code, message)`; `validate_quiz_support(question, options: Sequence[tuple[str,str]], correct_option_id, explanation, cited_sources, all_sources)` and `validate_flashcard_support(front, back, cited_sources, all_sources)`. Automatic support only for exact offline definition templates, preserving case/qualifiers/punctuation and normalizing whitespace. Requires literal unambiguity across all selected evidence; abstains on paraphrases/general questions, unsupported explanations/backs/distractors or irrelevant citations. Wrong template answer key is rejected, even when the wrong term appears in the true quote. Case-sensitive unit conflicts and whitespace-duplicate options also block support.
- `backend/services/f2_study_validation_service.py`: `F2StudyValidationService(repository).validate_quiz(quiz: QuizSet, *, workspace_id: str, context: SourceAccessContext) -> StudyValidationResult`; `.validate_flashcards(deck: FlashcardDeck, *, workspace_id, context)` analogous. `StudyValidationError(code,message)` rejects invalid backend context/workspace mismatch before reading. Q01 structural revalidation, denied-source checks via Q02, exact current passage reference membership (ID/version/hash/page/chunk/line/quote), known-injection checks, then independent support checks. Reprepares selected sources before return to detect visible changes; source/read failures fail closed. Source warnings, duplicate/conflicting prompts and count excess prevent release; no item is silently removed to turn a failed set into success.
- `study_resource_digest(resource: QuizSet|FlashcardDeck) -> str`: SHA-256 of revalidated canonical JSON including selection/key/explanation/references. Source digest covers current Q02 passages/issues/workspace/selection. Receipts are point-in-time, unkeyed bindings, not signed tokens or proof of raw file integrity; revalidate after edits/source changes and at use. Backend scope resolution/auth remains external. No atomic read, arbitrary semantic entailment, external truth checking or complete injection/contradiction detection is claimed.
- Verification: 78 focused tests; full `verify.py` 376 passed, AST 60 files, R2 PASS. Existing 298 tests unchanged, including F1/F3. Q01–Q04 source/tests retained. New gate is callable internally; generation/runtime/API/UI/practice do not invoke it automatically yet. See `docs/f2/F2-Q05_REPORT.md` for measured evidence and Q06 handoff; SQLite remains after MVP.

## F2-Q04 — 2026-11-12 Flashcard generation and shared study helpers
- `backend/algorithms/f2_definition_extraction.py`: pure-stdlib `extract_unambiguous_definitions(sources: Sequence[tuple[str, str]]) -> tuple[tuple[str, str, str], ...]` returns (source_id, term, definition) in source order; extracted from Q03 without changing its literal ambiguity/dedup rules.
- `backend/algorithms/f2_flashcard_generation.py`: `DEFAULT_MAX_BACK_WORDS = 60`; `build_definition_cards(sources, requested_count, *, max_back_words=60) -> list[dict[str, object]]`. Generates extractive term/definition front/back cards; one definition is enough, unlike Quiz distractors. Long answers are omitted, not truncated. Count and policy limit require positive integers.
- Shared `backend/providers/f2_study_provider.py`: frozen `StudyEvidence(source_id, kind, source_ref)`; `StudyProviderError(code, message)`; `format_study_evidence(evidence) -> str`; `OllamaStudyProvider(base_url, model, *, transport=None).generate_from_prompt(prompt) -> str`. Escaped line-labelled source frames, JSON mode, 60s read/2s connect, no redirects/retries and 1,000,000-byte cap.
- Shared `backend/services/f2_generation_support.py`: `StudyGenerationError(code, message)`, `prepare_generation_snapshot(prepared, required_format) -> (StudySourceSelection, tuple[StudyEvidence, ...])`, `parse_generation_items(raw, root_field) -> list`, `resolve_source_ids(ids, by_id) -> tuple[SourceRef, ...]`. Used by both generators; no auth or semantic verification implied.
- `backend/providers/f2_flashcard_provider.py`: FlashcardEvidence/FlashcardProviderError aliases to shared types, `FlashcardGenerationProvider` protocol, `DeterministicFlashcardProvider(*, max_back_words=60)`, `build_flashcard_prompt(evidence, requested_count, *, max_back_words=60)`, `OllamaFlashcardProvider(base_url, model, *, transport=None, max_back_words=60)`. Wire output is only cards/front/back/source_ids; no client/provider metadata accepted.
- `backend/services/f2_flashcard_service.py`: `F2FlashcardService(provider=None, *, fallback_provider=None, max_back_words=60).generate_flashcards(prepared) -> FlashcardGenerationResult`. Requires Flashcards format, maps source IDs to exact Q02 refs, validates front/back, deduplicates normalized prompts, removes all candidates with a literal conflicting answer for the same prompt, then limits count and assigns IDs. Never pads a shortage or silently cuts a long answer.
- Frozen `FlashcardGenerationIssue(code, message, card_index=None)` and `FlashcardGenerationResult(workspace_id, selection, deck, provider_name, issues=(), source_issues=(), failed=False)` expose COMPLETE/PARTIAL/INSUFFICIENT_CONTENT/ERROR plus recovery messages. `FlashcardGenerationError(code, message)` is raised for invalid prepared input/format before provider use. Source issues are retained.
- max_back_words=60 is configurable local generation policy for concise answers, not a new Q01 schema/product limit. Both service and offline adapter enforce it; align a separately configured Ollama provider prompt if overriding it.
- Q03 algorithm/provider/service now delegate shared mechanics to these helpers. Quiz public imports/signatures/error codes remain available; QuizEvidence and QuizProviderError are aliases to the shared types. Transport error text is generalized to study resources. Existing Q03 tests/report are unchanged; all 60 tests pass.
- Verification: 72 focused Flashcard tests, 60 Quiz regression tests; full verify 298 passed, AST 56 files, R2 PASS. F1/F3 and Q01/Q02 code/tests unchanged; see `docs/f2/F2-Q04_REPORT.md` for evidence and Q05 handoff. No live model evaluation, grading, study API/UI or SQLite; generated refs remain UNVERIFIED.

## F2-Q03 — 2026-11-12 Quiz generation (implemented, runtime not integrated)
- Pure stdlib `backend/algorithms/f2_quiz_generation.py`: `build_definition_questions(sources: Sequence[tuple[str, str]], requested_count: int) -> list[dict[str, object]]`. Offline extractive MCQs from unambiguous term/definition pairs; duplicate/conflicting terms or synonymous identical definitions excluded. Uses 2–4 existing source terms as options; no fabricated distractor facts.
- `backend/providers/f2_quiz_provider.py`: frozen `QuizEvidence(source_id: str, kind: str, source_ref: SourceRef)`; `QuizGenerationProvider` protocol (`name`, `generate(evidence: tuple[QuizEvidence, ...], requested_count: int) -> str`); `QuizProviderError(code, message)`.
- `DeterministicQuizProvider` is the offline default. `OllamaQuizProvider(base_url='http://localhost:11434', model='qwen2.5:7b', *, transport=None)` performs explicit JSON-mode, non-streamed Ollama generation on call only; read timeout 60s/connect 2s, no redirects/retries, HTTP response cap 1,000,000 bytes. Tests use MockTransport; no live model evaluation has run.
- `build_quiz_prompt(evidence, requested_count) -> str` HTML-escapes source text/attributes inside line-labelled `<untrusted_document_data>` blocks. Provider output is only a questions array with source_ids; metadata never comes back from the provider as source truth.
- `backend/services/f2_quiz_service.py`: `F2QuizService(provider=None, *, fallback_provider=None).generate_quiz(prepared: PreparedStudySources) -> QuizGenerationResult`. Revalidates/copies Q02 snapshots, requires Quiz format, maps S1/S2 aliases to exact original SourceRefs, assigns question/set IDs, rejects malformed JSON/duplicate keys/nonstandard constants, drops invalid/duplicate items and limits count. Source issues are preserved; no empty fake QuizSet is created.
- Frozen `QuizGenerationIssue(code: str, message: str, question_index: int | None=None)` and `QuizGenerationResult(workspace_id, selection, quiz: QuizSet | None, provider_name, issues=(), source_issues=(), failed=False)`; `.status` is COMPLETE/PARTIAL/INSUFFICIENT_CONTENT/ERROR, `.message` explains recovery. COMPLETE concerns count/structure only, not semantic verification. `QuizGenerationError(code, message)` rejects invalid input/format before provider use.
- Optional explicitly configured fallback is used only for PROVIDER_TIMEOUT/PROVIDER_UNAVAILABLE, records FALLBACK_USED and actual provider_name, and never masks invalid JSON/items. Default generation performs no network I/O.
- All generated SourceRefs remain UNVERIFIED. Internal QuizSet contains its answer key; Q05 validation and Q06/Q08 learner projection remain required before product use. No auth/live freshness recheck, grading, routes, UI or persistence added.
- At Q03 completion: `tests/test_f2_quiz_generation.py` 60 passed; full verify 226 passed, AST 49 files, R2 PASS. Q04 subsequently extracted shared helpers while retaining Quiz interfaces/behavior; see Q04 above for current verification. Q01/Q02 and F1/F3 retained. `docs/f2/F2-Q03_REPORT.md` remains the historical Q03 result/handoff.

## F2-Q02 — 2026-11-11 Source preparation (implemented, runtime not integrated)
- Pure stdlib `backend/algorithms/f2_source_extraction.py`: `StudySpanKind` (`definition`, `fact`, `example`, `procedure`); frozen `ExtractedStudySpan(kind, text, start_line, end_line)`; `extract_study_spans(text: str) -> tuple[ExtractedStudySpan, ...]`. Relative lines are inclusive/1-based; quotes are verbatim. Textual eligibility is not semantic verification.
- `backend/services/f2_source_service.py` accepts an explicit `StudySourceRepository` protocol: readonly `documents: Mapping[str, DocumentMetadata]` and `get_document_chunks(doc_id: str) -> Sequence[DocumentChunk]`. No singleton/default repository or runtime registration.
- Frozen `SourceAccessContext(workspace_id: str, allowed_doc_ids: frozenset[str])` must come from trusted backend workspace/permission resolution, not request-body claims. Context is not authentication.
- Frozen `StudySourcePassage(kind: StudySpanKind, source_ref: SourceRef)` exposes `.text` as its quote. Frozen `SourceContentIssue(doc_id, code, message, chunk_id=None)` codes: `NO_USABLE_CONTENT`, `SUSPICIOUS_SOURCE_CONTENT`.
- Frozen `PreparedStudySources(workspace_id, selection, passages: tuple[StudySourcePassage, ...], issues: tuple[SourceContentIssue, ...])` exposes `.status` (`READY`, `PARTIAL`, `INSUFFICIENT_CONTENT`) and Vietnamese `.message`. READY indicates eligible source spans exist, not enough supported items for the requested count.
- `F2SourceService(repository).prepare_sources(selection: StudySourceSelection, *, context: SourceAccessContext) -> PreparedStudySources`; revalidates selection, rejects denied IDs before repository access, reads exact stored metadata (not list_documents' orphan fallback), filters alias/case chunks, checks version/hash/line consistency and copies source snapshots. Duplicate same-location overlap is removed. Metadata is checked again before return; no atomic transaction is claimed.
- `SourcePreparationError(code: str, message: str, doc_ids: tuple[str, ...] = ())` codes: `INVALID_SELECTION`, `INVALID_CONTEXT`, `FORBIDDEN_SOURCE`, `SOURCE_NOT_FOUND`, `INVALID_PROVENANCE`, `SOURCE_INCONSISTENT`, `SOURCE_READ_FAILED`, `SOURCE_CHANGED`. Invalid/changed source metadata fails the request; unusable text yields explicit content issues/results.
- All SourceRefs remain UNVERIFIED. Known prompt-injection patterns are skipped using existing guardrails; accepted text is still untrusted data and must be framed appropriately by Q03/Q04 providers.
- Tests: `tests/test_f2_source_service.py`, 55 cases including actual DocumentService ingestion, filename/version alias isolation, sparse page numbers and long overlapping chunks. Full verify: 166 passed, AST 45 files, R2 PASS.
- At the Q02 handoff, Q03 Quiz generation was next and study generators were absent; see Q03 above for current Quiz status. Semantic grounding, grading, study API/UI and SQLite remain absent. See `docs/f2/F2-Q02_REPORT.md` for source-layer limits. User manual end-to-end testing is deferred until the F2-Q0x sequence is complete; automated checks continue per task.

## F2-Q01 — 2026-11-11 Data Contracts (implemented, runtime not integrated)
- Module: `backend/core/f2_study_schemas.py`; tests: `tests/test_f2_study_schemas.py`. No new public functions or runtime registration.
- `StudyFormat(str, Enum)`: `QUIZ='quiz'`, `FLASHCARDS='flashcards'`.
- `SourceRef`: `doc_id: str`, `doc_version: str`, `doc_hash: str` (64 lowercase hex characters), `page_number: int`, `chunk_id: str`, `start_line: int`, `end_line: int`, `evidence_quote: str`, `verification_status: Literal['UNVERIFIED'] = 'UNVERIFIED'`. Page/lines are positive strict integers, inclusive; end >= start. Provenance syntax does not prove factual support or live source identity.
- `StudySourceSelection`: `selected_doc_ids: tuple[str, ...]` (nonempty, exact unique IDs), `study_format: StudyFormat`, `requested_count: int = 10` (positive strict integer). Workspace authorization remains external.
- `QuizOption`: `option_id: str`, `text: str`.
- `QuizQuestion`: `question_id: str`, `question: str`, `options: tuple[QuizOption, ...]` (>=2), `correct_option_id: str`, `explanation: str`, `source_refs: tuple[SourceRef, ...]` (>=1). Unique option IDs/texts after strip/casefold; exactly one existing option ID as key. Internal model includes the key; future learner API must use a separate projection.
- `QuizSet`: `quiz_set_id: str`, `selection: StudySourceSelection`, `questions: tuple[QuizQuestion, ...]` (>=1). Requires quiz format, unique question IDs, exact selected source IDs and consistent version/hash per document.
- `Flashcard`: `card_id: str`, `front: str`, `back: str`, `source_refs: tuple[SourceRef, ...]` (>=1).
- `FlashcardDeck`: `deck_id: str`, `selection: StudySourceSelection`, `cards: tuple[Flashcard, ...]` (>=1). Requires flashcards format, unique card IDs and the same source/snapshot constraints as QuizSet.
- All models forbid extra fields, are frozen, and revalidate nested instances at validation boundaries. Collections accept ordered lists/tuples and become tuples; identifiers reject surrounding whitespace and remain case-sensitive. Required prose/quotes reject whitespace-only input and otherwise remain verbatim. Do not use Pydantic `model_construct`/`model_copy(update=...)` on untrusted data to bypass validation.
- Result size need not equal requested_count; content sufficiency/partial messaging is a service responsibility. At the Q01 handoff, Q02 source extraction, generators, semantic grounding, grading, API/UI and SQLite were unimplemented; see the Q02 entry for current source-preparation status.
- Verification: 81 focused tests; full `verify.py` 111 passed, AST 42 files, R2 gate passed. See `docs/f2/F2-Q01_REPORT.md` for AC/test mapping and next-task handoff.

## F2-Q00 — 2026-11-11 preparation status
- New scope: **Document-Based Quiz & Flashcard Generation**, FR2.01–FR2.05. Single-choice quiz, default 10 questions/cards; SQLite after the MVP flow.
- Q00 changes documentation only. No study schemas, services, APIs, algorithms, UI or public functions have been implemented.
- Read `docs/f2/F2-Q00_REPORT.md` for measured baseline/interfaces and `docs/f2/F2-Q01_TASK_CONTEXT_PACKET.md` before Q01 Data Contracts.
- Legacy `f2_schemas.py`/task SQLite work remains untouched in `D:\Projects\WorkSpaceAI` on `feat/f2-document-task-management`; it is not present in this branch and must not be copied into study contracts.
- Shared `DocumentChunk` has provenance fields, but `WorkspaceRepository.get_document_chunks`/`search` allow document-name aliases. F2 Q02 must explicitly enforce exact source identity/scope; do not assume the shared calls authenticate a workspace.
- React/Vite under `frontend/src/` coexists with Streamlit; its current demo/localStorage UI is not an integrated study backend. Q01 does not change either frontend.

## 1. Architecture & Layer Map
- `backend/core/`: Schemas (`schemas.py`), Configuration (`config.py`), Security Guardrails (`guardrails.py`).
- `backend/algorithms/`: Pure Python Stdlib (R2 deterministic logic: Citation Verifier, Email FSM, Reconciliation).
- `backend/repositories/`: Local in-memory indexing, BM25 + Dense RRF (`workspace_repository.py`), Email staging (`draft_repository.py`).
- `backend/providers/`: Local embeddings (`embedding_provider.py`), LLM interfaces (`llm_provider.py`), Prompt templates (`prompts.py`).
- `backend/services/`: Ingestion (`document_service.py`), Grounded Q&A (`qa_service.py`), Reconciliation (`reconciliation_service.py`), Email (`email_service.py`), Intent routing (`router_service.py`).
- `backend/api/`: FastAPI routers (`chat_routes.py`, `document_routes.py`, `email_routes.py`).
- `frontend/`: Modular Streamlit app (`app.py`, `state.py`, `styles.py`, `components/*`).

---

## 2. Core Pydantic Schemas (`backend/core/schemas.py`)
- `RouteType(str, Enum)`: `QA_FLOW`, `RECONCILE_FLOW`, `EMAIL_FLOW`, `CLARIFICATION_FLOW`, `REJECTED_SAFEGUARD`
- `EmailFSMState(str, Enum)`: `DRAFT`, `APPROVED`, `SENT`, `FAILED`, `DELIVERY_UNKNOWN`
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
- `EmailDraftRecord`: `id: UUID, workspace_id: UUID, recipients: Union[List[str], str], subject: str, body: str, fsm_state: EmailFSMState, sha256_digest: Optional[str], audit_timestamp: datetime, citations: List[str]`
- `CreateDraftRequest`: `workspace_id: UUID, recipients: Union[List[str], str], subject: str, body: str, citations: Optional[List[str]]`
- `ApproveDraftRequest`: `recipients: Optional[Union[List[str], str]], subject: Optional[str], body: Optional[str], user_confirmed: bool`
- `EmailDraftPayload`: `draft_id: str, recipient_email: str, subject: str, body: str, attachment_ids: List[str], citations: List[str], state: EmailState, payload_hash: str, fsm_state: Optional[EmailFSMState], audit_timestamp: Optional[datetime]`
- `EmailApproveRequest`: `recipient_email: str, subject: str, body: str, user_confirmed: bool`
- `UserRequest`: `query: str, selected_doc_ids: Optional[List[str]], recipient_email: Optional[str], reference_date: date, conversation_history: List[Dict[str, str]]`
- `DocumentSelectRequest`: `selected_doc_ids: List[str]`

---

## 3. Public Function Signatures

### Algorithms (`backend/algorithms/`) — 100% Pure Stdlib
- `citation_verifier.verify_citations(claims: Sequence[Union[CitationClaim, Any]], chunk_lookup: Dict[Any, Any], theta_match: float = 0.75) -> CitationVerificationResult`
- `reconciliation.reconcile_requirements_and_tasks(requirements: List[Any], tasks: List[Any], t_now: date) -> ReconciliationSummary`
- `email_state_machine.validate_rfc5322_email(email: str) -> bool`
- `email_state_machine.compute_draft_hash(recipients: Any, subject: str = "", body: str = "", attachments: Optional[Sequence[str]] = None) -> str`
- `email_state_machine.approve_snapshot(recipients: Any, subject: str, body: str, user_confirmed: bool = True) -> Tuple[str, str]`
- `email_state_machine.verify_and_lock_for_send(current_state: str, expected_digest: str, recipients: Any, subject: str, body: str) -> bool`
- `email_state_machine.prepare_draft_for_approval(draft: Any) -> Any`
- `email_state_machine.approve_and_verify_email_send(stored_draft: Any, approved_recipient: str, approved_subject: str, approved_body: str, approved_attachments: Optional[List[str]] = None, user_confirmed: bool = True) -> Any`

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
  - `save(draft: Union[EmailDraftRecord, EmailDraftPayload, Any]) -> Any`
  - `get(draft_id: Union[UUID, str]) -> Optional[Any]`
  - `list_by_workspace(workspace_id: Union[UUID, str]) -> List[Any]`
  - `list_all() -> List[Any]`
  - `delete(draft_id: Union[UUID, str]) -> bool`
  - `clear() -> None`

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
  - `create_draft(workspace_id=..., recipients=..., subject=..., body=..., citations=...) -> EmailDraftRecord`
  - `approve_draft_snapshot(draft_id, recipients=..., subject=..., body=..., user_confirmed=True) -> EmailDraftRecord`
  - `dispatch_email(draft_id) -> Dict[str, Any]`
  - `approve_and_send(draft_id, recipient_email, subject, body, user_confirmed=True) -> Dict[str, Any]`
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
