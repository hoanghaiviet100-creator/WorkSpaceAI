import fs from "node:fs";
import { createServer } from "node:http";
import { resolve, extname, sep } from "node:path";
import { createHash } from "node:crypto";
import ts from "typescript";
const code = ts.transpileModule(
  fs.readFileSync(resolve("src/data.ts"), "utf8"),
  {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
    },
  },
).outputText;
const { seedWorkspaces } = await import(
  "data:text/javascript;base64," + Buffer.from(code).toString("base64")
);
const root = resolve("dist"),
  out = resolve(".taste-skill/file-picker-v9");
export async function startFixture(options = {}) {
  const out = resolve(options.outDir || ".taste-skill/file-picker-v9");
  fs.mkdirSync(out, { recursive: true });
  const docs = structuredClone(options.documents || []),
    calls = [];
  let failRetry = true;
  const seed = seedWorkspaces()[0];
  const fixture = options.workspace || {
    ...seed,
    id: "picker-test",
    name: "Kiểm tra chọn file",
    schemaVersion: 3,
    notebookVersion: 1,
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
        updated: "2026-11-09T10:00:00Z",
        messages: [],
      },
    ],
  };
  const prep = `<script>if(!localStorage.getItem('workspaceai-v2'))localStorage.setItem('workspaceai-v2',${JSON.stringify(JSON.stringify([fixture]))});if(!localStorage.getItem('wai-theme'))localStorage.setItem('wai-theme','light');if(!location.hash)location.hash='workspace/picker-test/chat/single';</script>`;
  const server = createServer(async (req, res) => {
    if (req.url.startsWith("/api/")) {
      let raw = Buffer.alloc(0);
      for await (const chunk of req) raw = Buffer.concat([raw, chunk]);
      const record = {
        method: req.method,
        path: req.url,
        scope: req.headers["x-workspace-id"],
      };
      calls.push(record);
      res.setHeader("content-type", "application/json");
      const send = (data, status = 200) => {
        res.statusCode = status;
        res.end(JSON.stringify(data));
      };
      if (req.url === "/api/runtime")
        return send({
          status: "ready",
          engine_mode: "offline",
          offline_only: true,
          gemini_configured: false,
        });
      if (req.url === "/api/documents" && req.method === "GET")
        return send(docs);
      if (
        req.url.match(/^\/api\/documents\/[^/]+\/pages\/\d+$/) &&
        req.method === "GET"
      ) {
        const document = docs.find((doc) =>
          req.url.includes(encodeURIComponent(doc.doc_id)),
        );
        if (!document || options.pageError)
          return send({ detail: "Source text unavailable" }, 503);
        if (options.pageDelay)
          await new Promise((resolve) =>
            setTimeout(resolve, options.pageDelay),
          );
        return send({
          page_id: 1,
          doc_id: document.doc_id,
          page_number: 1,
          line_count: 3,
          raw_text:
            options.pageText ||
            "Cần hoàn thành báo cáo trước 2026-12-20.\nChuẩn bị bài thuyết trình.\nRà soát trích dẫn tài liệu.",
          doc_hash: document.file_hash,
          doc_version: "v1",
          page_hash: "fixture",
          created_at: "2026-11-09",
        });
      }
      if (req.url === "/api/documents/select") {
        const body = JSON.parse(raw.toString());
        for (const doc of docs)
          doc.is_selected = body.selected_doc_ids.includes(doc.doc_id);
        record.selected = body.selected_doc_ids;
        return send({ status: "SELECTION_UPDATED" });
      }
      if (req.url === "/api/documents/upload") {
        const body = raw.toString("utf8"),
          name = /filename="([^"]+)"/.exec(body)?.[1];
        record.filename = name;
        if (!name) return send({ detail: "No file received" }, 400);
        if (name === "Retry.txt" && failRetry) {
          failRetry = false;
          return send({ detail: "Temporary upload failure" }, 503);
        }
        const text = body
          .split("\r\n\r\n")
          .slice(1)
          .join("\r\n\r\n")
          .replace(/\r\n--[^]*$/, "");
        const hash = createHash("sha256").update(text).digest("hex");
        let document = docs.find((doc) => doc.file_hash === hash);
        if (!document) {
          document = {
            doc_id: "fixture-" + (docs.length + 1),
            doc_name: name,
            file_type: "txt",
            file_hash: hash,
            version_id: "v1",
            page_count: 1,
            chunk_count: 1,
            total_lines: 1,
            is_selected: true,
          };
          docs.push(document);
        }
        return send({ status: "INGESTED", document });
      }
      return send({ detail: "Unexpected fixture API" }, 404);
    }
    try {
      let file = resolve(
        root,
        "." + new URL(req.url, "http://fixture").pathname,
      );
      if (!file.startsWith(root + sep) && file !== root)
        throw Error("Outside build");
      if (fs.statSync(file).isDirectory()) file = resolve(file, "index.html");
      res.setHeader(
        "content-type",
        {
          ".html": "text/html",
          ".js": "text/javascript",
          ".css": "text/css",
          ".woff": "font/woff",
          ".woff2": "font/woff2",
        }[extname(file)] || "application/octet-stream",
      );
      let body = fs.readFileSync(file);
      if (extname(file) === ".html")
        body = body.toString().replace("<head>", "<head>" + prep);
      res.end(body);
    } catch {
      res.writeHead(404);
      res.end();
    }
  });
  await new Promise((r) => server.listen(0, "127.0.0.1", r));
  const url = `http://127.0.0.1:${server.address().port}/`;
  return {
    server,
    url,
    docs,
    calls,
    close: async () => {
      fs.writeFileSync(
        resolve(out, "fixture-api-calls.json"),
        JSON.stringify(calls, null, 2),
      );
      await new Promise((r) => server.close(r));
    },
  };
}
if (process.argv.includes("--serve")) {
  const fixture = await startFixture();
  fs.writeFileSync(
    resolve(out, "fixture-server.json"),
    JSON.stringify({ url: fixture.url, pid: process.pid }),
  );
  console.log(fixture.url);
  process.on("SIGINT", () => void fixture.close().then(() => process.exit(0)));
}
