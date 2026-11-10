import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import ts from "typescript";

// Load the actual pure TypeScript adapters without adding a test framework dependency.
const modules = new Map();
function moduleUrl(name) {
  if (modules.has(name)) return modules.get(name);
  let source = readFileSync(resolve("src", name + ".ts"), "utf8");
  source = source.replaceAll(
    "import.meta.env",
    '({ VITE_API_ENABLED: "true" })',
  );
  let output = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  }).outputText;
  output = output.replace(
    /from "\.\/([^".]+)"/g,
    (_, dependency) => `from "${moduleUrl(dependency)}"`,
  );
  const url =
    "data:text/javascript;base64," + Buffer.from(output).toString("base64");
  modules.set(name, url);
  return url;
}
const schema = await import(moduleUrl("schema"));
const model = await import(moduleUrl("workflow-model"));
const data = await import(moduleUrl("data"));
const reports = await import(moduleUrl("report-model"));
const api = await import(moduleUrl("api"));
const home = await import(moduleUrl("home-model"));
const kanban = await import(moduleUrl("kanban-model"));
const kanbanService = await import(moduleUrl("kanban-service"));
const fixtures = () => structuredClone(data.seedWorkspaces());

test("Kanban preview is unsaved until confirmation; one board per workspace", async () => {
  const workspace = fixtures()[0],
    original = structuredClone(workspace);
  const proposal = await kanbanService.suggestKanban(workspace, true);
  assert.equal(proposal.cards.length, 8);
  assert.deepEqual(workspace, original);
  proposal.cards[0].selected = false;
  proposal.columns[2].selected = false;
  const saved = kanban.confirmProposal(workspace, proposal);
  assert.equal(saved.kanban.cards.length, 5);
  assert.equal(saved.kanban.columns.length, 2);
  assert.equal(saved.threads[0].messages.at(-1).kanbanEvent.count, 5);
  assert.throws(() => kanban.confirmProposal(saved, proposal), /đã có bảng/);
  assert.equal(workspace.kanban, undefined);
  assert.equal(fixtures()[1].kanban, undefined);
});
test("Kanban append preserves user edits and deduplicates against the latest board", async () => {
  const initial = await kanbanService.suggestKanban(fixtures()[0], true);
  let workspace = kanban.confirmProposal(fixtures()[0], initial);
  const card = workspace.kanban.cards[0];
  workspace = kanban.saveBoard(workspace, {
    ...workspace.kanban,
    cards: workspace.kanban.cards.map((c) =>
      c.id === card.id
        ? {
            ...c,
            title: "Tiêu đề đã sửa",
            notes: "Giữ ghi chú",
            checklist: [{ id: "check", text: "Xác minh", done: true }],
          }
        : c,
    ),
  });
  const proposal = {
    ...initial,
    id: "more",
    mode: "append",
    boardId: workspace.kanban.id,
    columns: workspace.kanban.columns.map((c) => ({ ...c, selected: true })),
    cards: [
      {
        ...kanban.newCard(card.columnId, "Công việc mới", "ai"),
        selected: true,
      },
    ],
  };
  const saved = kanban.confirmProposal(workspace, proposal);
  assert.deepEqual(saved.kanban.cards.slice(0, -1), workspace.kanban.cards);
  assert.equal(saved.threads[0].messages.at(-1).kanbanEvent.initial, false);
  assert.throws(() => kanban.confirmProposal(saved, proposal), /đã tồn tại/);
  assert.throws(
    () =>
      kanban.confirmProposal(workspace, { ...proposal, boardId: "different" }),
    /đã thay đổi/,
  );
});
test("Kanban card edits and moves keep legacy task fields and independent cards intact", async () => {
  const workspace = fixtures()[0],
    task = workspace.tasks[0];
  const proposal = await kanbanService.suggestKanban(workspace);
  const saved = kanban.confirmProposal(workspace, proposal),
    board = kanban.workspaceBoard(saved);
  const imported = board.cards.find((card) => card.taskId === task.id);
  assert.ok(imported);
  const done = board.columns.find((col) => col.status === "DONE");
  const moved = kanban.saveBoard(
    saved,
    kanban.moveCard(board, imported.id, done.id),
  );
  const updated = moved.tasks.find((row) => row.id === task.id);
  assert.equal(updated.status, "DONE");
  assert.equal(updated.owner, task.owner);
  assert.equal(updated.mappedReqId, task.mappedReqId);
  assert.equal(updated.completionPct, 100);
  const oldEdit = {
    ...moved,
    tasks: moved.tasks.map((row) =>
      row.id === task.id
        ? { ...row, title: "Sửa từ Tasks", due: "2026-12-19", status: "TODO" }
        : row,
    ),
  };
  const synced = kanban
    .workspaceBoard(oldEdit)
    .cards.find((card) => card.id === imported.id);
  assert.equal(synced.title, "Sửa từ Tasks");
  assert.equal(synced.dueDate, "2026-12-19");
  assert.equal(synced.columnId, board.columns[0].id);
});
test("Kanban removal and targeted undo preserve changes made after deletion", async () => {
  let workspace = kanban.confirmProposal(
    fixtures()[0],
    await kanbanService.suggestKanban(fixtures()[0], true),
  );
  const [deleted, other] = workspace.kanban.cards;
  workspace = kanban.saveBoard(workspace, {
    ...workspace.kanban,
    cards: workspace.kanban.cards.filter((c) => c.id !== deleted.id),
  });
  assert.equal(
    workspace.tasks.find((t) => t.id === deleted.taskId).archived,
    true,
  );
  workspace = kanban.saveBoard(workspace, {
    ...workspace.kanban,
    cards: workspace.kanban.cards.map((c) =>
      c.id === other.id ? { ...c, notes: "Sau khi xóa" } : c,
    ),
  });
  const restored = kanban.saveBoard(workspace, {
    ...workspace.kanban,
    cards: [...workspace.kanban.cards, deleted],
  });
  assert.equal(
    restored.tasks.find((t) => t.id === deleted.taskId).archived,
    false,
  );
  assert.equal(
    restored.kanban.cards.find((c) => c.id === other.id).notes,
    "Sau khi xóa",
  );
});
test("Kanban ordering is stable and column deletion cannot lose cards silently", async () => {
  const workspace = kanban.confirmProposal(
    fixtures()[0],
    await kanbanService.suggestKanban(fixtures()[0], true),
  );
  const board = workspace.kanban,
    [first, second] = board.cards;
  const moved = kanban.moveCard(board, second.id, first.columnId, first.id);
  assert.equal(moved.cards[0].id, second.id);
  assert.equal(board.cards[0].id, first.id);
  const reordered = kanban.reorderColumn(
    board,
    board.columns[2].id,
    board.columns[0].id,
  );
  assert.equal(reordered.columns[0].id, board.columns[2].id);
  assert.equal(reordered.cards.length, board.cards.length);
  assert.throws(
    () =>
      kanban.saveBoard(workspace, {
        ...board,
        columns: board.columns.slice(1),
      }),
    /Kiểm tra/,
  );
  assert.throws(
    () => kanban.saveBoard(workspace, { ...board, columns: [] }),
    /ít nhất một cột/,
  );
});
test("Offline Kanban reads selected source text and chat without a model call", async () => {
  const workspace = {
    ...fixtures()[0],
    tasks: [],
    sources: [
      {
        id: "local-text",
        name: "Kế hoạch.txt",
        kind: "txt",
        status: "Processed",
        selected: true,
        origin: "local",
        pages: [
          {
            raw_text:
              "Cần hoàn thành báo cáo trước 2026-12-20.\nChuẩn bị bài thuyết trình cho buổi họp.",
          },
        ],
      },
    ],
    threads: [
      {
        ...fixtures()[0].threads[0],
        messages: [
          {
            id: "q",
            request: "Cần rà soát kết luận trước khi nộp bài.",
            answerText: "",
            sourceIds: [],
            mode: "Ask",
            state: "answer",
            at: "2026-11-09",
          },
        ],
      },
    ],
  };
  const result = await kanbanService.suggestKanban(workspace);
  assert.equal(result.engine, "offline");
  assert.ok(
    result.cards.some(
      (card) =>
        card.dueDate === "2026-12-20" && card.sourceIds.includes("local-text"),
    ),
  );
  assert.ok(
    result.cards.some((card) => card.description.includes("rà soát kết luận")),
  );
  assert.ok(result.cards.some((card) => card.dueDate === ""));
  assert.equal(workspace.kanban, undefined);
  await assert.rejects(
    kanbanService.suggestKanban({
      ...workspace,
      tasks: [],
      sources: [],
      threads: [],
    }),
    /Chưa đủ nội dung/,
  );
});
test("Kanban validates real dates and never marks completed cards overdue", () => {
  assert.equal(kanban.explicitDate("Nộp 20/12/2026"), "2026-12-20");
  assert.equal(kanban.explicitDate("Due November 6, 2026"), "2026-11-06");
  assert.equal(kanban.explicitDate("Ngày 6/11 chưa có năm"), "");
  assert.equal(
    kanban.explicitDate("Nộp 2026-02-31 hoặc 2026-12-19"),
    "2026-12-19",
  );
  const card = {
    ...kanban.newCard("todo", "Nộp báo cáo"),
    dueDate: "2026-11-08",
  };
  assert.equal(kanban.dueState(card, false, "2026-11-09"), "overdue");
  assert.equal(kanban.dueState(card, true, "2026-11-09"), "none");
  assert.equal(
    kanban.dueState({ ...card, dueDate: "2026-11-12" }, false, "2026-11-09"),
    "soon",
  );
  assert.equal(kanban.dueState({ ...card, dueDate: "" }, false), "none");
});

test("workspace identities are distinct before palette reuse and persist across reload/reorder", () => {
  const original = Array.from(
    { length: home.WORKSPACE_COLORS.length },
    (_, index) => ({
      ...fixtures()[0],
      id: `research-${index}`,
      color: undefined,
    }),
  );
  const colored = home.assignWorkspaceColors(original);
  assert.equal(
    new Set(colored.map((workspace) => workspace.color)).size,
    home.WORKSPACE_COLORS.length,
  );
  assert.ok(original.every((workspace) => workspace.color === undefined));
  const reopened = home.assignWorkspaceColors(
    JSON.parse(JSON.stringify(colored)).reverse(),
  );
  for (const workspace of reopened)
    assert.equal(
      workspace.color,
      colored.find((existing) => existing.id === workspace.id).color,
    );
});

test("creating another workspace balances colors without changing existing identities", () => {
  const first = home.assignWorkspaceColors(fixtures());
  const next = home.assignWorkspaceColors([
    ...first,
    { ...fixtures()[0], id: "new-research", color: undefined },
  ]);
  assert.deepEqual(next.slice(0, first.length), first);
  assert.ok(home.isWorkspaceColor(next.at(-1).color));
  const invalid = home.assignWorkspaceColors([
    { ...fixtures()[0], color: "invalid-stored-value" },
  ]);
  assert.ok(home.isWorkspaceColor(invalid[0].color));
});

test("home history is chronological across workspaces instead of being grouped by the first project", () => {
  const workspaces = fixtures();
  workspaces[0].threads[0].updated = "2026-11-01T00:00:00Z";
  workspaces[1].threads[0].updated = "2026-11-07T00:00:00Z";
  const rows = home.conversationRows(workspaces);
  assert.equal(rows[0].workspace.id, workspaces[1].id);
  assert.equal(
    rows.length,
    workspaces.reduce((sum, workspace) => sum + workspace.threads.length, 0),
  );
  assert.ok(
    rows.every(
      (row, index) =>
        index === 0 ||
        Date.parse(rows[index - 1].thread.updated) >=
          Date.parse(row.thread.updated),
    ),
  );
});

test("home filters combine workspace, feature and Vietnamese search including a saved question", () => {
  const workspaces = fixtures();
  const thread = workspaces[0].threads[0];
  thread.title = "Nguồn tài liệu";
  thread.mode = "Ask";
  thread.messages = [{ request: "Đối chiếu thời hạn báo cáo", sourceIds: [] }];
  assert.equal(
    home.conversationRows(workspaces, workspaces[0].id, "Ask", "doi chieu")[0]
      .thread.id,
    thread.id,
  );
  assert.equal(
    home.conversationRows(workspaces, workspaces[0].id, "Email", "doi chieu")
      .length,
    0,
  );
  assert.equal(
    home.conversationRows(workspaces, workspaces[1].id, null, "Nguon tai lieu")
      .length,
    0,
  );
  const counts = ["Ask", "Tasks", "Email"].map(
    (mode) => home.conversationRows(workspaces, null, mode).length,
  );
  assert.equal(
    counts.reduce((sum, count) => sum + count, 0),
    home.conversationRows(workspaces).length,
  );
});

test("a home source trail retains historical provenance when checkboxes change or a file disappears", () => {
  const workspace = fixtures()[0];
  const [first, second] = workspace.sources;
  workspace.sources = [
    { ...first, selected: false },
    { ...second, selected: true },
  ];
  const thread = {
    ...workspace.threads[0],
    messages: [{ sourceIds: [first.id, first.id, "removed-file"] }],
  };
  const trail = home.conversationSources(workspace, thread);
  assert.deepEqual(
    trail.sources.map((source) => source.id),
    [first.id],
  );
  assert.equal(trail.missing, 1);
  assert.deepEqual(
    home.conversationSources(workspace, {
      ...thread,
      messages: [],
      handoff: undefined,
    }),
    { sources: [], missing: 0 },
  );
});

test("home recency uses Bangkok calendar days and treats missing dates honestly", () => {
  const now = new Date("2026-11-07T00:30:00+07:00");
  assert.equal(home.activityLabel("2026-11-06T18:00:00Z", now), "Today");
  assert.equal(home.activityLabel("2026-11-06T16:00:00Z", now), "Yesterday");
  assert.equal(home.activityLabel("invalid", now), "—");
});

test("dashboard scopes task metrics and excludes archived, completed and invalid dates from deadline alerts", () => {
  const workspaces = fixtures();
  const workspace = workspaces[0];
  const base = workspace.tasks[0];
  workspace.tasks = [
    { ...base, id: "late", due: "2026-11-07", status: "TODO" },
    { ...base, id: "today", due: "2026-11-08", status: "IN_PROGRESS" },
    { ...base, id: "review", due: "", status: "REVIEW" },
    { ...base, id: "done", due: "2026-11-06", status: "DONE" },
    {
      ...base,
      id: "archived",
      due: "2026-11-01",
      status: "IN_PROGRESS",
      archived: true,
    },
    { ...base, id: "invalid", due: "2026-02-30", status: "TODO" },
  ];
  const data = home.dashboardData(
    workspaces,
    workspace.id,
    new Date("2026-11-07T18:30:00Z"),
  );
  assert.equal(data.today, "2026-11-08");
  assert.equal(data.open, 4);
  assert.equal(data.inProgress, 1);
  assert.equal(data.done, 1);
  assert.equal(data.overdue, 1);
  assert.deepEqual(
    data.deadlines.map(({ task }) => task.id),
    ["late", "today"],
  );
  assert.equal(data.progress[0].total, 5);
  assert.equal(data.progress[0].percent, 20);
  assert.equal(data.documents, workspace.sources.length);
  assert.ok(data.recent.every((row) => row.workspace.id === workspace.id));
});

test("an empty dashboard keeps honest zeros, missing progress and no invented activity", () => {
  const workspace = { ...fixtures()[0], tasks: [], sources: [], threads: [] };
  const data = home.dashboardData([workspace]);
  assert.deepEqual(
    [data.open, data.inProgress, data.done, data.documents, data.overdue],
    [0, 0, 0, 0, 0],
  );
  assert.equal(data.progress[0].percent, null);
  assert.equal(data.resume, undefined);
  assert.deepEqual(data.deadlines, []);
  assert.deepEqual(data.recent, []);
});

test("landing workspace history follows latest real activity and opens the latest thread without reordering stored records", () => {
  const workspaces = fixtures();
  const first = workspaces[0];
  const originalOrder = workspaces.map((workspace) => workspace.id);
  first.updated = "2026-11-01T08:00:00Z";
  first.threads[0].updated = "2026-11-07T08:00:00Z";
  first.threads[1].updated = "2026-11-08T08:00:00Z";
  workspaces[1].updated = "2026-11-09T08:00:00Z";
  const rows = home.workspaceHistory(workspaces);
  assert.equal(rows[0].workspace.id, workspaces[1].id);
  const row = rows.find((entry) => entry.workspace.id === first.id);
  assert.equal(row.thread.id, first.threads[1].id);
  assert.equal(row.updated, "2026-11-08T08:00:00.000Z");
  assert.deepEqual(
    workspaces.map((workspace) => workspace.id),
    originalOrder,
  );
  const empty = home.workspaceHistory([
    { ...first, updated: "invalid", threads: [] },
  ])[0];
  assert.equal(empty.updated, "");
  assert.equal(empty.thread, undefined);
});

test("task states exactly match database ENUM", () => {
  const sql = readFileSync("../database/schema.sql", "utf8");
  const states = /`status`\s+ENUM\(([^)]+)\)/i
    .exec(sql)[1]
    .match(/'([^']+)'/g)
    .map((x) => x.slice(1, -1));
  assert.deepEqual(schema.TASK_STATES, states);
});
test("all twelve database tables have explicit frontend contracts", () => {
  const source = readFileSync("src/schema.ts", "utf8");
  const sql = readFileSync("../database/schema.sql", "utf8");
  const tables = [
    ...sql.matchAll(/CREATE TABLE IF NOT EXISTS\s+`(\w+)`/gi),
  ].map((m) => m[1]);
  assert.equal(tables.length, 12);
  for (const table of tables) assert.match(source, new RegExp(`\\b${table}:`));
});
test("migration preserves records, local labels, CC and all conversations", () => {
  const old = fixtures()[0];
  old.tasks[0].status = "Blocked";
  old.tasks[1].status = "Design Review";
  old.tasks[2].status = "Archived";
  const migrated = model.migrateWorkspace(old);
  assert.equal(migrated.tasks[0].status, "IN_PROGRESS");
  assert.equal(migrated.tasks[0].localLabel, "Blocked");
  assert.equal(migrated.tasks[1].status, "REVIEW");
  assert.equal(migrated.tasks[1].localLabel, "Design Review");
  assert.equal(migrated.tasks[2].archived, true);
  assert.equal(migrated.tasks.length, old.tasks.length);
  assert.equal(migrated.sources.length, old.sources.length);
  assert.equal(migrated.threads.length, old.threads.length);
  assert.equal(migrated.draft.cc, old.draft.cc);
  assert.equal(
    migrated.threads[0].messages[0].request,
    old.threads[0].messages[0].request,
  );
  assert.equal(old.tasks[0].status, "Blocked", "input is not mutated");
});
test("migration is idempotent and does not reseed deleted requirements", () => {
  const first = model.migrateWorkspace(fixtures()[0]);
  first.requirements = [];
  assert.deepEqual(model.migrateWorkspace(first), first);
});
test("custom workspaces do not receive academic sample requirements", () => {
  const w = data.emptyWorkspace("My project", "");
  assert.deepEqual(model.migrateWorkspace(w).requirements, []);
});
test("task rows omit local design labels, archive flag, description and avatar", () => {
  const t = model.migrateWorkspace(fixtures()[0]).tasks[0];
  const row = model.taskRow({
    ...t,
    localLabel: "Blocked",
    archived: true,
    completionPct: 47.5,
  });
  assert.equal(row.completion_pct, 47.5);
  assert.equal(row.mapped_req_id, "R1");
  assert.equal(row.localLabel, undefined);
  assert.equal(row.archived, undefined);
  assert.equal(row.description, undefined);
  assert.equal(row.initials, undefined);
  assert.deepEqual(
    Object.keys(row).sort(),
    [
      "task_id",
      "mapped_req_id",
      "title",
      "owner",
      "status",
      "logged_deadline",
      "completion_pct",
      "source_ref",
      "created_at",
      "updated_at",
    ].sort(),
  );
});
test("missing dates and owners map to SQL NULL, progress is bounded", () => {
  const row = model.taskRow({
    ...fixtures()[0].tasks[0],
    mappedReqId: "",
    owner: "",
    due: "",
    completionPct: 180,
  });
  assert.equal(row.owner, null);
  assert.equal(row.logged_deadline, null);
  assert.equal(row.mapped_req_id, null);
  assert.equal(row.completion_pct, 100);
  assert.equal(schema.clampProgress(-5), 0);
  assert.equal(schema.clampProgress(undefined, 17), 17);
});
test("action routing and session engines remain independent", () => {
  assert.equal(schema.featureRoute("Ask"), "QA_FLOW");
  assert.equal(schema.featureRoute("Tasks"), "RECONCILE_FLOW");
  const w = model.migrateWorkspace(fixtures()[0]);
  assert.equal(w.threads[0].engineMode, "offline");
  assert.equal(w.threads[0].mode, "Ask");
});
test("only the four server verification statuses count as verified", () => {
  for (const value of [
    "VERIFIED_EXACT",
    "VERIFIED_SUBSTRING",
    "VERIFIED_TOKEN_LCS",
    "VERIFIED_FUZZY",
  ])
    assert.equal(schema.isVerified(value), true);
  for (const value of [
    undefined,
    "UNGROUNDED_QUOTE",
    "HALLUCINATED_CLAIM",
    "OUT_OF_BOUNDS",
    "From document",
  ])
    assert.equal(schema.isVerified(value), false);
});
test("sample evidence has no fabricated verification, score or hash", () => {
  const w = model.migrateWorkspace(fixtures()[0]);
  for (const claim of Object.values(w.evidence)) {
    assert.equal(claim.origin, "sample");
    assert.equal(claim.verificationStatus, undefined);
    assert.equal(claim.matchScore, undefined);
    assert.equal(claim.docHash, undefined);
  }
});
test("document adapter accepts current API aliases without inventing missing fields", () => {
  const s = model.sourceFromServer({
    doc_id: "d1",
    doc_name: "notes.md",
    page_count: 2,
    chunk_count: 5,
    total_lines: 25,
    version_id: "v2",
    is_selected: true,
  });
  assert.equal(s.totalPages, 2);
  assert.equal(s.totalChunks, 5);
  assert.equal(s.totalLines, 25);
  assert.equal(s.versionId, "v2");
  assert.equal(s.selected, true);
  assert.equal(s.fileHash, undefined);
  assert.equal(s.fileSizeBytes, undefined);
  assert.equal(s.pages, undefined);
  assert.throws(() => model.sourceFromServer({ doc_name: "bad.md" }));
});
test("citation document aliases resolve uniquely and never guess between versions", () => {
  const sources = [{ id: "doc-1", name: "Project_Brief.pdf" }];
  assert.equal(model.resolveCitedSource("project_brief", sources)?.id, "doc-1");
  assert.equal(
    model.resolveCitedSource("PROJECT_BRIEF.PDF", sources)?.id,
    "doc-1",
  );
  assert.equal(
    model.resolveCitedSource("project_brief", [
      ...sources,
      { id: "doc-2", name: "Project_Brief.md" },
    ]),
    undefined,
  );
  assert.equal(model.resolveCitedSource("nonexistent", sources), undefined);
});
test("R2 response names are adapted to SQL without recalculating reconciliation", () => {
  assert.equal(reports.reportState("COMPLETED", true), "FULLY_COVERED");
  assert.equal(reports.reportState("UNTRACKED_MISSING", false), "NOT_COVERED");
  assert.equal(reports.reportState("UNASSIGNED", false), "PARTIALLY_COVERED");
  assert.equal(reports.reportState("IN_PROGRESS", true), "DEADLINE_CONFLICT");
  assert.equal(reports.reportState("OVERDUE", true), "OVERDUE");
  assert.throws(() => reports.reportState("invented", false));
});
test("report snapshots retain source state, dates, owners and previous runs", () => {
  const item = {
    req_id: "R8",
    title: "Report",
    state: "COMPLETED",
    risk_level: "LOW",
    avg_completion: 100,
    days_remaining: 2,
    owners: ["Alex"],
    date_conflicts: [],
    citations: ["spec.pdf p.2"],
  };
  const report = {
    coverage_ratio: 1,
    overdue_count: 0,
    conflict_count: 0,
    item_reports: [item],
  };
  const w = model.migrateWorkspace(fixtures()[0]);
  const one = reports.appendReport(w, report, "2026-11-06");
  const two = reports.appendReport(one, report, "2026-11-07");
  assert.equal(w.reconciliationRuns.length, 0);
  assert.equal(two.reconciliationRuns.length, 2);
  assert.equal(two.reconciledItems.length, 2);
  assert.equal(two.reconciledItems[0].serverState, "COMPLETED");
  assert.deepEqual(two.reconciledItems[0].owners, ["Alex"]);
  assert.equal(two.reconciliationRuns[0].reference_date, "2026-11-06");
  assert.notEqual(
    two.reconciliationRuns[0].run_id,
    two.reconciliationRuns[1].run_id,
  );
});
test("invalid reports cannot replace previous data", () => {
  const w = model.migrateWorkspace(fixtures()[0]);
  assert.throws(() =>
    reports.appendReport(
      w,
      { coverage_ratio: NaN, item_reports: [] },
      "2026-11-06",
    ),
  );
  assert.equal(w.reconciliationRuns.length, 0);
});
test("email snapshot covers attachments and full content, with stable attachment order", async () => {
  const d = {
    ...data.blankDraft(),
    to: "Name <person@example.org>",
    subject: "Hello",
    body: "Message",
    attachmentIds: ["b", "a"],
  };
  assert.equal(
    model.draftPayload(d),
    model.draftPayload({ ...d, attachmentIds: ["a", "b"] }),
  );
  assert.notEqual(
    model.draftPayload(d),
    model.draftPayload({ ...d, attachmentIds: ["a"] }),
  );
  assert.notEqual(
    model.draftPayload(d),
    model.draftPayload({ ...d, body: "Changed" }),
  );
  assert.equal(
    (await model.sha256(new TextEncoder().encode(model.draftPayload(d))))
      .length,
    64,
  );
});
test("single-recipient boundary rejects multiple addresses and strips display names", () => {
  assert.equal(model.validRecipient("Name <person@example.org>"), true);
  assert.equal(
    model.recipientAddress("Name <person@example.org>"),
    "person@example.org",
  );
  for (const value of [
    "",
    "not-an-email",
    "a@example.org,b@example.org",
    "a@example.org;b@example.org",
  ])
    assert.equal(model.validRecipient(value), false);
});
const serverDraft = () =>
  api.draftFromServer(
    {
      draft_id: "d1",
      recipient_email: "a@example.org",
      subject: "S",
      body: "B",
      attachment_ids: [],
      citations: [],
      state: "PENDING_APPROVAL",
      payload_hash: "a".repeat(64),
    },
    "s1",
    { name: "Workspace" },
  );
test("server draft has no client-forged HMAC or audit rows", () => {
  const d = serverDraft();
  assert.equal(d.hmacSignature, undefined);
  assert.equal(d.auditLogs, undefined);
  assert.equal(d.sessionId, "s1");
  assert.equal(d.currentState, "PENDING_APPROVAL");
});
test("approval boundary blocks unstaged, edited, CC, attachment and already-sent drafts", () => {
  const d = serverDraft();
  for (const next of [
    { ...d, origin: "local" },
    { ...d, body: "Changed" },
    { ...d, to: "other@example.org" },
    { ...d, cc: "b@example.org" },
    { ...d, attachmentIds: ["f1"] },
    { ...d, currentState: "SENT" },
  ])
    assert.throws(() => api.approveAndSend(next));
});
test("every valid workspace can connect to its own backend library", () => {
  assert.equal(api.apiFor("midterm"), true);
  assert.equal(api.apiFor("thesis"), true);
  assert.equal(api.apiFor("0b17d2e1-6f79-4dae-bef6-06aeaef46db9"), true);
  for (const id of ["", "../private", "x".repeat(65)])
    assert.equal(api.apiFor(id), false);
});

test("indexing a device preview removes the duplicate and preserves its references", () => {
  const w = model.migrateWorkspace(fixtures()[0]);
  const source = {
    id: "local-pdf",
    name: "notes.txt",
    kind: "TXT",
    detail: "1 KB",
    origin: "local",
    status: "Preview only",
    selected: false,
    fileHash: "a".repeat(64),
    fileSizeBytes: 105,
    pages: [
      { doc_id: "local-pdf", raw_text: "Original preview", page_number: 1 },
    ],
  };
  w.sources = [source];
  w.requirements[0].doc_id = source.id;
  const evidenceKey = Object.keys(w.evidence)[0];
  w.evidence[evidenceKey].id = source.id;
  w.draft.attachmentIds = [source.id];
  w.threads[0].draft = { ...w.draft };
  const originalMessages = structuredClone(w.threads[0].messages);
  const server = model.sourceFromServer({
    doc_id: "notes.txt",
    doc_name: "notes.txt",
    file_hash: source.fileHash,
    page_count: 1,
    chunk_count: 2,
    is_selected: true,
  });
  const next = model.syncWorkspaceLibrary(w, [server]);
  assert.equal(next.sources.length, 1);
  assert.equal(next.sources[0].status, "Processed");
  assert.equal(next.sources[0].selected, true);
  assert.equal(next.sources[0].fileSizeBytes, 105);
  assert.equal(next.sources[0].pages[0].doc_id, server.id);
  assert.equal(next.requirements[0].doc_id, server.id);
  assert.equal(next.evidence[evidenceKey].id, server.id);
  assert.deepEqual(next.draft.attachmentIds, [server.id]);
  assert.deepEqual(next.threads[0].draft.attachmentIds, [server.id]);
  assert.deepEqual(next.threads[0].messages, originalMessages);
  assert.equal(w.sources[0].id, "local-pdf");
});

test("sync does not treat matching filenames as matching file content", () => {
  const w = data.emptyWorkspace("Files", "");
  w.sources = [
    {
      id: "preview",
      name: "notes.txt",
      kind: "TXT",
      detail: "",
      origin: "local",
      status: "Preview only",
      selected: false,
      fileHash: "old",
      pages: [{ raw_text: "Old version" }],
    },
  ];
  const server = model.sourceFromServer({
    doc_id: "notes.txt",
    doc_name: "notes.txt",
    file_hash: "new",
    is_selected: false,
  });
  const next = model.syncWorkspaceLibrary(w, [server]);
  assert.equal(next.sources.length, 2);
  assert.equal(next.sources[1].pages, undefined);
  assert.equal(next.sources[1].selected, false);
});

test("explicit re-upload remaps a preview without carrying text from different bytes", () => {
  const w = data.emptyWorkspace("Files", "");
  w.sources = [
    {
      id: "preview",
      name: "notes.txt",
      kind: "TXT",
      detail: "",
      origin: "local",
      status: "Needs upload",
      selected: false,
      fileHash: "old",
      pages: [{ raw_text: "Old version" }],
    },
  ];
  const server = model.sourceFromServer({
    doc_id: "notes.txt",
    doc_name: "notes.txt",
    file_hash: "new",
    is_selected: true,
  });
  const next = model.syncWorkspaceLibrary(w, [server], { preview: server.id });
  assert.equal(next.sources.length, 1);
  assert.equal(next.sources[0].pages, undefined);
  assert.equal(next.sources[0].fileHash, "new");
});

test("a restarted library retains missing file metadata with a re-upload state", () => {
  const w = data.emptyWorkspace("Files", "");
  w.sources = [
    model.sourceFromServer({
      doc_id: "notes.txt",
      doc_name: "notes.txt",
      file_hash: "abc",
      is_selected: true,
    }),
  ];
  const next = model.syncWorkspaceLibrary(w, []);
  assert.equal(next.sources.length, 1);
  assert.equal(next.sources[0].status, "Needs upload");
  assert.equal(next.sources[0].selected, false);
  assert.equal(next.sources[0].fileHash, "abc");
  assert.match(next.sources[0].limitation, /Re-upload/);
});

test("all document and workflow requests retain the current workspace header", async () => {
  const original = globalThis.fetch;
  const captured = [];
  const row = { doc_id: "notes.txt", doc_name: "notes.txt", is_selected: true };
  globalThis.fetch = async (url, init) => {
    captured.push({ url, init });
    return new Response(
      JSON.stringify(
        url === "/api/documents"
          ? [row]
          : url === "/api/documents/upload"
            ? { document: row }
            : url === "/api/chat"
              ? { reconciliation_report: { item_reports: [] } }
              : { status: "SELECTION_UPDATED" },
      ),
    );
  };
  try {
    const wid = "new-workspace";
    await api.listDocuments(wid);
    const uploaded = await api.uploadDocument(
      new File(["notes"], "notes.txt", { type: "text/plain" }),
      wid,
    );
    assert.equal(uploaded.fileSizeBytes, 5);
    assert.equal(uploaded.origin, "server");
    assert.equal(
      captured.at(-1).init.headers.get("Content-Type"),
      null,
      "multipart boundary is set by fetch",
    );
    await api.selectDocuments(["notes.txt"], wid);
    await api.deleteDocument("notes.txt", wid);
    await api.chatRequest(
      "Question",
      ["notes.txt"],
      [],
      undefined,
      "2026-11-06",
      wid,
    );
    await api.reconcile("2026-11-06", wid);
    await api.approveAndSend(serverDraft(), wid);
    assert.equal(captured.length, 7);
    for (const { init } of captured)
      assert.equal(init.headers.get("X-Workspace-ID"), wid);
    assert.equal(
      captured[2].init.headers.get("Content-Type"),
      "application/json",
    );
    await api.getRuntimeStatus();
    assert.equal(
      captured.at(-1).init.headers.get("X-Workspace-ID"),
      null,
      "machine runtime is global",
    );
  } finally {
    globalThis.fetch = original;
  }
});
test("chat sends selected docs and history using the real endpoint contract", async () => {
  const original = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, init) => {
    captured = { url, init };
    return new Response(
      JSON.stringify({ route: "QA_FLOW", status: "ANSWER_VERIFIED" }),
    );
  };
  try {
    await api.chatRequest(
      "Question",
      ["d1"],
      [{ role: "user", content: "Before" }],
      undefined,
      "2026-11-06",
    );
    assert.equal(captured.url, "/api/chat");
    const body = JSON.parse(captured.init.body);
    assert.deepEqual(body.selected_doc_ids, ["d1"]);
    assert.equal(body.reference_date, "2026-11-06");
    assert.equal(body.conversation_history[0].content, "Before");
    assert.equal(body.active_mode, undefined);
  } finally {
    globalThis.fetch = original;
  }
});
test("approve-and-send uses POST and the staged content; no fake send response", async () => {
  const original = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, init) => {
    captured = { url, init };
    return new Response(
      JSON.stringify({ status: "SENT", dispatch_mode: "local_mock" }),
    );
  };
  try {
    const r = await api.approveAndSend(serverDraft());
    assert.equal(r.dispatch_mode, "local_mock");
    assert.equal(captured.init.method, "POST");
    const url = new URL(captured.url, "http://test");
    assert.equal(url.searchParams.get("user_confirmed"), "true");
    assert.equal(url.searchParams.get("body"), "B");
    assert.equal(url.searchParams.get("recipient_email"), "a@example.org");
  } finally {
    globalThis.fetch = original;
  }
});
test("network failure stays an unconfirmed API error", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => {
    throw new Error("offline");
  };
  try {
    await assert.rejects(
      api.approveAndSend(serverDraft()),
      (error) => error instanceof api.ApiError && error.status === undefined,
    );
  } finally {
    globalThis.fetch = original;
  }
});

test("Gemini setup opts in only Feature 1 with a pinned model and supports returning offline", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(
      JSON.stringify({ status: "ready", engine_mode: "offline" }),
    );
  };
  try {
    await api.configureGemini("synthetic-test-key-not-a-credential", false);
    const body = JSON.parse(calls[0].init.body);
    assert.equal(body.enable_feature1, true);
    assert.equal(body.model, "gemini-3.5-flash-lite");
    assert.equal(body.save_locally, false);
    assert.equal(calls[0].init.headers.get("X-Workspace-ID"), null);
    await api.useOffline(true);
    assert.equal(calls[1].url, "/api/runtime/offline");
    assert.deepEqual(JSON.parse(calls[1].init.body), { save_locally: true });
  } finally {
    globalThis.fetch = original;
  }
});

const notebook = await import(moduleUrl("notebook-model"));
test("notebook migration retains original sessions and all distinct messages in one chronological chat", () => {
  const original = fixtures()[0];
  const before = structuredClone(original);
  const migrated = notebook.notebookWorkspace(original);
  assert.equal(migrated.threads.length, 1);
  assert.equal(migrated.threads[0].mode, "Ask");
  assert.deepEqual(migrated.legacyThreads, before.threads);
  assert.deepEqual(original, before);
  const messages = migrated.threads[0].messages;
  assert.ok(messages.length > 0);
  assert.ok(
    messages.every(
      (message, index) =>
        !index || Date.parse(message.at) >= Date.parse(messages[index - 1].at),
    ),
  );
  for (const thread of before.threads)
    for (const message of thread.messages)
      assert.ok(
        messages.some(
          (entry) =>
            entry.request === message.request &&
            entry.at === message.at &&
            JSON.stringify(entry.evidenceIds) ===
              JSON.stringify(message.evidenceIds),
        ),
      );
  assert.ok(
    migrated.studioResults.some(
      (result) => result.kind === "email" && result.draft,
    ),
  );
  assert.deepEqual(notebook.notebookWorkspace(migrated), migrated);
});
test("message ID collisions with different source scope remain separate, and saved state survives", () => {
  const workspace = fixtures()[0],
    first = workspace.threads[0].messages[0];
  first.saved = true;
  workspace.threads.push({
    ...workspace.threads[0],
    id: "collision",
    messages: [{ ...first, sourceIds: ["different-document"] }],
  });
  const migrated = notebook.notebookWorkspace(workspace);
  const copies = migrated.threads[0].messages.filter(
    (message) => message.request === first.request && message.at === first.at,
  );
  assert.ok(copies.length >= 2);
  assert.equal(
    new Set(migrated.threads[0].messages.map((message) => message.id)).size,
    migrated.threads[0].messages.length,
  );
  assert.ok(copies.some((message) => message.saved));
});
test("interrupted Studio jobs are recoverable on reload but remain running during storage sync", () => {
  const workspace = notebook.notebookWorkspace(fixtures()[0]);
  workspace.studioResults.push({ id: "pending", status: "generating" });
  assert.equal(
    notebook.notebookWorkspace(workspace, false).studioResults.at(-1).status,
    "generating",
  );
  const recovered = notebook.notebookWorkspace(workspace);
  assert.equal(recovered.studioResults.at(-1).status, "error");
  assert.match(recovered.studioResults.at(-1).error, /gián đoạn/);
});
test("chat output capture is idempotent, snapshots its sources and never adds a second conversation", () => {
  const workspace = notebook.notebookWorkspace(fixtures()[0]);
  workspace.threads[0].messages.push({
    id: "fresh-email",
    state: "draft",
    request: "A new email draft",
    mode: "Email",
    sourceIds: workspace.sources.slice(0, 1).map((source) => source.id),
    evidenceIds: [],
    at: "2026-11-08T10:00:00Z",
  });
  workspace.threads[0].draft = {
    ...workspace.draft,
    subject: "Snapshot subject",
    body: "Snapshot body",
  };
  const captured = notebook.captureChatOutputs(workspace);
  assert.equal(captured.threads.length, 1);
  const result = captured.studioResults.find(
    (item) => item.id === "chat-fresh-email",
  );
  assert.equal(result.draft.body, "Snapshot body");
  assert.equal(result.sourceSnapshot.length, 1);
  assert.deepEqual(notebook.captureChatOutputs(captured), captured);
});
