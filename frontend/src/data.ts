import type { TaskStatus } from "./task-status";
export type Mode = "Ask" | "Tasks" | "Email";
export type View = "chat" | "tasks" | "email";
export type Source = {
  id: string;
  name: string;
  kind: string;
  detail: string;
  status: string;
  selected: boolean;
  limitation?: string;
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
};
export type Task = {
  id: string;
  title: string;
  description: string;
  owner: string;
  initials: string;
  due: string;
  status: TaskStatus;
  flag?: string;
  source?: string;
  secondarySource?: string;
};
export type Suggestion = {
  id: string;
  title: string;
  description: string;
  owner: string;
  due: string;
  status?: TaskStatus;
  selected: boolean;
  source?: string;
  threadId?: string;
};
export type Draft = {
  to: string;
  cc: string;
  subject: string;
  body: string;
  purpose: string;
  tone: string;
  evidenceIds: string[];
  context?: string;
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
  view: View;
  updated: string;
  messages: Message[];
  draft?: Draft;
  handoff?: Handoff;
};
export type Workspace = {
  id: string;
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
  conflict: {
    file: "Team_Tasks.csv",
    locator: "row 4",
    title: "A conflicting submission date",
    quote: "T04, Submit midterm report, Phạm Gia Khiêm, 2026-11-05, To do",
    context: "Task row 4 · Internal planning record",
    id: "task-file",
    finding:
      "The internal task sheet lists November 5 for report submission. This conflicts with November 6 in the assignment specification.",
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
  slides: {
    file: "Kickoff_Slides.pptx",
    locator: "slide 6",
    title: "The three connected features",
    quote:
      "WorkspaceAI connects document-based learning, reviewed task planning, and user-approved academic email reporting.",
    context: "Slide 6 · Product overview",
    id: "slides-file",
    finding:
      "The three features are document-based learning, reviewed task planning, and user-approved email reporting.",
  },
  config: {
    file: "Config.json",
    locator: "$.workspace.max_files",
    title: "Workspace file capacity",
    quote: '"workspace": { "max_files": 20 }',
    context: "Workspace configuration · JSON path",
    id: "config-file",
    finding: "This workspace has a soft limit of 20 active files.",
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
  source("task-file", "Team_Tasks.csv", "7 rows · Spreadsheet", true),
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
export const initialTasks: Task[] = [
  {
    id: "t1",
    title: "Clarify the report deadline",
    description:
      "Resolve November 5 versus November 6 before the final submission.",
    owner: team[0],
    initials: "GK",
    due: "2026-11-05",
    status: "To do",
    flag: "Conflicting dates",
    source: "conflict",
    secondarySource: "deadline",
  },
  {
    id: "t2",
    title: "Complete use case specifications",
    description:
      "Document the alternate and exception flows for all three features.",
    owner: team[2],
    initials: "QM",
    due: "2026-11-03",
    status: "In progress",
    flag: "Overdue",
    source: "rubric",
  },
  {
    id: "t3",
    title: "Verify source citations",
    description:
      "Check page numbers and quotations against the original files.",
    owner: team[1],
    initials: "HV",
    due: "2026-11-05",
    status: "In progress",
    source: "deadline",
  },
  {
    id: "t4",
    title: "Review functional requirements",
    description: "Align the requirements with the project scope.",
    owner: team[3],
    initials: "BH",
    due: "2026-11-02",
    status: "Done",
    source: "rubric",
  },
  {
    id: "t5",
    title: "Prepare the report structure",
    description: "Create the shared outline for the midterm report.",
    owner: team[4],
    initials: "MD",
    due: "2026-11-01",
    status: "Done",
    source: "deadline",
  },
];
export const seedSuggestions: Suggestion[] = [
  {
    id: "s1",
    title: "Document computational thinking analysis",
    description:
      "Cover decomposition, pattern recognition, abstraction, and algorithm design for the three features.",
    owner: "",
    due: "",
    selected: true,
    source: "rubric",
  },
];
export const initialEmail: Draft = {
  to: "Châu Thành Đức <chau.thanh.duc@example.edu>",
  cc: "Đỗ Đức Hào <do.duc.hao@example.edu>, Trần Hoàng Quân <tran.hoang.quan@example.edu>",
  subject: "[CSC10014 – WorkspaceAI] Midterm report deadline clarification",
  body: "Dear Mr. Đức, Mr. Hào, and Mr. Quân,\n\nOur CSC10014 team is preparing the WorkspaceAI midterm report. The assignment lists November 6, 2026 at 23:59 (ICT) as the deadline, while our internal task sheet lists November 5.\n\nCould you please confirm which date we should follow? We will update our task board once the date is clarified.\n\nThank you for your guidance.\n\nBest regards,\nPhạm Gia Khiêm\nOn behalf of the WorkspaceAI team",
  purpose: "Clarification request",
  tone: "Formal and respectful",
  evidenceIds: ["deadline", "cc", "conflict"],
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
const midSources = ["spec", "policy", "task-file", "rubric-file"];
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
      tasks: initialTasks,
      suggestions: seedSuggestions,
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
            ["deadline", "cc", "conflict"],
            "2026-11-04T10:42:00+07:00",
            midSources,
          ),
        ),
        makeThread(
          "midterm-plan",
          "Break down the report requirements",
          "Tasks",
          "chat",
          message(
            "m2",
            "Break down the report requirements into tasks.",
            "Tasks",
            "suggestions",
            ["rubric"],
            "2026-11-04T09:20:00+07:00",
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
            ["deadline", "cc", "conflict"],
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
        makeThread(
          "midterm-scope",
          "The three core features",
          "Ask",
          "chat",
          message(
            "m5",
            "What features are in our project scope?",
            "Ask",
            "answer",
            ["slides"],
            "2026-11-02T11:15:00+07:00",
            ["slides-file"],
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
      tasks: [
        {
          id: "thesis-task",
          title: "Prepare this week’s paper summary",
          description:
            "Bring a paper summary and two discussion questions to the reading group.",
          owner: team[0],
          initials: "GK",
          due: "2026-11-05",
          status: "To do",
          source: "reading",
        },
      ],
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
          "thesis-questions",
          "Plan the literature review",
          "Tasks",
          "chat",
          message(
            "m7",
            "Suggest tasks for the next literature review.",
            "Tasks",
            "suggestions",
            ["research"],
            "2026-11-03T13:00:00+07:00",
            ["research-file"],
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
  };
}
export function detectMode(text: string): Mode {
  return /\b(email|mail|draft|write to|send to)\b/i.test(text)
    ? "Email"
    : /\b(tasks?|plan|assign|kanban|break down|to.do)\b/i.test(text)
      ? "Tasks"
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
      return available.filter((id) =>
        ["deadline", "cc", "conflict"].includes(id),
      );
    if (/checklist|final checks/i.test(text))
      return available.filter((id) => id === "checklist");
    if (/scope|features/i.test(text))
      return available.filter((id) => id === "slides");
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
console.assert(
  seedWorkspaces().reduce((n, w) => n + w.threads.length, 0) === 8,
  "Eight seeded conversations",
);
console.assert(
  initialTasks.filter((t) => t.status === "Done").length === 2,
  "Progress reconciles with task rows",
);
