// Native chooser regression: real browser pointer/key activation, then fixture-only files.
// Protocol contracts: https://chromedevtools.github.io/devtools-protocol/tot/Page/#event-fileChooserOpened
// and https://chromedevtools.github.io/devtools-protocol/tot/DOM/#method-setFileInputFiles
import fs from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import assert from "node:assert/strict";
import { startFixture } from "./support/picker-server.mjs";
const { Browser, sleep } = await import(
  pathToFileURL(
    process.env.TASTE_CDP_PATH ||
      resolve("../../.agents/skills/design-taste-frontend/scripts/lib/cdp.mjs"),
  ).href
);
const out = resolve(".taste-skill/file-picker-v9"),
  checks = [],
  events = [];
fs.mkdirSync(out, { recursive: true });
const files = ["Picker A.txt", "Picker B.txt", "Retry.txt"].map(
  (name, index) => {
    const path = resolve(out, name);
    fs.writeFileSync(
      path,
      `Fixture ${index + 1}: course document upload test.\n`,
    );
    return path;
  },
);
const fixture = await startFixture(),
  browser = await Browser.launch(),
  page = await browser.newPage({ width: 1440, height: 960 });
await page.send("Page.setInterceptFileChooserDialog", { enabled: true });
async function pointer(selector) {
  const p = await page.eval((s) => {
    const e = [...document.querySelectorAll(s)].find(
      (e) => e.getClientRects().length,
    );
    if (!e) throw Error("Missing " + s);
    const r = e.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }, selector);
  await page.send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    ...p,
    button: "left",
    clickCount: 1,
  });
  await page.send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    ...p,
    button: "left",
    clickCount: 1,
  });
  await sleep(70);
}
async function textPointer(text) {
  const p = await page.eval((t) => {
    const e = [...document.querySelectorAll("button")].find(
      (e) => e.getClientRects().length && e.textContent.trim() === t,
    );
    if (!e) throw Error(t);
    const r = e.getBoundingClientRect();
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }, text);
  await page.send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    ...p,
    button: "left",
    clickCount: 1,
  });
  await page.send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    ...p,
    button: "left",
    clickCount: 1,
  });
  await sleep(70);
}
async function check(name, fn) {
  assert.equal(await page.eval(fn), true, name);
  checks.push(name);
  console.log("PASS " + name);
}
async function chooser(action) {
  let off, timer;
  const event = new Promise((resolve, reject) => {
    off = browser.on(page.sessionId, "Page.fileChooserOpened", (p) => {
      clearTimeout(timer);
      off();
      resolve(p);
    });
    timer = setTimeout(() => {
      off();
      reject(Error("Native file chooser did not open"));
    }, 3000);
  });
  const [, result] = await Promise.all([action(), event]);
  events.push({ mode: result.mode, backendNodeId: result.backendNodeId });
  return result;
}
async function select(event, paths) {
  await page.send("DOM.setFileInputFiles", {
    backendNodeId: event.backendNodeId,
    files: paths,
  });
  await sleep(260);
}
try {
  await page.goto(fixture.url, { settleMs: 220 });
  await pointer(".nb-add-source");

  await check(
    "file input is rendered inside the active modal, not hidden outside it",
    () => {
      const e = document.querySelector('input[type="file"]');
      return (
        !!e.closest('[role="dialog"]') &&
        !e.hidden &&
        e.getBoundingClientRect().height >= 44
      );
    },
  );
  let opened = await chooser(() => pointer('input[type="file"]'));
  assert.equal(opened.mode, "selectMultiple");
  checks.push("trusted pointer opens the real multiple-file chooser");
  await select(opened, []);
  await check(
    "cancel keeps the dialog usable without a false upload",
    () =>
      !!document.querySelector('[role="dialog"]') &&
      document.querySelectorAll(".nb-upload-job").length === 0,
  );
  assert.equal(
    fixture.calls.filter((c) => c.path.endsWith("/upload")).length,
    0,
  );
  opened = await chooser(async () => {
    await page.eval(() => document.querySelector('input[type="file"]').focus());
    await page.send("Input.dispatchKeyEvent", {
      type: "keyDown",
      key: " ",
      code: "Space",
      windowsVirtualKeyCode: 32,
      nativeVirtualKeyCode: 32,
    });
    await page.send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key: " ",
      code: "Space",
      windowsVirtualKeyCode: 32,
      nativeVirtualKeyCode: 32,
    });
  });
  assert.equal(opened.mode, "selectMultiple");
  checks.push("trusted keyboard Space opens the native chooser");
  await select(opened, files.slice(0, 2));
  await check(
    "choosing two real fixture files uploads both and enables their checkboxes",
    () =>
      document.querySelectorAll(".nb-source-row").length === 2 &&
      [...document.querySelectorAll(".nb-source-check input")].every(
        (e) => e.checked && !e.disabled,
      ),
  );
  await pointer(".nb-source-check input");
  await check(
    "uploaded file selection still toggles and saves",
    () =>
      JSON.parse(localStorage.getItem("workspaceai-v2"))[0].sources.filter(
        (s) => s.selected,
      ).length === 1,
  );
  await pointer(".nb-add-source");
  opened = await chooser(() => pointer('input[type="file"]'));
  await select(opened, [files[0]]);
  await check(
    "choosing the same file again fires upload without duplicating its source",
    () => document.querySelectorAll(".nb-source-row").length === 2,
  );
  assert.equal(
    fixture.calls.filter((c) => c.path.endsWith("/upload")).length,
    3,
  );
  await pointer('[aria-label="Tùy chọn Picker A.txt"]');
  await textPointer("Tải lại file gốc");
  await check(
    "re-upload opens the same accessible picker with a single-file limit",
    () =>
      document
        .querySelector('[role="dialog"]')
        .textContent.includes("Picker A.txt") &&
      !document.querySelector('input[type="file"]').multiple,
  );
  opened = await chooser(() => pointer('input[type="file"]'));
  assert.equal(opened.mode, "selectSingle");
  checks.push("re-upload requests a real single-file chooser");
  await select(opened, [files[0]]);
  await check(
    "re-upload preserves the source count and original stable ID",
    () =>
      JSON.parse(localStorage.getItem("workspaceai-v2"))[0].sources.length ===
        2 &&
      JSON.parse(localStorage.getItem("workspaceai-v2"))[0].sources.some(
        (s) => s.id === "fixture-1",
      ),
  );
  await pointer(".nb-add-source");
  opened = await chooser(() => pointer('input[type="file"]'));
  await select(opened, [files[2]]);
  await check(
    "a failed upload shows the actual error and an available retry",
    () =>
      !!document.querySelector(".nb-upload-job button") &&
      document
        .querySelector(".nb-upload-job")
        .textContent.includes("Temporary upload failure"),
  );
  await pointer('[aria-label="Thử tải lại Retry.txt"]');
  await sleep(100);
  await check(
    "retry reuses the chosen File without reopening or blocking the picker",
    () =>
      document.querySelectorAll(".nb-source-row").length === 3 &&
      !document.querySelector(".nb-upload-job"),
  );
  await page.screenshot({
    path: resolve(out, "uploaded-files-desktop.png"),
    format: "png",
  });
  for (const [width, height] of [
    [390, 844],
    [320, 780],
  ]) {
    await page.setViewport({ width, height, mobile: true });
    await pointer(".nb-bottom-tabs button:first-child");
    await pointer(".nb-add-source");
    await check(
      `phone ${width} native target is visible and at least 44px high`,
      () => {
        const r = document
          .querySelector('input[type="file"]')
          .getBoundingClientRect();
        return r.height >= 44 && r.left >= 0 && r.right <= innerWidth;
      },
    );
    opened = await chooser(() => pointer('input[type="file"]'));
    await select(opened, []);
    await pointer('[aria-label="Close dialog"]');
  }
  await page.setViewport({ width: 1440, height: 960 });
  await page.eval(() => localStorage.setItem("wai-theme", "dark"));
  await page.goto(fixture.url + "?theme=dark", { settleMs: 200 });
  await pointer(".nb-add-source");
  opened = await chooser(() => pointer('input[type="file"]'));
  await select(opened, []);
  await check(
    "dark theme also opens and cancels the native picker",
    () => !!document.querySelector('[role="dialog"]'),
  );
  await pointer('[aria-label="Close dialog"]');
  assert.deepEqual(page.consoleErrors, []);
  assert.ok(
    fixture.calls
      .filter((c) => c.path.startsWith("/api/documents"))
      .every((c) => c.scope === "picker-test"),
  );
  assert.ok(
    !fixture.calls.some(
      (c) =>
        c.path.includes("/chat") ||
        c.path.includes("/email") ||
        c.path.includes("/runtime/gemini"),
    ),
  );
  checks.push(
    "no browser exceptions, unscoped requests, model calls or email dispatch",
  );
  console.log("PASS " + checks.length + " native file picker checks");
} finally {
  fs.writeFileSync(
    resolve(out, "picker-checks.json"),
    JSON.stringify(
      { checks, events, calls: fixture.calls, errors: page.consoleErrors },
      null,
      2,
    ),
  );
  await browser.close();
  await fixture.close();
}
