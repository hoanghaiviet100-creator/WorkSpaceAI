import type {
  DocumentPageRow,
  EmailAuditRow,
  EmailState,
  EngineMode,
  RequirementRow,
  ReconciliationRunRow,
  ReconciledItemRow,
  VerificationStatus,
  RouteType,
  TaskState,
} from "./schema";
export type Mode = "Ask" | "Tasks" | "Email";
export type View = "chat" | "email";
export type Source = {
  id: string;
  name: string;
  kind: string;
  detail: string;
  status: string;
  selected: boolean;
  limitation?: string;
  fileHash?: string;
  fileSizeBytes?: number;
  versionId?: string;
  totalPages?: number;
  totalLines?: number;
  totalChunks?: number;
  mimeType?: string;
  uploadedAt?: string;
  updatedAt?: string;
  pages?: DocumentPageRow[];
  origin?: "sample" | "local" | "server";
  sourceUrl?: string;
};
export type EvidenceKey = string;
export type Evidence = {
  file: string;
  locator: string;
  title: string;
  quote: string;
  context: string;
  id: string;
  finding: string;
  claimId?: string;
  messageId?: string;
  page?: number;
  startLine?: number;
  endLine?: number;
  verificationStatus?: VerificationStatus;
  matchScore?: number;
  matchedSpan?: string;
  docVersion?: string;
  docHash?: string;
  verifiedAt?: string;
  origin?: "sample" | "server";
};
export type Task = {
  id: string;
  title: string;
  description: string;
  owner: string;
  initials: string;
  due: string;
  status: TaskState;
  flag?: string;
  source?: string;
  secondarySource?: string;
  mappedReqId?: string;
  completionPct?: number;
  sourceRef?: string;
  createdAt?: string;
  updatedAt?: string;
  localLabel?: string;
  archived?: boolean;
};
export type Suggestion = {
  id: string;
  title: string;
  description: string;
  owner: string;
  due: string;
  status?: TaskState;
  selected: boolean;
  source?: string;
  threadId?: string;
  mappedReqId?: string;
  completionPct?: number;
};
export type Draft = {
  serverCitations?: string[];
  to: string;
  cc: string;
  subject: string;
  body: string;
  purpose: string;
  tone: string;
  evidenceIds: string[];
  context?: string;
  id?: string;
  sessionId?: string;
  attachmentIds?: string[];
  currentState?: EmailState;
  payloadHash?: string;
  hmacSignature?: string;
  auditLogs?: EmailAuditRow[];
  createdAt?: string;
  updatedAt?: string;
  sentAt?: string;
  origin?: "local" | "server";
  serverSnapshot?: {
    to: string;
    subject: string;
    body: string;
    attachmentIds: string[];
  };
};
export type Message = {
  id: string;
  request: string;
  mode: Mode;
  state: "answer" | "abstention" | "error" | "suggestions" | "draft";
  sourceIds: string[];
  evidenceIds: string[];
  at: string;
  saved?: boolean;
  answerText?: string;
  responseId?: string;
  groundingScore?: number;
  routeType?: RouteType;
  rejectedClaims?: string[];
  errorText?: string;
  origin?: "sample" | "server";
  studioResultId?: string;
  feedback?: "helpful" | "unhelpful";
  legacyThreadId?: string;
};
export type Handoff = {
  question: string;
  answer: string;
  evidenceIds: string[];
  sourceIds: string[];
};
export type Thread = {
  id: string;
  title: string;
  mode: Mode;
  view: View | "tasks";
  updated: string;
  messages: Message[];
  draft?: Draft;
  handoff?: Handoff;
  engineMode?: EngineMode;
  createdAt?: string;
  /** An unsent question staged by the Home workbench; never an assistant response. */
  composerDraft?: string;
};
export type Workspace = {
  id: string;
  color?: import("./home-model").WorkspaceColor;
  name: string;
  description: string;
  updated: string;
  sources: Source[];
  evidence: Record<string, Evidence>;
  tasks: Task[];
  suggestions: Suggestion[];
  draft: Draft;
  threads: Thread[];
  members: string[];
  requirements?: RequirementRow[];
  reconciliationRuns?: (ReconciliationRunRow & {
    origin: "preview" | "server";
    inputSignature?: string;
  })[];
  reconciledItems?: (ReconciledItemRow & {
    title?: string;
    serverState?: string;
  })[];
  schemaVersion?: number;
  notebookVersion?: 1;
  legacyThreads?: Thread[];
  studioResults?: import("./notebook-model").StudioResult[];
  studySets?: import("./study-model").StudySet[];
};
export const team = [
  "Phạm Gia Khiêm",
  "Hoàng Hải Việt",
  "Đặng Quang Minh",
  "Hà Lê Bảo Hưng",
  "Nguyễn Hoàng Minh Duy",
  "Nguyễn Quang Trường",
  "Phạm Lâm Viên",
];
export const blankDraft = (): Draft => ({
  to: "",
  cc: "",
  subject: "",
  body: "",
  purpose: "Clarification request",
  tone: "Formal and respectful",
  evidenceIds: [],
  attachmentIds: [],
  currentState: "IDLE",
  origin: "local",
});
export const evidence: Record<string, Evidence> = {
  deadline: {
    file: "Assignment_Spec.pdf",
    locator: "p. 3",
    title: "Midterm report submission",
    quote:
      "The midterm report must be submitted by November 6, 2026 at 23:59 (ICT). One team member submits the final PDF on behalf of the group.",
    context: "Section 3 · Submission requirements",
    id: "spec",
    finding:
      "The report is due November 6, 2026 at 23:59 (ICT). One team member submits the final PDF for the group.",
  },
  cc: {
    file: "Course_Policy.docx",
    locator: "section 2",
    title: "Academic correspondence",
    quote:
      "Address project-related emails to Mr. Châu Thành Đức and CC Mr. Đỗ Đức Hào and Mr. Trần Hoàng Quân. Include the course code and team name in the subject.",
    context: "Section 2 · Academic correspondence",
    id: "policy",
    finding:
      "Email Mr. Châu Thành Đức and CC Mr. Đỗ Đức Hào and Mr. Trần Hoàng Quân. Include the course code and team name in the subject.",
  },
  rubric: {
    file: "Grading_Rubric.pdf",
    locator: "p. 2",
    title: "Computational thinking coverage",
    quote:
      "The report must describe functional requirements, use cases, and the four pillars of computational thinking for each core feature.",
    context: "Section 2 · Assessment criteria",
    id: "rubric-file",
    finding:
      "Cover functional requirements, use cases, and the four pillars of computational thinking for each feature.",
  },
  checklist: {
    file: "Submission_Checklist.txt",
    locator: "lines 3–6",
    title: "Final checks",
    quote:
      "Verify citations. Confirm the report deadline. Include all team member names. Export the final report as a PDF.",
    context: "Final checklist · Lines 3–6",
    id: "checklist-file",
    finding:
      "Verify citations, confirm the deadline, include all team names, and export the final PDF.",
  },
};
const source = (
  id: string,
  name: string,
  detail: string,
  selected = false,
  status = "Processed",
  limitation?: string,
): Source => ({
  id,
  name,
  kind: name.split(".").pop()!.toUpperCase(),
  detail,
  status,
  selected,
  limitation,
});
export const initialSources = [
  source("spec", "Assignment_Spec.pdf", "8 pages · PDF", true),
  source("rubric-file", "Grading_Rubric.pdf", "4 pages · PDF", true),
  source("slides-file", "Kickoff_Slides.pptx", "14 slides · PowerPoint"),
  source("policy", "Course_Policy.docx", "4 sections · Word", true),
  source("config-file", "Config.json", "12 fields · Configuration"),
  source("checklist-file", "Submission_Checklist.txt", "18 lines · Text"),
  source(
    "scanned-file",
    "Lecture_Notes.pdf",
    "6 scanned pages",
    false,
    "Unreadable",
    "Scanned pages are not supported. Upload a text-based PDF.",
  ),
  source(
    "meeting-file",
    "Meeting_Notes.docx",
    "Queued for extraction",
    false,
    "Processing",
    "Processing is paused in this local preview.",
  ),
  source(
    "outline-file",
    "Project_Outline.doc",
    "3 pages · Legacy Word",
    false,
    "Processed",
    "Legacy formatting may differ from the original.",
  ),
  source("roles-file", "Team_Roles.json", "7 team members · JSON"),
  source("milestones-file", "Milestones.csv", "5 milestones · Spreadsheet"),
];
export const initialEmail: Draft = {
  to: "Châu Thành Đức <chau.thanh.duc@example.edu>",
  cc: "Đỗ Đức Hào <do.duc.hao@example.edu>, Trần Hoàng Quân <tran.hoang.quan@example.edu>",
  subject: "[CSC10014 – WorkspaceAI] Midterm report deadline clarification",
  body: "Dear Mr. Đức, Mr. Hào, and Mr. Quân,\n\nOur CSC10014 team is preparing the WorkspaceAI midterm report. The assignment lists November 6, 2026 at 23:59 (ICT) as the deadline.\n\nCould you please confirm that this is the submission deadline?\n\nThank you for your guidance.\n\nBest regards,\nPhạm Gia Khiêm\nOn behalf of the WorkspaceAI team",
  purpose: "Clarification request",
  tone: "Formal and respectful",
  evidenceIds: ["deadline", "cc"],
};
const thesisEvidence: Record<string, Evidence> = {
  reading: {
    file: "Reading_Protocol.pdf",
    locator: "p. 2",
    title: "Weekly reading discussion",
    quote:
      "The reading group meets every Thursday at 15:00 ICT. Each member prepares one paper summary and two discussion questions.",
    context: "Section 2 · Weekly reading format",
    id: "reading-file",
    finding:
      "Meet on Thursdays at 15:00 ICT. Prepare one paper summary and two discussion questions per member.",
  },
  research: {
    file: "Research_Questions.docx",
    locator: "heading 1.2",
    title: "Current research question",
    quote:
      "How can retrieval-augmented systems make evidence provenance easier to inspect for student researchers?",
    context: "Heading 1.2 · Research focus",
    id: "research-file",
    finding:
      "The group is studying how retrieval-augmented systems can make evidence provenance easier for student researchers to inspect.",
  },
};
const message = (
  id: string,
  request: string,
  mode: Mode,
  state: Message["state"],
  ids: string[],
  at: string,
  sources: string[],
): Message => ({
  id,
  request,
  mode,
  state,
  sourceIds: sources,
  evidenceIds: ids,
  at,
});
const midSources = ["spec", "policy", "rubric-file"];
const makeThread = (
  id: string,
  title: string,
  mode: Mode,
  view: View,
  m: Message,
): Thread => ({ id, title, mode, view, updated: m.at, messages: [m] });
export function seedWorkspaces(): Workspace[] {
  const records: Workspace[] = [
    {
      id: "midterm",
      name: "CSC10014 - Midterm Project",
      description: "From course requirements to a report we can stand behind.",
      updated: "2026-11-04T10:42:00+07:00",
      sources: initialSources,
      evidence,
      tasks: [],
      suggestions: [],
      draft: initialEmail,
      members: team,
      threads: [
        makeThread(
          "midterm-deadline",
          "Midterm deadline & email recipients",
          "Ask",
          "chat",
          message(
            "m1",
            "What is the deadline for the midterm report and who must be CC’d?",
            "Ask",
            "answer",
            ["deadline", "cc"],
            "2026-11-04T10:42:00+07:00",
            midSources,
          ),
        ),
        makeThread(
          "midterm-mail",
          "Clarify the submission date",
          "Email",
          "chat",
          message(
            "m3",
            "Draft a formal email to clarify the submission date.",
            "Email",
            "draft",
            ["deadline", "cc"],
            "2026-11-03T16:30:00+07:00",
            midSources,
          ),
        ),
        makeThread(
          "midterm-checks",
          "Final submission checklist",
          "Ask",
          "chat",
          message(
            "m4",
            "What are the final checks before submitting?",
            "Ask",
            "answer",
            ["checklist"],
            "2026-11-03T14:05:00+07:00",
            ["checklist-file"],
          ),
        ),
      ],
    },
    {
      id: "thesis",
      name: "Thesis Reading Group",
      description: "A shared reading desk for evidence and better questions.",
      updated: "2026-11-04T08:15:00+07:00",
      sources: [
        source("reading-file", "Reading_Protocol.pdf", "5 pages · PDF", true),
        source(
          "research-file",
          "Research_Questions.docx",
          "3 sections · Word",
          true,
        ),
        source("papers-file", "Paper_Index.csv", "9 papers · Spreadsheet"),
        source("seminar-file", "Seminar_Notes.txt", "64 lines · Text"),
      ],
      evidence: thesisEvidence,
      tasks: [],
      suggestions: [],
      draft: blankDraft(),
      members: team.slice(0, 3),
      threads: [
        makeThread(
          "thesis-reading",
          "Prepare for Thursday’s discussion",
          "Ask",
          "chat",
          message(
            "m6",
            "What should we prepare for the weekly reading group?",
            "Ask",
            "answer",
            ["reading"],
            "2026-11-04T08:15:00+07:00",
            ["reading-file"],
          ),
        ),
        makeThread(
          "thesis-invitation",
          "Reading group invitation",
          "Email",
          "chat",
          message(
            "m8",
            "Draft an invitation for our next reading discussion.",
            "Email",
            "draft",
            ["reading"],
            "2026-11-02T15:30:00+07:00",
            ["reading-file"],
          ),
        ),
      ],
    },
  ];
  return records.map((w) => ({
    ...w,
    threads: w.threads.map((t) =>
      t.mode === "Email"
        ? {
            ...t,
            draft:
              w.id === "midterm"
                ? initialEmail
                : {
                    ...blankDraft(),
                    subject: "Thesis Reading Group – Thursday discussion",
                    body: "Hello,\n\nOur reading group meets on Thursday at 15:00 ICT. Please bring one paper summary and two discussion questions.\n\nBest regards,\nPhạm Gia Khiêm",
                    evidenceIds: ["reading"],
                  },
          }
        : t,
    ),
  }));
}
export function emptyWorkspace(name: string, description: string): Workspace {
  return {
    id: crypto.randomUUID(),
    name,
    description,
    updated: new Date().toISOString(),
    sources: [],
    evidence: {},
    tasks: [],
    suggestions: [],
    draft: blankDraft(),
    threads: [],
    members: [team[0]],
    requirements: [],
    reconciliationRuns: [],
    reconciledItems: [],
    schemaVersion: 3,
  };
}
export function detectMode(text: string): "Ask" | "Email" {
  return /\b(email|mail|draft|write to|send to)\b/i.test(text)
    ? "Email"
    : "Ask";
}
export function relevantEvidence(
  workspace: Workspace,
  text: string,
  sources: string[],
): string[] {
  const available = Object.keys(workspace.evidence).filter((id) =>
    sources.includes(workspace.evidence[id].id),
  );
  if (workspace.id === "midterm") {
    if (/deadline|cc|recipient|submission date/i.test(text))
      return available.filter((id) => ["deadline", "cc"].includes(id));
    if (/checklist|final checks/i.test(text))
      return available.filter((id) => id === "checklist");
    if (/requirement|computational|rubric/i.test(text))
      return available.filter((id) => id === "rubric");
    if (/file limit|capacity|maximum/i.test(text))
      return available.filter((id) => id === "config");
  } else if (workspace.id === "thesis") {
    if (/reading|Thursday|prepare|meeting|discussion|weekly/i.test(text))
      return available.filter((id) => id === "reading");
    if (/research|literature|question/i.test(text))
      return available.filter((id) => id === "research");
  }
  return [];
}
