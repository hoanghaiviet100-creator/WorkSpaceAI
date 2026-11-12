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
const api = await import(moduleUrl("api"));
const home = await import(moduleUrl("home-model"));
const study = await import(moduleUrl("study-model"));
const samples = await import(moduleUrl("study-sample"));
const generator = await import(moduleUrl("study-generator"));
const fixtures = () => structuredClone(data.seedWorkspaces());

test("study generation uses only configured sources and cites the extracted page", async () => {
  const workspace = fixtures()[0];
  const lines = [
    "# Thuật toán",
    "Tìm kiếm nhị phân yêu cầu dãy dữ liệu đã được sắp xếp.",
    "Thuật toán cần mô tả các bước hữu hạn và xác định.",
    "Tìm kiếm tuyến tính kiểm tra lần lượt các phần tử của dãy.",
    "Ca kiểm thử có đầu vào và kết quả mong đợi.",
  ];
  workspace.sources = ["chosen", "ignored"].map((id, index) => ({
    id,
    name: id + ".txt",
    kind: "txt",
    detail: "",
    status: "Processed",
    origin: "local",
    selected: index === 0,
    pages: [
      {
        page_number: 1,
        raw_text: index
          ? "Do not use this unrelated sentence."
          : lines.join("\n"),
      },
    ],
  }));
  const config = { ...study.studyConfig(workspace, "quiz"), count: 4 };
  assert.deepEqual(config.sourceIds, ["chosen"]);
  const items = await generator.createStudyItems(workspace, config);
  assert.equal(items.length, 4);
  for (const item of items) {
    assert.equal(item.citation.docId, "chosen");
    assert.equal(item.citation.quote, lines[item.citation.startLine - 1]);
    assert.equal(item.topic, "Thuật toán");
    assert.ok(item.answer.includes(item.options[item.correctIndex]));
    assert.equal(item.options.length, new Set(item.options).size);
  }
  await assert.rejects(
    generator.createStudyItems(workspace, {
      ...config,
      sourceIds: ["different-workspace"],
    }),
  );
  const english = await generator.createStudyItems(workspace, {
    ...config,
    language: "en",
  });
  assert.match(english[0].question, /^Fill in the blank\./);
  assert.equal(english[0].citation.quote, items[0].citation.quote);
});

test("quiz samples and retry review scores are calculated from answered questions", () => {
  assert.equal(samples.sampleStudy("flashcard").items.length, 8);
  const quiz = samples.sampleStudy("quiz");
  assert.equal(quiz.items.length, 5);
  const answers = Object.fromEntries(
    quiz.items.map((item) => [item.id, item.correctIndex]),
  );
  answers[quiz.items[0].id] = 1;
  assert.deepEqual(study.scoreQuiz(quiz.items, answers), {
    correct: 4,
    total: 5,
  });
  assert.equal(study.quizTopics(quiz.items, answers)[0].correct, 2);
  const [review] = study.reviewCards([quiz.items[0]]);
  assert.equal(review.options, undefined);
  assert.equal(review.citation, quiz.items[0].citation);
  assert.match(review.answer, /Break the problem into smaller parts/);
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

test("home recency uses Bangkok calendar days and treats missing dates honestly", () => {
  const now = new Date("2026-11-07T00:30:00+07:00");
  assert.equal(home.activityLabel("2026-11-06T18:00:00Z", now), "Today");
  assert.equal(home.activityLabel("2026-11-06T16:00:00Z", now), "Yesterday");
  assert.equal(home.activityLabel("invalid", now), "—");
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
  old.tasks = ["Blocked", "Design Review", "Archived"].map((status, index) => ({
    id: `legacy-task-${index}`,
    title: "Archived workspace task",
    status,
  }));
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
test("action routing and session engines remain independent", () => {
  assert.equal(schema.featureRoute("Ask"), "QA_FLOW");
  assert.equal(schema.featureRoute("Email"), "EMAIL_FLOW");
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
  w.requirements = [{ req_id: "legacy-req", doc_id: source.id }];
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
              ? { route: "QA_FLOW", status: "ANSWER_VERIFIED" }
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
    await api.approveAndSend(serverDraft(), wid);
    assert.equal(captured.length, 6);
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
    assert.equal(body.allow_reconciliation, false);
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

test("model selection sends a provider only; credentials stay on the server", async () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    return new Response(
      JSON.stringify({ status: "ready", engine_mode: "ollama" }),
    );
  };
  try {
    await api.selectProvider("ollama");
    await api.selectProvider("gemini");
    assert.equal(calls[0].url, "/api/runtime/provider");
    assert.deepEqual(JSON.parse(calls[0].init.body), { provider: "ollama" });
    assert.deepEqual(JSON.parse(calls[1].init.body), { provider: "gemini" });
    const screen = readFileSync(resolve("src/AISettings.tsx"), "utf8");
    assert.ok(!screen.includes('type="password"'));
    assert.ok(!screen.includes("configureGemini"));
    assert.ok(!screen.includes("saveLocally"));
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
test("retired feature outputs are filtered from chat and Studio without rewriting history", () => {
  const workspace = notebook.notebookWorkspace(fixtures()[0]);
  const thread = workspace.threads[0];
  const question = thread.messages.find(
    (message) => message.state === "answer",
  );
  workspace.legacyThreads.push({
    id: "legacy-tasks",
    mode: "Tasks",
    view: "tasks",
  });
  workspace.studioResults.push({ id: "legacy-plan", kind: "plan" });
  const retired = [
    { mode: "Tasks" },
    { state: "suggestions" },
    { routeType: "RECONCILE_FLOW" },
    { kanbanEvent: { boardId: "old" } },
    { legacyThreadId: "legacy-tasks" },
    { studioResultId: "legacy-plan" },
  ].map((fields, index) => ({
    ...question,
    ...fields,
    id: `retired-${index}`,
    saved: true,
  }));
  thread.messages.push(...retired);
  const before = structuredClone(workspace);
  const visible = notebook.visibleChatMessages(workspace, thread);
  assert.ok(visible.some((message) => message.id === question.id));
  assert.ok(visible.every((message) => !message.id.startsWith("retired-")));
  assert.ok(
    notebook
      .visibleStudioResults(workspace)
      .every((result) => result.kind === "email"),
  );
  assert.deepEqual(workspace, before);
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
  workspace.studioResults.push({
    id: "pending",
    kind: "email",
    status: "generating",
  });
  assert.equal(
    notebook.notebookWorkspace(workspace, false).studioResults.at(-1).status,
    "generating",
  );
  const recovered = notebook.notebookWorkspace(workspace);
  assert.equal(recovered.studioResults.at(-1).status, "error");
  assert.match(recovered.studioResults.at(-1).error, /reloaded/);
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
