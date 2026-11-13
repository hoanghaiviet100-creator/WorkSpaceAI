# WorkspaceAI System Codebase Map (v2.5)
> Rapid context reference for AI Agents: Module layout, Pydantic schemas, and public function signatures.

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
