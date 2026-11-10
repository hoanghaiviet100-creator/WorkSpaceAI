import fs from "node:fs";
import { createServer } from "node:http";
import { resolve, extname, sep } from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { homedir } from "node:os";
const { Browser, sleep } = await import(
  pathToFileURL(
    process.env.TASTE_SKILL_CDP ||
      resolve(
        homedir(),
        ".codex/skills/design-taste-frontend/scripts/lib/cdp.mjs",
      ),
  ).href
);
const cloudForm = process.argv.includes("--cloud-form");
const root = resolve("dist"),
  repo = resolve(".."),
  out = resolve(
    cloudForm
      ? ".taste-skill/review-feature1-cloud-form"
      : ".taste-skill/review-feature1-offline",
  );
fs.mkdirSync(out, { recursive: true });
const python =
  process.env.WORKSPACE_PYTHON ||
  resolve(repo, "../.venv-schema-audit/Scripts/python.exe");
const backend = spawn(
  python,
  ["-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "0"],
  {
    cwd: repo,
    windowsHide: true,
    env: {
      ...process.env,
      LLM_PROVIDER: "mock",
      WORKSPACE_OFFLINE_ONLY: cloudForm ? "false" : "true",
      EMAIL_DISPATCH_MODE: "local_mock",
      GEMINI_API_KEY: "",
      GMAIL_APP_PASSWORD: "",
      HF_HUB_OFFLINE: "1",
      PYTHONIOENCODING: "utf-8",
    },
  },
);
let backendLog = "",
  backendPort,
  browser,
  page,
  server;
for (const stream of [backend.stdout, backend.stderr])
  stream.on("data", (chunk) => {
    backendLog = (backendLog + chunk).slice(-6000);
    const match = /Uvicorn running on http:\/\/127\.0\.0\.1:(\d+)/.exec(
      backendLog,
    );
    if (match) backendPort = Number(match[1]);
  });
const results = [];
let apiQuestions = 0;
const fakeKey = "ui-test-not-a-real-api-key-6194";
try {
  for (let i = 0; !backendPort && i < 80; i++) await sleep(200);
  if (!backendPort)
    throw new Error("Test backend did not start: " + backendLog);
  const backendBase = `http://127.0.0.1:${backendPort}`;
  server = createServer(async (req, res) => {
    if (req.url.startsWith("/api")) {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const bytes = Buffer.concat(chunks);
      // Only the credential form response is mocked; document ingestion and Q&A use FastAPI.
      if (cloudForm && req.url === "/api/runtime/gemini") {
        res.setHeader("content-type", "application/json");
        res.end(
          JSON.stringify({
            status: "ready",
            engine_mode: "gemini",
            model: "gemini-test",
            gemini_configured: true,
          }),
        );
        return;
      }
      if (req.url === "/api/chat") apiQuestions++;
      try {
        const response = await fetch(backendBase + req.url, {
          method: req.method,
          headers: {
            ...(req.headers["content-type"]
              ? { "content-type": req.headers["content-type"] }
              : {}),
            ...(req.headers["x-workspace-id"]
              ? { "X-Workspace-ID": req.headers["x-workspace-id"] }
              : {}),
          },
          ...(bytes.length ? { body: bytes } : {}),
        });
        res.writeHead(response.status, {
          "content-type":
            response.headers.get("content-type") || "application/json",
        });
        res.end(Buffer.from(await response.arrayBuffer()));
      } catch {
        res.writeHead(502);
        res.end();
      }
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
  browser = await Browser.launch();
  page = await browser.newPage({ width: 1440, height: 1000 });
  const check = async (name, fn, arg) => {
    const value = await page.eval(fn, arg);
    results.push({ name, pass: value === true, detail: value });
    if (value !== true) throw new Error(name + ": " + JSON.stringify(value));
    console.log("PASS " + name);
  };
  const click = async (selector) => {
    await page.eval((s) => {
      const el = document.querySelector(s);
      if (!el) throw new Error("Missing " + s);
      el.click();
    }, selector);
    await sleep(100);
  };
  const input = async (selector, value) => {
    await page.eval(
      ({ selector, value }) => {
        const el = document.querySelector(selector);
        const proto =
          el.tagName === "TEXTAREA"
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, "value").set.call(el, value);
        el.dispatchEvent(new Event("input", { bubbles: true }));
      },
      { selector, value },
    );
    await sleep(50);
  };
  const until = async (fn) => {
    for (let i = 0; i < 100; i++) {
      if (await page.eval(fn)) return;
      await sleep(100);
    }
    throw new Error("Timed out waiting for the real API");
  };
  await page.goto(base + "/#workspace/midterm/chat/midterm-deadline", {
    settleMs: 300,
  });
  await until(() =>
    JSON.parse(localStorage.getItem("workspaceai-v2"))[0].sources.some(
      (s) => s.origin === "server",
    ),
  );
  await check("Server library synchronizes automatically", () =>
    JSON.parse(localStorage.getItem("workspaceai-v2"))[0].sources.some(
      (s) => s.origin === "server" && s.status === "Processed",
    ),
  );
  await page.eval(() => {
    const transfer = new DataTransfer();
    transfer.items.add(
      new File(
        [
          "WorkspaceAI live verification.\nThe verification code is WAI-LIVE-6194. The report deadline is November 20, 2026.",
        ],
        "Feature1_Live_Check.txt",
        { type: "text/plain" },
      ),
    );
    const el = document.querySelector('input[type="file"]');
    el.files = transfer.files;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await until(() =>
    JSON.parse(localStorage.getItem("workspaceai-v2"))[0].sources.some(
      (s) => s.name === "Feature1_Live_Check.txt" && s.origin === "server",
    ),
  );
  await check(
    "Actual upload returns a hash, version and indexed passages",
    () => {
      const s = JSON.parse(
        localStorage.getItem("workspaceai-v2"),
      )[0].sources.find((s) => s.name === "Feature1_Live_Check.txt");
      return (
        /^[a-f0-9]{64}$/.test(s.fileHash) &&
        s.versionId === "v1" &&
        s.totalChunks > 0
      );
    },
  );
  await click('[aria-label="Clear selection"]');
  await click('[aria-label="Use Feature1_Live_Check.txt"]');
  await input(
    '[aria-label="Message your workspace"]',
    "What is the verification code in Feature1_Live_Check.txt?",
  );
  await click('[aria-label="Send message"]');
  await until(() =>
    [...document.querySelectorAll(".exchange")]
      .at(-1)
      ?.innerText.includes("WAI-LIVE-6194"),
  );
  await check("Real document Q&A returns verified evidence", () => {
    const last = [...document.querySelectorAll(".exchange")].at(-1);
    return (
      last.innerText.includes("WAI-LIVE-6194") &&
      last.innerText.includes("VERIFIED") &&
      !!last.querySelector(".citation")
    );
  });
  if (apiQuestions !== 1)
    throw new Error("The question did not reach the real backend");
  await check("Selected document snapshot is retained", () => {
    const w = JSON.parse(localStorage.getItem("workspaceai-v2"))[0];
    const m = w.threads
      .find((t) => t.id === "midterm-deadline")
      .messages.at(-1);
    return (
      m.origin === "server" &&
      m.sourceIds.length === 1 &&
      w.evidence[m.evidenceIds[0]].file === "Feature1_Live_Check.txt"
    );
  });
  await page.eval(() =>
    [...document.querySelectorAll(".exchange")]
      .at(-1)
      .querySelector(".citation")
      .click(),
  );
  await sleep(100);
  await check(
    "Citation opens the actual quote and provenance",
    () =>
      document.querySelector(".modal").innerText.includes("WAI-LIVE-6194") &&
      document.querySelector(".modal").innerText.includes("v1"),
  );
  await click('.modal [aria-label="Close dialog"]');
  await click('[aria-label="Clear selection"]');
  await input(
    '[aria-label="Message your workspace"]',
    "What is the verification code?",
  );
  await click('[aria-label="Send message"]');
  await until(
    () =>
      !![...document.querySelectorAll(".exchange")]
        .at(-1)
        ?.querySelector(".abstention"),
  );
  await check(
    "No selected files produces an abstention, not a sample answer",
    () =>
      !![...document.querySelectorAll(".exchange")]
        .at(-1)
        .querySelector(".abstention"),
  );
  await input(
    '[aria-label="Message your workspace"]',
    "Keep this unsent question",
  );
  await click('[aria-label="AI settings"]');
  if (!cloudForm) {
    await check(
      "Offline setup offers masked credentials scoped to Feature 1",
      () =>
        document
          .querySelector(".modal")
          .innerText.includes("Gemini applies only to document Q&A") &&
        document.querySelector('[aria-label="Gemini API key"]').type ===
          "password" &&
        document.querySelector('[aria-label="Gemini model for Feature 1"]')
          .value === "gemini-3.5-flash-lite",
    );
    await click('.modal [aria-label="Close dialog"]');
    await check(
      "Closing offline settings preserves the unsent question",
      () =>
        document.querySelector('[aria-label="Message your workspace"]')
          .value === "Keep this unsent question",
    );
    const rejected = await fetch(backendBase + "/api/runtime/gemini", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ api_key: fakeKey }),
    });
    if (rejected.status !== 409)
      throw new Error("Offline backend did not reject cloud configuration");
    const status = await fetch(backendBase + "/api/runtime").then((r) =>
      r.json(),
    );
    if (status.engine_mode !== "offline" || !status.offline_only)
      throw new Error("Offline configuration changed unexpectedly");
    await click('[aria-label="AI settings"]');
  } else {
    await check(
      "Gemini credential field is masked",
      () =>
        document.querySelector('[aria-label="Gemini API key"]').type ===
          "password" &&
        document.querySelector('[aria-label="Gemini API key"]').autocomplete ===
          "off",
    );
    await input('[aria-label="Gemini API key"]', fakeKey);
    await page.eval(() =>
      document.querySelector(".ai-settings-form").requestSubmit(),
    );
    await until(() => !document.querySelector(".ai-settings-form"));
    await check(
      "The credential is never stored in browser storage",
      (secret) =>
        !JSON.stringify(localStorage).includes(secret) &&
        !JSON.stringify(sessionStorage).includes(secret),
      fakeKey,
    );
    await check(
      "Saving AI settings preserves the unsent question",
      () =>
        document.querySelector('[aria-label="Message your workspace"]')
          .value === "Keep this unsent question",
    );
    if (apiQuestions !== 2)
      throw new Error("AI settings triggered an unintended chat submission");
    await click('[aria-label="AI settings"]');
    await check(
      "The key field clears after connecting",
      () =>
        document.querySelector('[aria-label="Gemini API key"]').value === "",
    );
  }
  for (const theme of ["light", "dark"]) {
    await page.eval(
      (theme) => (document.documentElement.dataset.theme = theme),
      theme,
    );
    for (const width of [1440, 768, 390, 320]) {
      await page.setViewport({ width, height: 1000 });
      await check(
        `Engine settings ${theme} ${width}px does not overflow`,
        () =>
          document.documentElement.scrollWidth <= innerWidth + 1 &&
          document.querySelector(".modal").getBoundingClientRect().right <=
            innerWidth,
      );
      if (width === 1440 || width === 390)
        await page.screenshot({
          path: resolve(out, `engine-${theme}-${width}.png`),
          format: "png",
        });
    }
  }
  await check(
    "No browser runtime errors",
    (errors) => errors.length === 0,
    page.consoleErrors,
  );
  console.log(
    `${results.length} live Feature 1 checks passed with an isolated real FastAPI backend. No external AI requests were made.`,
  );
} catch (error) {
  if (page)
    await page.screenshot({ path: resolve(out, "failure.png"), format: "png" });
  console.error(error);
  process.exitCode = 1;
} finally {
  fs.writeFileSync(
    resolve(out, "results.json"),
    JSON.stringify(results, null, 2),
  );
  if (browser) await browser.close();
  if (server) server.close();
  if (backend.pid) {
    if (process.platform === "win32")
      spawnSync("taskkill", ["/PID", String(backend.pid), "/T", "/F"], {
        windowsHide: true,
        stdio: "ignore",
      });
    else backend.kill();
  }
}
