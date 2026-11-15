# WorkspaceAI — Kiến Trúc Hệ Thống & Quy Trình Hoạt Động (Workflows)

> **Môn học**: Tư duy tính toán (CSC10014) — Track C: Intelligent Document Workspace with Evidence Grounding  
> **Trường Đại học Khoa học Tự nhiên, ĐHQG-HCM (HCMUS)**  
> **Phiên bản hệ thống**: v2.5 Enterprise  

---

## 1. Tổng Quan Đường Ống CSC10014 Pipeline

Mọi yêu cầu từ người dùng (truy vấn tài liệu, kiểm tra tiến độ, soạn email) đều tuân thủ nghiêm ngặt chu trình 7 bước tính toán:

```mermaid
flowchart LR
    A["1. REQUEST\n(Yêu cầu người dùng)"] --> B["2. UNDERSTAND\n(Phân tích & Guardrail)"]
    B --> C["3. ROUTE\n(Điều phối luồng)"]
    C --> D["4. RETRIEVE / COMPUTE\n(BM25/Dense RRF / R2)"]
    D --> E["5. REASON\n(Ollama Qwen2.5 / Gemini)"]
    E --> F["6. VERIFY\n(Kiểm định trích dẫn & FSM)"]
    F --> G["7. RESPOND / ACT\n(Phản hồi & Gmail SMTP)"]
```

| Bước Pipeline | Thành phần phụ trách | Mô tả chi tiết |
| :--- | :--- | :--- |
| **1. REQUEST** | `frontend/components/chat_panel.py` | Tiếp nhận câu hỏi, văn bản tải lên, tập tài liệu đã chọn (`selected_doc_ids`), ngày mốc tham chiếu (`reference_date`). |
| **2. UNDERSTAND** | `backend/core/guardrails.py` | Quét kiểm tra prompt injection, bao đóng tài liệu trong thẻ `<untrusted_document_data>`, chuẩn hóa truy vấn. |
| **3. ROUTE** | `backend/services/router_service.py` | Phân loại ý định thành: `QA_FLOW`, `RECONCILE_FLOW`, `EMAIL_FLOW`, `CLARIFICATION_FLOW`, `REJECTED_SAFEGUARD`. |
| **4. RETRIEVE / COMPUTE** | `backend/repositories/workspace_repository.py` & `backend/algorithms/` | Truy xuất kết hợp Hybrid RRF (BM25 + Dense) hoặc thực thi thuật toán đối soát thuần Python Standard Library. |
| **5. REASON** | `backend/providers/llm_provider.py` | Kích hoạt LLM (Local Ollama Qwen2.5-7B hoặc Gemini API) sinh câu trả lời có cấu trúc JSON kèm trích dẫn gốc. |
| **6. VERIFY** | `backend/algorithms/citation_verifier.py` & `email_state_machine.py` | Thuật toán R2 đối soát 4 cấp độ kiểm tra từng claim; tính Grounding Score; băm SHA-256 payload email. |
| **7. RESPOND / ACT** | `backend/api/` & `frontend/` | Trả về kết quả có bằng chứng highlight trên Evidence Viewer hoặc kích hoạt gửi email sau khi người dùng ký duyệt. |

---

## 2. Kiến Trúc Phân Lớp (Layered Architecture)

```mermaid
graph TD
    subgraph UI ["Tầng Trình Diễn (Frontend - Streamlit / Web)"]
        UI_Sidebar["Sidebar Document Library\n(Upload PDF/TXT/CSV & Lọc nguồn)"]
        UI_Chat["Chat Panel & Intent Router\n(Hội thoại & Gợi ý ngữ cảnh)"]
        UI_Evidence["Evidence Viewer\n(Highlight trực quan trích dẫn)"]
        UI_Kanban["Reconciliation Board\n(Ma trận công việc & Mâu thuẫn)"]
        UI_Email["Email Assistant Dialog\n(Kiểm duyệt & Ký duyệt SHA-256)"]
    end

    subgraph API ["Tầng Giao Diện Lập Trình (FastAPI REST Routes)"]
        API_Chat["/api/chat/query"]
        API_Doc["/api/documents/upload & /list"]
        API_Email["/api/email/approve & /send"]
    end

    subgraph CoreServices ["Tầng Nghiệp Vụ & Điều Phối (Services)"]
        S_Router["RouterService\n(Phân loại ý định & Slot-filling)"]
        S_Doc["DocumentService\n(Line-level Chunking & Hashing)"]
        S_QA["QAService\n(Contextual Expansion & Hybrid RAG)"]
        S_Recon["ReconciliationService\n(Chiết xuất & Đánh giá rủi ro)"]
        S_Email["EmailService\n(Soạn thảo & Gmail SMTP Adapter)"]
    end

    subgraph PureR2 ["Tầng Thuật Toán Tất Định (Pure Python Stdlib R2 - 100% Deterministic)"]
        R2_Citation["Citation Verifier\n(Exact, Substring, LCS, Token Jaccard)"]
        R2_Recon["Reconciliation Logic\n(Bipartite matching & Conflict Detector)"]
        R2_FSM["Email FSM & Tamper Protection\n(SHA-256 Digest & HMAC Verification)"]
    end

    subgraph AI_Providers ["Tầng Nhà Cung Cấp Mô Hình (Providers)"]
        P_Ollama["Local Ollama Provider\n(Qwen2.5:7b @ localhost:11434)"]
        P_Gemini["Cloud Gemini Provider\n(gemini-flash-lite Fallback)"]
        P_Embed["Embedding Provider\n(nomic-embed-text / NumPy)"]
    end

    subgraph DataLayer ["Tầng Dữ Liệu & Lưu Trữ (Data / Repository)"]
        Repo_Mem["WorkspaceRepository (In-Memory / BM25Okapi / Vector Cache)"]
        Repo_SQL["SQLite Local-First Database (workspace_ai.db)\n12 Quan hệ chuẩn hóa & Zero-Config"]
    end

    UI --> API
    API --> CoreServices
    CoreServices --> PureR2
    CoreServices --> AI_Providers
    CoreServices --> DataLayer
    DataLayer --> Repo_SQL
```

---

## 3. Chi Tiết Quy Trình Nghiệp Vụ Chính (Core Workflows)

### 3.1. Workflow 1: Hỏi Đáp Có Căn Cứ Dẫn Chứng (Evidence-Grounded Q&A)

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant UI as Chat Panel & Evidence Viewer
    participant API as FastAPI Router
    participant Service as QAService
    participant Repo as WorkspaceRepository
    participant LLM as Ollama Qwen2.5-7B
    participant Verifier as Citation Verifier (R2)

    User->>UI: Nhập câu hỏi (Ví dụ: "Hạn nộp báo cáo giữa kỳ là ngày nào?")
    UI->>API: POST /api/chat/query (kèm selected_doc_ids, ref_date)
    API->>Service: answer_question()
    Service->>Repo: search(query, top_k=5, selected_doc_ids)
    Note over Repo: Kết hợp BM25Okapi + Dense Cosine (RRF)<br/>Áp dụng Pinpoint Reranker (khớp ngày tháng/con số)
    Repo-->>Service: Danh sách Top DocumentChunk (kèm số trang, dòng bắt đầu - kết thúc)
    Service->>LLM: Gửi Prompt đóng gói XML <untrusted_document_data> (Format JSON)
    LLM-->>Service: Phản hồi JSON: {answer, citations: [{doc_id, page, line_start, line_end, excerpt}]}
    Service->>Verifier: verify_citations(claims, chunk_lookup, theta_match=0.75)
    Note over Verifier: Kiểm định 4 cấp độ:<br/>1. Exact Match (1.0)<br/>2. Substring Match (0.95)<br/>3. Longest Common Subsequence (LCS)<br/>4. Token Jaccard / Fuzzy Match<br/>Phát hiện Out-of-bounds hoặc sai lệch mã Hash
    Verifier-->>Service: CitationVerificationResult (validated_claims, hallucination_flags, grounding_score)
    Service-->>API: Phản hồi hoàn chỉnh kèm căn cứ kiểm định
    API-->>UI: Hiển thị câu trả lời + Huy hiệu trích dẫn (Citation Badges)
    User->>UI: Nhấp vào huy hiệu trích dẫn [Project_Brief.pdf, Trang 6, Dòng 10-15]
    UI->>UI: Mở Evidence Viewer & Highlight vàng đoạn văn gốc trên trang tài liệu
```

---

### 3.2. Workflow 2: Quản Lý & Đối Soát Tiến Độ Đồ Án (Progress Reconciliation)

```mermaid
sequenceDiagram
    autonumber
    actor User as Nhóm dự án / Leader
    participant UI as Reconciliation Board
    participant Service as ReconciliationService
    participant R2 as Reconciliation Algorithm (Pure Python)
    participant DB as Database / Task Store

    User->>UI: Chọn ngày mốc tham chiếu (Ví dụ: 10/11/2026)
    User->>UI: Nhấn "Chạy đối soát tiến độ" (Run Reconciliation)
    UI->>Service: reconcile(reference_date)
    Service->>DB: Lấy danh sách Requirements (từ đề bài) và Tasks (từ Kanban/CSV)
    Service->>R2: reconcile_requirements_and_tasks(requirements, tasks, t_now)
    Note over R2: Tính toán tất định:<br/>1. Ánh xạ lưỡng phân (Bipartite Mapping) dựa trên req_id hoặc keywords<br/>2. Tính tiến độ trung bình: avg_completion = Sum(completion_pct) / N<br/>3. Phân loại trạng thái: FULLY_COVERED, PARTIALLY_COVERED, NOT_COVERED<br/>4. Kiểm tra quá hạn: days_remaining = official_deadline - t_now<br/>5. Phát hiện mâu thuẫn: logged_deadline != official_deadline
    R2-->>Service: ReconciliationSummary (coverage_ratio, overdue_count, conflict_count, item_reports)
    Service-->>UI: Hiển thị bảng ma trận đối soát:
    Note over UI: - Cảnh báo thẻ đỏ: Quá hạn hoặc Mâu thuẫn ngày nộp<br/>- Cảnh báo thẻ vàng: Thiếu người phụ trách hoặc Chưa đủ task<br/>- Thẻ xanh: Đã hoàn thành 100% đúng hạn
```

---

### 3.3. Workflow 3: Soạn & Gửi Báo Cáo Email Có Giám Sát (Human-in-the-Loop Email Reporting)

```mermaid
sequenceDiagram
    autonumber
    actor User as Người dùng
    participant UI as Email Assistant Dialog
    participant FSM as Email State Machine (R2)
    participant Service as EmailService
    participant SMTP as Gmail SMTP Server (STARTTLS:587)

    User->>UI: Chọn các mục đối soát cần báo cáo -> Nhấn "Soạn Email Tiến Độ"
    UI->>Service: prepare_draft(query, chunks, recipient_email)
    Service->>FSM: prepare_draft_for_approval(draft)
    Note over FSM: Sinh payload_hash = SHA256(recipient|subject|body)<br/>Khởi tạo trạng thái: PENDING_APPROVAL
    FSM-->>Service: EmailDraftPayload
    Service-->>UI: Mở hộp thoại Preview nội dung email
    
    alt Người dùng chỉnh sửa nội dung sau khi duyệt
        User->>UI: Thay đổi người nhận / tiêu đề / nội dung
        UI->>FSM: Kiểm tra payload_hash
        Note over FSM: Phát hiện Hash không khớp! Thu hồi cờ APPROVED -> Quay về PENDING_APPROVAL
    end

    User->>UI: Tích chọn checkbox "Tôi xác nhận nội dung chính xác" & Nhấn "KÝ DUYỆT & GỬI"
    UI->>Service: send_email(draft_id, recipient, subject, body, user_confirmed=True)
    Service->>FSM: approve_and_verify_email_send(...)
    Note over FSM: Xác minh 3 lớp bảo vệ:<br/>1. user_confirmed == True<br/>2. payload_hash khớp 100% nội dung phê duyệt<br/>3. Chuyển trạng thái FSM: PENDING_APPROVAL -> APPROVED -> SENT
    FSM-->>Service: Cho phép phát lệnh gửi (Authorized)
    Service->>SMTP: Kết nối SMTP Gmail, xác thực TLS và gửi thư thực tế
    SMTP-->>Service: 250 OK (Email Delivered)
    Service-->>UI: Thông báo "Gửi email báo cáo thành công!" kèm mã định danh và Audit Log
```

---

## 4. Máy Trạng Thái Hữu Hạn Email (Email Finite State Machine)

Hệ thống bảo vệ chuyển trạng thái email nghiêm ngặt nhằm triệt tiêu nguy cơ gửi nhầm hoặc AI tự ý gửi thư:

```mermaid
stateDiagram-v2
    [*] --> IDLE: Khởi tạo hệ thống
    IDLE --> AWAITING_CLARIFICATION: Thiếu thông tin người nhận / ngữ cảnh
    AWAITING_CLARIFICATION --> PENDING_APPROVAL: Bổ sung đầy đủ thông tin
    IDLE --> PENDING_APPROVAL: Sinh xong bản nháp có căn cứ
    
    state PENDING_APPROVAL {
        [*] --> Draft_Review
        Draft_Review --> Hash_Computed: Tính SHA-256 Digest
    }

    PENDING_APPROVAL --> PENDING_APPROVAL: Người dùng chỉnh sửa (Tự động cập nhật lại Hash)
    PENDING_APPROVAL --> APPROVED: Người dùng tích chọn xác nhận & Ký duyệt
    
    APPROVED --> PENDING_APPROVAL: Bất kỳ chỉnh sửa nào sau khi duyệt (Tamper Detection)
    APPROVED --> SENT: Gửi thành công qua Gmail SMTP (TLS 587)
    APPROVED --> FAILED_RETRYABLE: Mất mạng hoặc lỗi SMTP xác thực
    FAILED_RETRYABLE --> APPROVED: Thử gửi lại thành công
    FAILED_RETRYABLE --> PENDING_APPROVAL: Chỉnh sửa lại cấu hình
    SENT --> [*]: Lưu trữ Audit Log bất biến
```

---

## 5. Quy Chuẩn Đóng Gói & Triển Khai (Deployment Architecture)

```mermaid
graph LR
    subgraph Host ["Máy Cục Bộ / Máy Chủ Đồ Án"]
        subgraph DockerCompose ["Docker Compose Stack"]
            AppContainer["workspaceai-app\n(FastAPI :8000 + Streamlit :8501)\n+ SQLite Embedded (workspace_ai.db)"]
            OllamaContainer["workspaceai-ollama\n(Qwen2.5:7b :11434)"]
        end
        ClientBrowser["Trình Duyệt Người Dùng\n(Chrome / Edge / Firefox)"]
        GmailServer["Google Gmail SMTP Server\n(smtp.gmail.com:587 STARTTLS)"]
    end

    ClientBrowser -->|HTTP :8501| AppContainer
    AppContainer -->|Internal HTTP :11434| OllamaContainer
    AppContainer -->|SMTP TLS :587| GmailServer
```

Hệ thống hoàn toàn độc lập, đảm bảo quyền riêng tư dữ liệu học thuật (Local-First Privacy), không rò rỉ đề bài hay thông tin nội bộ của nhóm sinh viên ra ngoài Internet.
