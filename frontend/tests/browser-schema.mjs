import fs from "node:fs";
import { createServer } from "node:http";
import { resolve, extname, sep } from "node:path";
import { pathToFileURL } from "node:url";
import { homedir } from "node:os";
const cdp =
  process.env.TASTE_SKILL_CDP ||
  resolve(homedir(), ".codex/skills/design-taste-frontend/scripts/lib/cdp.mjs");
const { Browser, sleep } = await import(pathToFileURL(cdp).href);
const root = resolve(process.argv[2] || "dist"),
  live = process.argv.includes("--live");
const out = resolve(".taste-skill/review-schema" + (live ? "-live" : "-local"));
fs.mkdirSync(out, { recursive: true });
const calls = [],
  results = [];
let emailOutcome = "sent",
  serverDocuments = [
    {
      doc_id: "server-doc",
      doc_name: "Project.md",
      file_type: "md",
      page_count: 1,
      chunk_count: 2,
      total_lines: 5,
      file_hash: "c".repeat(64),
      version_id: "v1",
      is_selected: true,
    },
  ];
const report = {
  coverage_ratio: 0.5,
  overdue_count: 0,
  conflict_count: 1,
  item_reports: [
    {
      req_id: "R1",
      title: "Server requirement complete",
      state: "COMPLETED",
      risk_level: "LOW",
      avg_completion: 100,
      days_remaining: 3,
      owners: ["Alex"],
      date_conflicts: [],
      citations: ["Project.md p. 1"],
    },
    {
      req_id: "R8",
      title: "Server deadline mismatch",
      state: "IN_PROGRESS",
      risk_level: "MEDIUM",
      avg_completion: 20,
      days_remaining: 3,
      owners: ["Sam"],
      date_conflicts: [
        {
          doc_a: "Official",
          date_a: "2026-11-09",
          doc_b: "Team",
          date_b: "2026-11-08",
        },
      ],
      citations: ["Team.csv row 2"],
    },
  ],
};
const server = createServer(async (req, res) => {
  if (req.url.startsWith("/api")) {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const raw = Buffer.concat(chunks).toString();
    let body = {};
    try {
      body = JSON.parse(raw);
    } catch {}
    calls.push({ method: req.method, path: req.url, body });
    res.setHeader("content-type", "application/json");
    if (req.url.startsWith("/api/documents/select")) {
      serverDocuments = serverDocuments.map((d) => ({
        ...d,
        is_selected: body.selected_doc_ids.includes(d.doc_id),
      }));
      res.end(JSON.stringify({ status: "SELECTION_UPDATED" }));
      return;
    }
    if (req.url === "/api/documents") {
      res.end(JSON.stringify(serverDocuments));
      return;
    }
    if (req.url.startsWith("/api/email/approve/")) {
      if (emailOutcome === "uncertain") {
        res.destroy();
        return;
      }
      res.end(JSON.stringify({ status: "SENT", dispatch_mode: "local_mock" }));
      return;
    }
    if (req.url === "/api/chat") {
      if (/reconcile/i.test(body.query)) {
        res.end(
          JSON.stringify({
            route: "RECONCILE_FLOW",
            status: "RECONCILIATION_COMPLETE",
            reconciliation_report: report,
          }),
        );
        return;
      }
      if (/draft.*email/i.test(body.query)) {
        res.end(
          JSON.stringify({
            route: "EMAIL_FLOW",
            status: "PENDING_APPROVAL",
            draft: {
              draft_id:
                emailOutcome === "uncertain" ? "draft_002" : "draft_001",
              recipient_email: body.recipient_email,
              subject: "Server subject",
              body: "Review this server-generated message.",
              attachment_ids: [],
              citations: ["Project.md p. 1"],
              state: "PENDING_APPROVAL",
              payload_hash: (emailOutcome === "uncertain" ? "b" : "a").repeat(
                64,
              ),
            },
          }),
        );
        return;
      }
      res.end(
        JSON.stringify({
          route: "QA_FLOW",
          status: "ANSWER_VERIFIED",
          grounding_score: 0.8,
          validated_claims: [
            {
              claim_text: "The official deadline is November 9.",
              cited_doc_id: "server-doc",
              cited_page: 1,
              cited_start_line: 2,
              cited_end_line: 3,
              evidence_quote: "Submit by November 9.",
              verification_status: "VERIFIED_EXACT",
              match_score: 1,
              doc_version: "v1",
              doc_hash: "c".repeat(64),
            },
            {
              claim_text: "UNSAFE CLAIM MUST BE HIDDEN",
              cited_doc_id: "server-doc",
              cited_page: 99,
              evidence_quote: "No source",
              verification_status: "OUT_OF_BOUNDS",
              match_score: 0,
            },
            {
              claim_text: "OUT OF SCOPE MUST BE HIDDEN",
              cited_doc_id: "unselected-doc",
              cited_page: 1,
              evidence_quote: "Elsewhere",
              verification_status: "VERIFIED_EXACT",
              match_score: 1,
            },
          ],
          hallucination_flags: [
            {
              claim_text: "HALLUCINATION MUST BE HIDDEN",
              verification_status: "HALLUCINATED_CLAIM",
            },
          ],
        }),
      );
      return;
    }
    res.writeHead(404);
    res.end(JSON.stringify({ detail: "No endpoint" }));
    return;
  }
  try {
    let path = resolve(
      root,
      "." + decodeURIComponent(new URL(req.url, "http://x").pathname),
    );
    if (path !== root && !path.startsWith(root + sep))
      throw Error("Invalid path");
    if (fs.statSync(path).isDirectory()) path = resolve(path, "index.html");
    res.setHeader(
      "content-type",
      {
        ".html": "text/html",
        ".js": "text/javascript",
        ".css": "text/css",
        ".woff2": "font/woff2",
        ".woff": "font/woff",
      }[extname(path)] || "application/octet-stream",
    );
    res.end(fs.readFileSync(path));
  } catch {
    res.writeHead(404);
    res.end();
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await Browser.launch(),
  page = await browser.newPage({ width: 1440, height: 1000 });
let visit = 0;
const go = async (view) =>
  page.goto(
    `${base}/?v=${visit++}#workspace/midterm/${view}/midterm-deadline`,
    { settleMs: 200 },
  );
const check = async (name, fn, arg) => {
  const value = await page.eval(fn, arg);
  const pass = value === true;
  results.push({ name, pass, detail: value });
  if (!pass) throw new Error(name + ": " + JSON.stringify(value));
  console.log("PASS " + name);
};
const click = async (selector) => {
  await page.eval((s) => {
    const el = document.querySelector(s);
    if (!el) throw Error("Missing " + s);
    el.click();
  }, selector);
  await sleep(100);
};
const textClick = async (text, selector = "button") => {
  await page.eval(
    ({ text, selector }) => {
      const el = [...document.querySelectorAll(selector)].find(
        (e) =>
          e.getClientRects().length && e.textContent.trim().startsWith(text),
      );
      if (!el) throw Error("Missing visible button " + text);
      el.click();
    },
    { text, selector },
  );
  await sleep(100);
};
const input = async (selector, value) => {
  await page.eval(
    ({ selector, value }) => {
      const el = document.querySelector(selector);
      if (!el) throw Error("Missing " + selector);
      const proto =
        el.tagName === "SELECT"
          ? HTMLSelectElement.prototype
          : el.tagName === "TEXTAREA"
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
      el.dispatchEvent(
        new Event(el.tagName === "SELECT" ? "change" : "input", {
          bubbles: true,
        }),
      );
    },
    { selector, value },
  );
  await sleep(50);
};
const field = async (label, value) => {
  const selector = await page.eval((label) => {
    const row = [...document.querySelectorAll(".modal form label")].find(
      (e) => e.firstChild?.textContent.trim() === label,
    );
    if (!row) throw Error("No form label " + label);
    const el = row.querySelector("input,select,textarea");
    el.dataset.testField = "current";
    return '[data-test-field="current"]';
  }, label);
  await input(selector, value);
  await page.eval(() =>
    document
      .querySelector('[data-test-field="current"]')
      .removeAttribute("data-test-field"),
  );
};
const screenshot = async (name) =>
  page.screenshot({
    path: resolve(out, name + ".png"),
    format: "png",
    fullPage: false,
  });
try {
  await go("tasks");
  await check(
    "Existing shell, font and 4 workflow states remain",
    () =>
      !!document.querySelector(".workspace-layout") &&
      getComputedStyle(document.body).fontFamily.includes("Be Vietnam Pro") &&
      document.querySelector('[aria-label="Filter tasks by status"]').options
        .length === 5,
  );
  await textClick("Requirements", ".tabs button");
  await check(
    "Requirements show mandatory flag, deadline and linked tasks",
    () =>
      document.querySelectorAll(".requirement-row").length === 5 &&
      document
        .querySelector(".requirement-row")
        .innerText.includes("2026-11-06") &&
      document
        .querySelector(".requirement-row")
        .innerText.includes("Mandatory"),
  );
  await textClick("Add requirement");
  await field("Title", "Schema test requirement");
  await field("Official deadline", "2026-11-20");
  await field("Keywords (comma separated)", "testing, integration");
  await textClick("Save requirement");
  await check(
    "Requirement creates and persists with source-ready schema fields",
    () =>
      JSON.parse(localStorage.getItem("workspaceai-v2"))[0].requirements.some(
        (r) =>
          r.title === "Schema test requirement" &&
          r.official_deadline === "2026-11-20" &&
          r.mandatory_flag &&
          r.keywords[1] === "integration",
      ),
  );
  await page.eval(() =>
    [...document.querySelectorAll(".requirement-row")]
      .find((e) => e.innerText.includes("Schema test requirement"))
      .querySelector(".requirement-actions .button")
      .click(),
  );
  await sleep(100);
  await textClick("Task board", ".tabs button");
  await click('[aria-label="Edit Schema test requirement"]');
  await field("Status", "REVIEW");
  await field("Completion (%)", "45.5");
  await field("Additional label", "Blocked");
  await textClick("Save changes");
  await check(
    "Task mapping, fractional completion and legacy label are independent",
    () => {
      const t = JSON.parse(
        localStorage.getItem("workspaceai-v2"),
      )[0].tasks.find((t) => t.title === "Schema test requirement");
      return (
        t.status === "REVIEW" &&
        t.completionPct === 45.5 &&
        t.localLabel === "Blocked" &&
        !!t.mappedReqId &&
        document
          .querySelector('[data-lane="In Review"]')
          .innerText.includes("45.5%")
      );
    },
  );
  await input('[aria-label="Status of Schema test requirement"]', "DONE");
  await check(
    "Completing a task records 100 percent",
    () =>
      JSON.parse(localStorage.getItem("workspaceai-v2"))[0].tasks.find(
        (t) => t.title === "Schema test requirement",
      ).completionPct === 100,
  );
  await textClick("Requirements", ".tabs button");
  await click('[aria-label="Delete requirement Schema test requirement"]');
  await textClick("Delete requirement", ".modal .button.primary");
  await check("Deleting a requirement preserves and unlinks its task", () => {
    const w = JSON.parse(localStorage.getItem("workspaceai-v2"))[0];
    return (
      !w.requirements.some((r) => r.title === "Schema test requirement") &&
      w.tasks.some(
        (t) => t.title === "Schema test requirement" && !t.mappedReqId,
      )
    );
  });
  await textClick("Reconciliation", ".tabs button");
  if (!live) {
    await check(
      "Disconnected report has no invented coverage or results",
      () =>
        document
          .querySelector(".reconciliation-screen")
          .innerText.includes("No reconciliation runs yet") &&
        document.querySelector(".reconciliation-screen button.primary")
          .disabled &&
        !document.querySelector(".reconciliation-metrics"),
    );
  } else {
    await textClick("Run reconciliation");
    await sleep(300);
    await check(
      "Server report shows coverage, conflicts, owners and state adaptation",
      () =>
        document
          .querySelector(".reconciliation-metrics")
          .innerText.includes("50%") &&
        document
          .querySelector(".reconciliation-list")
          .innerText.includes("Deadline conflict") &&
        document
          .querySelector(".reconciliation-list")
          .innerText.includes("Sam"),
    );
    await textClick("Run reconciliation");
    await sleep(200);
    await check(
      "Run history preserves previous report snapshots",
      () =>
        document.querySelector('[aria-label="Reconciliation history"]').options
          .length === 2,
    );
  }
  await screenshot("reconciliation-desktop");
  if (live) {
    await textClick("Sync server library");
    await sleep(150);
    await check(
      "Server library sync keeps local samples and selects actual server files",
      () => {
        const w = JSON.parse(localStorage.getItem("workspaceai-v2"))[0];
        return (
          w.sources.length === 13 &&
          w.sources
            .filter((s) => s.selected)
            .every((s) => s.origin === "server")
        );
      },
    );
    await click('[aria-label="Use Project.md"]');
    await click('[aria-label="Use Project.md"]');
    await check(
      "Document selection uses the real server selection endpoint",
      (calls) =>
        calls.filter((c) => c.path === "/api/documents/select").length === 2 &&
        calls.filter((c) => c.path === "/api/documents/select").at(-1).body
          .selected_doc_ids[0] === "server-doc",
      calls,
    );
    await go("chat");
    await input(
      '[aria-label="Message your workspace"]',
      "What is the official deadline?",
    );
    await click('[aria-label="Send message"]');
    await sleep(250);
    await check(
      "Live Q&A displays only verified claims from selected documents",
      () => {
        const last = [...document.querySelectorAll(".exchange")].at(-1);
        return (
          last.innerText.includes("The official deadline is November 9.") &&
          last.innerText.includes("VERIFIED EXACT") &&
          last.innerText.includes("3 unsupported claims") &&
          !last.innerText.includes("MUST BE HIDDEN") &&
          last.innerText.includes("80%")
        );
      },
    );
    await page.eval(() =>
      [...document.querySelectorAll(".exchange")]
        .at(-1)
        .querySelector(".citation")
        .click(),
    );
    await sleep(80);
    await check(
      "Citation viewer shows page/line/version/hash without forging page text",
      () =>
        document.querySelector(".modal").innerText.includes("lines 2–3") &&
        document.querySelector(".modal").innerText.includes("v1") &&
        document
          .querySelector(".modal")
          .innerText.includes("not available in the current API"),
    );
    await click('.modal [aria-label="Close dialog"]');
  } else {
    await go("chat");
    await check(
      "Sample answers are explicitly unverified",
      () =>
        document
          .querySelector(".answer")
          .innerText.includes("Sample conversation") &&
        document
          .querySelector(".answer")
          .innerText.includes("Unverified sample"),
    );
    await input('[aria-label="Session engine preference"]', "gemini");
    await check("Engine preference does not change the action mode", () => {
      const t = JSON.parse(
        localStorage.getItem("workspaceai-v2"),
      )[0].threads.find((t) => t.id === "midterm-deadline");
      return t.engineMode === "gemini" && t.mode === "Ask";
    });
    const uploadText = async (name) => {
      await page.eval((name) => {
        const transfer = new DataTransfer();
        transfer.items.add(
          new File(["# Original text\nLine two"], name, {
            type: "text/markdown",
          }),
        );
        const el = document.querySelector('input[type="file"]');
        el.files = transfer.files;
        el.dispatchEvent(new Event("change", { bubbles: true }));
      }, name);
      await sleep(200);
    };
    await uploadText("schema-notes.md");
    await check(
      "Markdown upload records actual hash, size, version and page text",
      () => {
        const s = JSON.parse(
          localStorage.getItem("workspaceai-v2"),
        )[0].sources.find((s) => s.name === "schema-notes.md");
        return (
          !!s &&
          /^[a-f0-9]{64}$/.test(s.fileHash) &&
          s.totalLines === 2 &&
          s.versionId === "v1" &&
          s.pages[0].raw_text.includes("Line two") &&
          !s.selected &&
          s.status === "Preview only"
        );
      },
    );
    await uploadText("same-content.md");
    await check(
      "File content deduplication preserves a single local record",
      () =>
        !JSON.parse(localStorage.getItem("workspaceai-v2"))[0].sources.some(
          (s) => s.name === "same-content.md",
        ),
    );
    await click('[aria-label="Show details for schema-notes.md"]');
    await page.eval(() =>
      [...document.querySelectorAll(".source-row")]
        .find((r) => r.innerText.includes("schema-notes.md"))
        .querySelector(".text-button")
        .click(),
    );
    await sleep(100);
    await check(
      "Original text viewer shows real numbered lines",
      () =>
        document.querySelectorAll(".document-lines li").length === 2 &&
        document
          .querySelector(".document-lines")
          .innerText.includes("Line two"),
    );
    await click('.modal [aria-label="Close dialog"]');
  }
  await screenshot("chat-desktop");
  if (live) {
    await input(
      '[aria-label="Message your workspace"]',
      "Reconcile requirement coverage",
    );
    await click('[aria-label="Send message"]');
    await sleep(250);
    await textClick("Open Tasks & reconciliation");
    await check(
      "A chat reconciliation result opens its report tab directly",
      () =>
        document.querySelector(".reconciliation-screen")?.getClientRects()
          .length > 0 &&
        document.querySelector(".tasks-screen .tabs .selected").innerText ===
          "Reconciliation",
    );
  }
  await go("email");
  await input('[aria-label="CC recipients"]', "");
  await input('[aria-label="Email recipients"]', "person@example.org");
  await input('[aria-label="Email subject"]', "Subject for schema test");
  await input('[aria-label="Email body"]', "Check this version carefully.");
  if (live) {
    await textClick("Request a new server draft");
    await sleep(200);
  }
  await textClick("Review exact version");
  await check(
    "Review snapshot includes attachment list and full SHA-256",
    () =>
      document.querySelector(".modal").innerText.includes("Attachments") &&
      /[a-f0-9]{64}/.test(document.querySelector(".fingerprint").innerText),
  );
  await textClick("Confirm review");
  if (!live)
    await check(
      "Local review never claims server approval or enables sending",
      () =>
        document
          .querySelector(".email-titlebar")
          .innerText.includes("Local draft") &&
        [...document.querySelectorAll(".send-controls button")].every(
          (b) => b.disabled,
        ),
    );
  await input('[aria-label="Email body"]', "A changed version.");
  await check(
    "Content edit invalidates the reviewed snapshot",
    () =>
      document
        .querySelector(".approval-summary")
        .innerText.includes("draft changed") &&
      document.querySelector(".send-controls button").disabled,
  );
  await page.eval(
    () => (document.querySelector(".email-attachments").open = true),
  );
  await click('.email-attachments input[type="checkbox"]');
  await textClick("Review exact version");
  await check("Attachment selection appears in approval snapshot", () =>
    document.querySelector(".modal").innerText.includes("Assignment_Spec.pdf"),
  );
  await textClick("Confirm review");
  await check(
    "Attachment changes cannot bypass the server capability boundary",
    () => document.querySelector(".send-controls button").disabled,
  );
  await screenshot("email-desktop");
  if (live) {
    await click('.email-attachments input[type="checkbox"]');
    await textClick("Request a new server draft");
    await sleep(200);
    await textClick("Review exact version");
    await textClick("Confirm review");
    await textClick("Approve & send");
    await sleep(200);
    await check(
      "Mock dispatch is clearly distinguished from real delivery and blocks duplicates",
      () =>
        document
          .querySelector(".send-controls")
          .innerText.includes("no real email sent") &&
        document.querySelector(".send-controls button").disabled,
    );
    // A new test-only server draft exercises an uncertain network outcome, with no real mail service.
    emailOutcome = "uncertain";
    await page.eval(() => {
      const w = JSON.parse(localStorage.getItem("workspaceai-v2"));
      const d = w[0].draft;
      d.currentState = "IDLE";
      d.id = undefined;
      d.payloadHash = undefined;
      d.origin = "local";
      delete d.serverSnapshot;
      w[0].draft = d;
      localStorage.setItem("workspaceai-v2", JSON.stringify(w));
    });
    await go("email");
    await textClick("Request a new server draft");
    await sleep(200);
    await textClick("Review exact version");
    await textClick("Confirm review");
    await textClick("Approve & send");
    await sleep(250);
    await check(
      "Unknown send outcome locks the existing draft instead of fabricating SENT",
      () =>
        document
          .querySelector(".approval-section")
          .innerText.includes("outcome needs checking") &&
        document.querySelector(".send-controls button").disabled &&
        !document
          .querySelector(".email-titlebar")
          .innerText.includes("Server accepted"),
    );
    await go("email");
    await check(
      "Submission lock survives reload",
      () =>
        document
          .querySelector(".approval-section")
          .innerText.includes("outcome needs checking") &&
        document.querySelector(".send-controls button").disabled,
    );
  }
  for (const theme of ["light", "dark"]) {
    await page.eval((t) => localStorage.setItem("wai-theme", t), theme);
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewport({ width, height: 1000 });
      for (const view of ["chat", "tasks", "email"]) {
        await go(view);
        if (view === "tasks") await textClick("Requirements", ".tabs button");
        await check(
          `${view} ${theme} ${width}px has no page overflow`,
          () =>
            document.documentElement.scrollWidth <= innerWidth + 1 &&
            !document.querySelector("#root:empty"),
        );
        if (width === 390 || width === 1440)
          await screenshot(`${view}-${theme}-${width}`);
      }
    }
  }
  await check(
    "No unhandled browser runtime errors",
    (errors) => errors.length === 0,
    page.consoleErrors.filter(
      (e) =>
        !String(e).includes("Failed to load resource") &&
        !String(e).includes("ERR_EMPTY_RESPONSE"),
    ),
  );
  console.log(
    `${results.length} browser checks passed (${live ? "mock API" : "standalone"}).`,
  );
} catch (error) {
  await screenshot("failure");
  console.error(error);
  process.exitCode = 1;
} finally {
  fs.writeFileSync(
    resolve(out, "results.json"),
    JSON.stringify({ results, calls }, null, 2),
  );
  await browser.close();
  server.close();
}
