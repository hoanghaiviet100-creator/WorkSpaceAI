// Run after pnpm build. Disposable origin/profile only; no user workspace is touched.
import fs from "node:fs";
import assert from "node:assert/strict";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import ts from "typescript";
import { startFixture } from "./support/picker-server.mjs";
const { Browser, sleep } = await import(
  pathToFileURL(
    process.env.TASTE_CDP_PATH ||
      resolve("../../.agents/skills/design-taste-frontend/scripts/lib/cdp.mjs"),
  ).href
);
const out = resolve(".taste-skill/kanban-v10");
fs.mkdirSync(out, { recursive: true });
const seedCode = ts.transpileModule(fs.readFileSync("src/data.ts", "utf8"), {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
}).outputText;
const { seedWorkspaces } = await import(
  "data:text/javascript;base64," + Buffer.from(seedCode).toString("base64")
);
const workspace = {
  ...seedWorkspaces()[0],
  id: "picker-test",
  name: "Nghiên cứu học phần",
  notebookVersion: 1,
  kanban: undefined,
  sources: [],
  evidence: {},
  tasks: [],
  suggestions: [],
  requirements: [],
  reconciliationRuns: [],
  reconciledItems: [],
  studioResults: [],
  legacyThreads: [],
  threads: [
    {
      id: "single",
      title: "Hội thoại workspace",
      mode: "Ask",
      view: "chat",
      engineMode: "offline",
      updated: "2026-11-09",
      messages: [],
    },
  ],
};
const fixture = await startFixture({ workspace, outDir: out }),
  browser = await Browser.launch(),
  page = await browser.newPage({ width: 1440, height: 960 }),
  checks = [];
const state = () =>
  page.eval(() => JSON.parse(localStorage.getItem("workspaceai-v2"))[0]);
let sourceFixture;
async function click(selector) {
  await page.eval((s) => {
    const e = [...document.querySelectorAll(s)].find(
      (e) => e.getClientRects().length,
    );
    if (!e) throw Error("Missing " + s);
    e.click();
  }, selector);
  await sleep(90);
}
async function text(text, scope = "") {
  await page.eval(
    ({ text, scope }) => {
      const e = [
        ...document.querySelectorAll(scope ? scope + " button" : "button"),
      ].find((e) => e.getClientRects().length && e.textContent.trim() === text);
      if (!e) throw Error("Missing button " + text);
      e.click();
    },
    { text, scope },
  );
  await sleep(100);
}
async function fill(selector, value) {
  await page.eval(
    ({ selector, value }) => {
      const e = document.querySelector(selector);
      if (!e) throw Error(selector);
      Object.getOwnPropertyDescriptor(
        e instanceof HTMLTextAreaElement
          ? HTMLTextAreaElement.prototype
          : e instanceof HTMLSelectElement
            ? HTMLSelectElement.prototype
            : HTMLInputElement.prototype,
        "value",
      ).set.call(e, value);
      e.dispatchEvent(
        new Event(e instanceof HTMLSelectElement ? "change" : "input", {
          bubbles: true,
        }),
      );
    },
    { selector, value },
  );
  await sleep(60);
}
async function check(name, fn) {
  const result = await page.eval(fn);
  if (!result)
    console.log(
      await page.eval(() =>
        document.querySelector(".kb-board-modal")?.textContent.slice(0, 1800),
      ),
    );
  assert.equal(result, true, name);
  checks.push(name);
  console.log("PASS " + name);
}
async function shot(name) {
  await page.screenshot({ path: resolve(out, name + ".png"), format: "png" });
}
async function key(key, code, modifiers = 0) {
  await page.send("Input.dispatchKeyEvent", {
    type: "keyDown",
    ...(key === "Enter" ? { text: "\r", unmodifiedText: "\r" } : {}),
    key,
    code: key,
    windowsVirtualKeyCode: code,
    nativeVirtualKeyCode: code,
    modifiers,
  });
  await page.send("Input.dispatchKeyEvent", {
    type: "keyUp",
    key,
    code: key,
    windowsVirtualKeyCode: code,
    nativeVirtualKeyCode: code,
    modifiers,
  });
  await sleep(100);
}
async function drag(from, to) {
  const coords = await page.eval(
    ({ from, to }) => {
      const a = document.querySelector(from).getBoundingClientRect(),
        b = document.querySelector(to).getBoundingClientRect();
      return {
        a: { x: a.x + a.width / 2, y: a.y + a.height / 2 },
        b: { x: b.x + b.width / 2, y: b.y + Math.min(24, b.height / 2) },
      };
    },
    { from, to },
  );
  await page.send("Input.setInterceptDrags", { enabled: true });
  let off, timer;
  const intercepted = new Promise((resolve, reject) => {
    off = browser.on(page.sessionId, "Input.dragIntercepted", (event) => {
      clearTimeout(timer);
      off();
      resolve(event.data);
    });
    timer = setTimeout(() => {
      off();
      reject(Error("Native drag did not start"));
    }, 4000);
  });
  await page.send("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    ...coords.a,
  });
  await page.send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    ...coords.a,
    button: "left",
    clickCount: 1,
  });
  await page.send("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: coords.a.x + 12,
    y: coords.a.y + 12,
    button: "left",
    buttons: 1,
  });
  const data = await intercepted;
  data.dragOperationsMask = 16;
  for (const type of ["dragEnter", "dragOver", "drop"])
    await page.send("Input.dispatchDragEvent", { type, ...coords.b, data });
  await page.send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    ...coords.b,
    button: "left",
    clickCount: 1,
  });
  await page.send("Input.setInterceptDrags", { enabled: false });
  await sleep(160);
}
try {
  await page.goto(fixture.url, { settleMs: 250 });
  await click(".kb-summary .kb-open");
  await check(
    "empty workspace has one clear create action and no board saved",
    () =>
      !!document.querySelector(".kb-empty") &&
      !JSON.parse(localStorage.getItem("workspaceai-v2"))[0].kanban,
  );
  await shot("empty-desktop");
  await text("Tạo bảng Kanban từ gợi ý của AI", ".kb-board-modal");
  await check(
    "missing context shows an honest error and retry",
    () =>
      !!document.querySelector(".kb-error") &&
      [...document.querySelectorAll(".kb-empty button")].some(
        (e) => e.textContent === "Thử lại",
      ),
  );
  await text("Thử lại", ".kb-board-modal");
  await text("Xem bản mẫu 8 thẻ", ".kb-board-modal");
  await check(
    "sample preview has eight cards and saves nothing before confirmation",
    () =>
      document.querySelectorAll(".kb-preview-card").length === 8 &&
      !JSON.parse(localStorage.getItem("workspaceai-v2"))[0].kanban &&
      document
        .querySelector(".kb-preview-note")
        .textContent.includes("Bản mẫu"),
  );
  await fill('.kb-preview-column input:not([type="checkbox"])', "Cần ưu tiên");
  await fill(
    '.kb-preview-card input:not([type="checkbox"])',
    "Rà soát tài liệu nguồn",
  );
  await click('.kb-preview-card:last-child input[type="checkbox"]');
  await click(".kb-preview-card .kb-text");
  await fill(
    ".kb-card-editor textarea",
    "Đọc nguồn, đối chiếu yêu cầu và ghi lại các điểm chưa rõ.",
  );
  await fill('.kb-card-editor input[aria-label="Tên nhãn"]', "Nguồn");
  await click('[aria-label="Thêm nhãn"]');
  await fill(
    '.kb-card-editor input[aria-label="Thêm việc vào checklist"]',
    "Đối chiếu mục tiêu",
  );
  await click('[aria-label="Thêm checklist"]');
  await page.eval(() => {
    const label = [...document.querySelectorAll(".kb-card-editor label")].find(
      (e) => e.textContent.startsWith("Ghi chú"),
    );
    const e = label.querySelector("textarea");
    Object.getOwnPropertyDescriptor(
      HTMLTextAreaElement.prototype,
      "value",
    ).set.call(e, "Ghi chú được giữ sau khi di chuyển");
    e.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await shot("card-detail-desktop");
  await text("Lưu thay đổi", ".kb-card-editor");
  await shot("preview-desktop");
  await click(".kb-preview-footer .primary");
  let current = await state();
  assert.equal(current.kanban.cards.length, 7);
  assert.equal(current.kanban.columns[0].title, "Cần ưu tiên");
  assert.ok(
    current.kanban.cards.some(
      (c) =>
        c.title === "Rà soát tài liệu nguồn" &&
        c.checklist.length === 1 &&
        c.notes.includes("được giữ"),
    ),
  );
  checks.push(
    "edited selection, labels, notes and checklist survive confirmation",
  );
  await check(
    "confirmed board shows saved feedback and no create-second-board action",
    () =>
      document.querySelector(".kb-save").textContent === "Đã lưu" &&
      !document.querySelector(".kb-empty"),
  );
  const originalId = current.kanban.id,
    firstId = current.kanban.cards[0].id,
    colId = current.kanban.columns[0].id,
    secondCol = current.kanban.columns[1].id;
  await click(`[data-column-id="${colId}"] .kb-add-card`);
  await fill(
    `[data-column-id="${colId}"] .kb-quick-add input`,
    "Thẻ người dùng thêm nhanh",
  );
  await page.eval(
    (s) => document.querySelector(s).focus(),
    `[data-column-id="${colId}"] .kb-quick-add input`,
  );
  await key("Enter", 13);
  current = await state();
  assert.ok(
    current.kanban.cards.some(
      (c) => c.title === "Thẻ người dùng thêm nhanh" && c.origin === "manual",
    ),
  );
  checks.push("quick add plus Enter saves a manual card");
  await page.eval(
    (s) => document.querySelector(s).focus(),
    `[data-card-id="${firstId}"] .kb-grip`,
  );
  await key("ArrowRight", 39, 1);
  current = await state();
  assert.equal(
    current.kanban.cards.find((c) => c.id === firstId).columnId,
    secondCol,
  );
  checks.push("keyboard Alt plus Arrow moves a card between columns");
  await drag(
    `[data-card-id="${firstId}"] .kb-grip`,
    `[data-column-id="${colId}"] .kb-column-header`,
  );
  current = await state();
  assert.equal(
    current.kanban.cards.find((c) => c.id === firstId).columnId,
    colId,
  );
  checks.push("native pointer drag moves a card between columns");
  const otherId = current.kanban.cards.find(
    (c) => c.columnId === colId && c.id !== firstId,
  ).id;
  await drag(
    `[data-card-id="${firstId}"] .kb-grip`,
    `[data-card-id="${otherId}"]`,
  );
  current = await state();
  assert.ok(
    current.kanban.cards.findIndex((c) => c.id === firstId) <
      current.kanban.cards.findIndex((c) => c.id === otherId),
  );
  checks.push("native drag reorders cards within the same column");
  await drag(
    `[data-column-id="${secondCol}"] .kb-column-header .kb-grip`,
    `[data-column-id="${colId}"] .kb-column-header`,
  );
  current = await state();
  assert.equal(current.kanban.columns[0].id, secondCol);
  checks.push("native drag reorders columns");
  await click(`[data-card-id="${firstId}"] .kb-card-title`);
  await text("Nhân bản", ".kb-card-editor");
  current = await state();
  const duplicate = current.kanban.cards.find((c) =>
    c.title.includes("(bản sao)"),
  );
  assert.ok(
    duplicate &&
      duplicate.origin === "manual" &&
      duplicate.notes.includes("được giữ"),
  );
  await click(`[data-card-id="${duplicate.id}"] .kb-card-title`);
  await text("Xóa thẻ", ".kb-card-editor");
  assert.ok(!(await state()).kanban.cards.some((c) => c.id === duplicate.id));
  await text("Hoàn tác", ".kb-undo");
  assert.ok((await state()).kanban.cards.some((c) => c.id === duplicate.id));
  checks.push("duplicate, delete and targeted undo preserve card detail");
  await fill('[aria-label="Tìm kiếm thẻ"]', "không có kết quả");
  await check(
    "search filters without deleting data and shows an empty-column state",
    () =>
      !document.querySelector(".kb-card") &&
      document.querySelector(".kb-column-empty").textContent.includes("bộ lọc"),
  );
  await text("Xóa bộ lọc", ".kb-filters");
  await fill('[aria-label="Lọc ưu tiên"]', "high");
  await check(
    "priority filter shows only matching cards",
    () =>
      document.querySelectorAll(".kb-card").length === 1 &&
      !!document.querySelector('.kb-priority[data-priority="high"]'),
  );
  await text("Xóa bộ lọc", ".kb-filters");
  await fill('[aria-label="Lọc hạn chót"]', "overdue");
  await check(
    "deadline filter distinguishes overdue work",
    () =>
      document.querySelectorAll(".kb-card").length === 1 &&
      !!document.querySelector('.kb-due[data-state="overdue"]'),
  );
  await text("Xóa bộ lọc", ".kb-filters");
  await fill('[aria-label="Lọc nhãn"]', "Nguồn");
  await check(
    "label filter retains matching source-related cards",
    () => document.querySelectorAll(".kb-card").length === 2,
  );
  await text("Xóa bộ lọc", ".kb-filters");
  await text("Thêm cột", ".kb-filters");
  await fill('.modal[aria-label="Thêm cột"] input', "Chờ phản hồi");
  await text("Lưu cột", '.modal[aria-label="Thêm cột"]');
  current = await state();
  assert.equal(current.kanban.columns.length, 4);
  checks.push("manual column creation keeps the single board");
  await click('[aria-label="Tùy chọn cột Chờ phản hồi"]');
  await text("Đổi tên cột", ".nb-action-menu");
  await fill(
    '.modal[aria-label="Chỉnh sửa cột"] input:not([type="checkbox"])',
    "Chờ duyệt",
  );
  await text("Lưu cột", '.modal[aria-label="Chỉnh sửa cột"]');
  assert.ok(
    (await state()).kanban.columns.some((col) => col.title === "Chờ duyệt"),
  );
  const countBeforeDelete = (await state()).kanban.cards.length;
  await click('[aria-label="Tùy chọn cột Đang làm"]');
  await text("Xóa cột", ".nb-action-menu");
  await text(
    "Xóa cột và chuyển thẻ",
    '.modal[aria-label="Xóa cột, giữ lại công việc"]',
  );
  current = await state();
  assert.equal(current.kanban.cards.length, countBeforeDelete);
  assert.equal(current.kanban.columns.length, 3);
  assert.ok(
    current.kanban.cards.every((card) =>
      current.kanban.columns.some((col) => col.id === card.columnId),
    ),
  );
  checks.push(
    "rename and delete a populated column preserve every card by relocation",
  );
  await page.eval(() => {
    const rows = JSON.parse(localStorage.getItem("workspaceai-v2"));
    rows[0].threads[0].messages.push({
      id: "fresh",
      origin: "server",
      request: "Cần chuẩn bị hồ sơ trao đổi mới trước 2026-12-21.",
      mode: "Ask",
      state: "answer",
      at: "2026-11-09",
      sourceIds: [],
      evidenceIds: [],
    });
    localStorage.setItem("workspaceai-v2", JSON.stringify(rows));
  });
  await page.goto(fixture.url, { settleMs: 200 });
  await click(".kb-summary .kb-open");
  const before = structuredClone((await state()).kanban.cards);
  assert.ok(
    (await state()).threads[0].messages.some(
      (message) => message.id === "fresh",
    ),
    "fresh conversation restored",
  );
  await text("Nhờ AI gợi ý thêm", ".kb-board-modal");
  await check(
    "additional suggestions are previewed without modifying the confirmed board",
    () =>
      !!document.querySelector(".kb-preview-note") &&
      document
        .querySelector(".kb-preview-note")
        .textContent.includes("Chưa thêm vào bảng"),
  );
  await click(".kb-preview-footer .primary");
  current = await state();
  assert.equal(current.kanban.id, originalId);
  assert.equal(current.kanban.cards.length, before.length + 1);
  assert.deepEqual(current.kanban.cards.slice(0, before.length), before);
  checks.push(
    "append keeps all existing edited cards and adds only the confirmed new card",
  );
  await shot("board-desktop-light");
  await click('[aria-label="Thu nhỏ về Studio"]');
  await shot("studio-summary-light");
  await check(
    "Studio summary and shared chat contain a clickable Kanban event",
    () =>
      !!document.querySelector(".kb-summary progress") &&
      [...document.querySelectorAll(".nb-studio-event button")].some((e) =>
        e.textContent.includes("Kanban"),
      ),
  );
  await page.eval(() =>
    [...document.querySelectorAll(".nb-studio-event button")]
      .find((e) => e.textContent.includes("Kanban"))
      .click(),
  );
  await sleep(80);
  await check(
    "chat event opens the same expanded board",
    () => !!document.querySelector(".kb-board-modal"),
  );
  for (const [width, height] of [
    [1024, 800],
    [768, 1024],
    [390, 844],
    [320, 780],
  ]) {
    await page.setViewport({ width, height, mobile: width < 768 });
    await sleep(100);
    await check(
      `Kanban stays in the viewport at ${width}px`,
      () =>
        document.documentElement.scrollWidth <= innerWidth + 1 &&
        document.querySelector(".kb-board-modal").getBoundingClientRect()
          .right <=
          innerWidth + 1 &&
        document.querySelector(".kb-lanes").scrollWidth > 0,
    );
    if (width < 768) {
      await click(".kb-mobile-dots button:last-child");
      await sleep(350);
      await check(
        `phone ${width}px switches a complete lane with accessible indicators`,
        () =>
          document.querySelector(".kb-lanes").scrollLeft > 0 &&
          !!document.querySelector('.kb-mobile-dots [aria-pressed="true"]'),
      );
      await check(`phone ${width}px actions have 44px touch targets`, () =>
        [...document.querySelectorAll(".kb-board-modal button")]
          .filter((e) => e.getClientRects().length)
          .every((e) => e.getBoundingClientRect().height >= 43.5),
      );
      await click(".kb-mobile-dots button:first-child");
      await sleep(350);
      if (width === 390) {
        const touch = await page.eval(() => {
          const cards = [
            ...document.querySelectorAll(".kb-column:first-child .kb-card"),
          ];
          const from = cards[1]
              .querySelector(".kb-grip")
              .getBoundingClientRect(),
            to = cards[0]
              .querySelector(".kb-card-title")
              .getBoundingClientRect();
          return {
            id: cards[1].dataset.cardId,
            before: cards[0].dataset.cardId,
            from: { x: from.x + from.width / 2, y: from.y + from.height / 2 },
            to: { x: to.x + to.width / 2, y: to.y + to.height / 2 },
          };
        });
        await page.send("Input.dispatchTouchEvent", {
          type: "touchStart",
          touchPoints: [touch.from],
        });
        await page.send("Input.dispatchTouchEvent", {
          type: "touchMove",
          touchPoints: [touch.to],
        });
        await page.send("Input.dispatchTouchEvent", {
          type: "touchEnd",
          touchPoints: [],
        });
        await sleep(140);
        current = await state();
        assert.ok(
          current.kanban.cards.findIndex((card) => card.id === touch.id) <
            current.kanban.cards.findIndex((card) => card.id === touch.before),
        );
        checks.push("touch handle drag reorders cards on a phone");
      }
    }
    await shot(`board-${width}-light`);
  }
  await page.eval(() => localStorage.setItem("wai-theme", "dark"));
  await page.goto(fixture.url, { settleMs: 200 });
  await page.setViewport({ width: 1440, height: 960 });
  await click(".kb-summary .kb-open");
  await shot("board-desktop-dark");
  current = await state();
  assert.equal(current.kanban.id, originalId);
  assert.equal(
    current.kanban.cards.find((c) => c.id === firstId).notes,
    "Ghi chú được giữ sau khi di chuyển",
  );
  checks.push(
    "reload and theme switch retain the same board and rich card details",
  );
  sourceFixture = await startFixture({
    workspace: { ...workspace, name: "Nguồn kiểm thử" },
    outDir: resolve(out, "source-fixture"),
    pageDelay: 650,
    documents: [
      {
        doc_id: "study-source",
        doc_name: "Study brief.txt",
        file_type: "txt",
        file_hash: "source-fixture-hash",
        version_id: "v1",
        page_count: 1,
        chunk_count: 1,
        total_lines: 3,
        is_selected: true,
      },
    ],
  });
  await page.goto(sourceFixture.url, { settleMs: 250 });
  await click(".kb-summary .kb-open");
  await text("Tạo bảng Kanban từ gợi ý của AI", ".kb-board-modal");
  await check(
    "reading source text shows a real loading state",
    () => !!document.querySelector('.kb-generation[aria-busy="true"]'),
  );
  await shot("loading-source-desktop");
  await sleep(750);
  await check(
    "processed selected source produces an Offline preview with no saved board",
    () =>
      document.querySelectorAll(".kb-preview-card").length === 3 &&
      !JSON.parse(localStorage.getItem("workspaceai-v2"))[0].kanban &&
      document
        .querySelector(".kb-preview-note")
        .textContent.includes("Gợi ý Offline"),
  );
  await click(".kb-preview-footer .primary");
  current = await state();
  assert.equal(current.kanban.cards.length, 3);
  assert.ok(
    current.kanban.cards.every((card) =>
      card.sourceIds.includes("study-source"),
    ),
  );
  assert.ok(current.kanban.cards.some((card) => card.dueDate === "2026-12-20"));
  checks.push(
    "source-derived cards retain their source ID and explicit deadline after confirmation",
  );
  await click(".kb-card-title");
  await check(
    "card editor links the actual source",
    () => !!document.querySelector(".kb-source-options input:checked"),
  );
  await click('.kb-card-editor [aria-label="Close dialog"]');
  await shot("board-source-desktop");
  assert.deepEqual(page.consoleErrors, []);
  assert.ok(
    ![...fixture.calls, ...sourceFixture.calls].some(
      (c) =>
        c.path.includes("/chat") ||
        c.path.includes("/email") ||
        c.path.includes("gemini"),
    ),
  );
  checks.push("no browser errors, model calls or email dispatch");
  console.log(`PASS ${checks.length} Kanban browser checks`);
} finally {
  fs.writeFileSync(
    resolve(out, "browser-checks.json"),
    JSON.stringify(
      {
        checks,
        calls: [...fixture.calls, ...(sourceFixture?.calls || [])],
        errors: page.consoleErrors,
      },
      null,
      2,
    ),
  );
  await browser.close();
  if (sourceFixture) await sourceFixture.close();
  await fixture.close();
}
