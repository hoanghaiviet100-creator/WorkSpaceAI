# WorkspaceAI UI Mockup Design & Localization Specifications

This document defines the interface layout and prompt specifications for the three core feature mockups in WorkspaceAI, aligned with the 15 Functional Requirements (FRs), CSC10014 baseline, and pure Python verification pipeline.

---

## Feature 1: Evidence-Grounded Q&A (`feature-1-4-en.png`)

### Layout Specification (Tripartite View)
- **Left Panel (Source Library):**
  - Workspace title: "PROJECT TEAM 01 · Study Workspace"
  - Active course: "Systems Analysis & Design · Semester 1, 2026"
  - Source list showing uploaded documents:
    - `Chapter 2 - Requirements Analysis.pdf` (Active, 18 pages)
    - `Project_Rubric_v2.pdf` (Active, 6 pages)
  - Action buttons: "Upload Document (+)" and trash/delete icons per source.
- **Center Panel (Conversational Chat Stream):**
  - Section title: "Ask Sources" (Subtitle: "Source-grounded answers with deterministic citation verification")
  - User query card: *"How do functional and non-functional requirements differ in our project rubric?"*
  - Grounded Assistant response card:
    - Structured answer strictly quoting source definitions.
    - Explicit inline citation badges: `[Chapter 2, Page 8, Line 14]` and `[Rubric v2, Page 2]`.
    - Verification badge: *"Verified against active sources (SHA-256 locator match)"*.
  - Input area at bottom: *"Ask a follow-up question scoped to selected sources..."*
- **Right Panel (Evidence Viewer):**
  - Header: "Inspect Supporting Evidence"
  - Source context: `Chapter 2 - Requirements Analysis.pdf (Page 8)`
  - Exact highlighted passage in yellow/blue box matching the inline citation span.
  - Action button: "Open full document view".

### Generation Prompt
```text
UI mockup design for WorkspaceAI desktop web application, modern clean SaaS aesthetic, Figma-style 16:9 layout. Left sidebar: Project navigation ('Overview', 'Documents', 'Ask Sources', 'Tasks', 'Email Report') and Document Library listing 'Chapter 2 - Requirements Analysis.pdf' and 'Project_Rubric_v2.pdf' with active checkboxes. Center main panel: Chat conversation stream titled 'Ask Sources', showing a user question 'How do functional and non-functional requirements differ?' and an AI response containing structured paragraphs with clickable blue inline citation tags '[Chapter 2, p.8]' and a green badge 'Citations Verified'. Right drawer panel: 'Evidence Viewer' showing the exact highlighted source paragraph with metadata 'Chapter 2, Page 8, Lines 14-22'. Crisp typography, white and light slate gray background (#F8FAFC), indigo accents (#4F46E5), no mind maps, no flashcards, no quizzes.
```

---

## Feature 2: Document-Driven Progress Management (`feature-2-4-en.png`)

### Layout Specification (Kanban + Reconciliation Drawer)
- **Top Header:**
  - Page title: "Team Tasks & Progress Board"
  - Subtitle: "Track sprint deliverables grounded in verified project requirements."
  - Action buttons: "+ New Task", "Extract from Documents", and "Run Reconciliation" (highlighted primary button).
  - Filter bar: Filter by Assignee ("All Members", "Alice", "Bob") and Status ("All Statuses").
- **Center View (Kanban Board):**
  - Three columns:
    - **To Do (2):**
      - Card 1: "Complete use case specifications" · Deadline: Nov 10 · Assignee: Minh · Link: `[Rubric §2.1]`
      - Card 2: "Configure local Ollama testbed" · Deadline: Nov 12 · Assignee: Duy · Link: `[Architecture §3]`
    - **In Progress (1):**
      - Card 3: "Implement hybrid retrieval (BM25 + RRF)" · Deadline: Nov 05 · Assignee: Viet · Link: `[Brief §4]`
    - **Done (3):**
      - Card 4: "Draft Chapter 1 introduction" · Completed Nov 01 · Assignee: Khiem
  - Drag-and-drop handles and status indicators.
- **Right Drawer (Reconciliation Findings):**
  - Header: "Automated Reconciliation Findings" (Reference date: Nov 02, 2026)
  - Finding 1 (Warning - Uncovered Requirement): *"Requirement R-04 ('Deterministic citation verification') has no linked Kanban task."*
  - Finding 2 (Alert - Deadline Conflict): *"Task 'Complete use case specifications' has deadline Nov 10, but Rubric v2 §2 mandates Nov 08."*
  - Finding 3 (Alert - Overdue): *"Task 'Review non-functional requirements' was due Oct 30."*
  - Action link: "Export findings to Email Report".

### Generation Prompt
```text
UI mockup design for WorkspaceAI Task Board and Progress Reconciliation, modern web app interface. Top header displays 'Team Tasks & Progress', with filter dropdowns for Assignee and Status, and action buttons '+ New Task', 'Extract from Docs', and a prominent blue button 'Run Reconciliation'. Main area shows a clean 3-column Kanban board: 'To Do', 'In Progress', 'Done' containing task cards with assignees, dates, and source requirement tags. On the right, an open drawer panel titled 'Reconciliation Findings' with reference date '2026-11-02' displays 3 audit alerts with source citations: 'Uncovered Requirement: R-04', 'Deadline Conflict: Rubric Nov 8 vs Task Nov 10', and 'Overdue Task: Due Oct 30'. Modern Tailwind UI aesthetic, subtle card shadows, no learning progress tabs, no priority filters.
```

---

## Feature 3: Context-Aware Email Reporting (`feature-3-4-en.png`)

### Layout Specification (Composer + Approval Gate + Audit Log)
- **Top Header:**
  - Page title: "Progress Email Reporting"
  - Subtitle: "Human-in-the-loop email dispatch grounded in verified project milestones."
  - Action toggle: "Synthesize from Findings" | "Compose Manually"
- **Center Area (Email Composer & Snapshot Approval):**
  - Recipient field: `dr.an.nguyen@hcmus.edu.vn` (green checkmark: Valid RFC-5322)
  - Subject field: `[CSC10014] Team 01 - Weekly Milestone & Discrepancy Progress Report`
  - Body Editor:
    - Structured progress summary: Completed deliverables, current sprint tasks, and verified findings with citation markers `[Finding #2, Rubric p.2]`.
  - **Prominent Approval Banner:**
    - Background: Soft green / amber container.
    - State Badge: `APPROVED` (Green pill).
    - Integrity Hash: `Snapshot SHA-256: 7f83b165...e92a` (Cryptographically locked).
    - Notice: *"Payload locked. Any modification immediately revokes approval and recalculates hash."*
  - **Action Button Bar:**
    - Button 1: "Approve Snapshot" (Outlined).
    - Button 2: **"Send Email via SMTP"** (Solid Primary Blue, enabled only when state is `APPROVED`).
- **Bottom Panel (Transmission Audit Log):**
  - Header: "Transmission Audit History"
  - Table columns: `Timestamp`, `Recipient`, `Subject`, `Payload SHA-256`, `Dispatch State`, `SMTP Response`.
  - Row 1: `2026-10-30 14:15` · `dr.an.nguyen@hcmus.edu.vn` · `Milestone Report` · `7f83b1...` · `SENT` · `250 2.0.0 OK (Gmail SMTP port 587 STARTTLS)`.

### Generation Prompt
```text
UI mockup design for WorkspaceAI Email Reporting system with human-in-the-loop snapshot approval. Main screen shows an email composition form with verified recipient 'dr.an.nguyen@hcmus.edu.vn', subject '[CSC10014] Team 01 Progress Report', and a grounded body containing milestone findings with citation references. Above the send button is a prominent 'Snapshot Approval Banner' displaying state 'APPROVED' in green and cryptographic digest 'SHA-256: 7f83b1657c90...'. Below the editor are two distinct buttons: 'Approve Snapshot' and 'Send Email via SMTP (Port 587)'. At the bottom of the page is a 'Transmission Audit Log' table displaying timestamps, SHA-256 hashes, and transmission receipts marked 'SENT: 250 2.0.0 OK'. Clean, secure enterprise-grade SaaS design, white and navy blue palette.
```
