import { useState } from "react";
import {
  Plus,
  Pencil,
  Trash2,
  ArrowRight,
  FileText,
  Download,
} from "lucide-react";
import type { Workspace } from "./data";
import type { RequirementRow } from "./schema";
import { Badge, Modal, Notice } from "./components";
import { taskRow } from "./workflow-model";

export default function Requirements({
  workspace,
  update,
  notify,
}: {
  workspace: Workspace;
  update: (fn: (w: Workspace) => Workspace) => void;
  notify: (message: string) => void;
}) {
  const [editing, setEditing] = useState<RequirementRow | null>(null);
  const [deleting, setDeleting] = useState<RequirementRow | null>(null);
  const [search, setSearch] = useState("");
  const rows = workspace.requirements ?? [];
  const filtered = rows.filter((r) =>
    `${r.req_id} ${r.title} ${r.keywords.join(" ")}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  const add = () => {
    const at = new Date().toISOString();
    setEditing({
      req_id: `req_${crypto.randomUUID()}`,
      doc_id: null,
      title: "",
      description: "",
      keywords: [],
      official_deadline: null,
      mandatory_flag: true,
      source_ref: "",
      created_at: at,
      updated_at: at,
    });
  };
  return (
    <div className="requirements-screen">
      <div className="review-intro">
        <div>
          <h2>Requirements</h2>
          <p>Connect the official requirements to the work your team tracks.</p>
        </div>
        <button className="button primary" onClick={add}>
          <Plus size={14} />
          Add requirement
        </button>
      </div>
      <Notice tone="neutral">
        Requirements and task edits are saved on this device. Server
        reconciliation uses the server’s own records.
      </Notice>
      <div className="schema-toolbar">
        <input
          type="search"
          aria-label="Search requirements"
          placeholder="Find a requirement…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <button
          className="button"
          onClick={() => {
            const body = JSON.stringify(
              { requirements: rows, tasks: workspace.tasks.map(taskRow) },
              null,
              2,
            );
            const url = URL.createObjectURL(
              new Blob([body], { type: "application/json" }),
            );
            const link = document.createElement("a");
            link.href = url;
            link.download = "requirements-tasks.json";
            link.click();
            URL.revokeObjectURL(url);
          }}
        >
          <Download size={14} />
          Export records
        </button>
      </div>
      <div className="requirement-list">
        {filtered.map((r) => {
          const linked = workspace.tasks.filter(
            (t) => t.mappedReqId === r.req_id,
          );
          const source = workspace.sources.find((s) => s.id === r.doc_id);
          return (
            <article className="requirement-row" key={r.req_id}>
              <div className="requirement-main">
                <div className="schema-meta">
                  <span className="muted">{r.req_id}</span>
                  <Badge tone={r.mandatory_flag ? "warning" : "neutral"}>
                    {r.mandatory_flag ? "Mandatory" : "Optional"}
                  </Badge>
                  <span>{r.official_deadline || "No official deadline"}</span>
                </div>
                <h3>{r.title}</h3>
                {r.description && <p>{r.description}</p>}
                <div className="schema-meta">
                  <FileText size={13} />
                  <span>
                    {source?.name ||
                      (r.doc_id
                        ? "Source no longer in library"
                        : "No linked document")}
                  </span>
                  <span>{r.source_ref || "Source reference unspecified"}</span>
                </div>
                {r.keywords.length > 0 && (
                  <p className="small muted">
                    Keywords: {r.keywords.join(", ")}
                  </p>
                )}
                <details className="requirement-linked">
                  <summary>
                    {linked.length} linked task{linked.length === 1 ? "" : "s"}
                  </summary>
                  {linked.map((t) => (
                    <p key={t.id}>
                      {t.title} · {t.completionPct ?? 0}%
                      {t.archived ? " · Archived locally" : ""}
                    </p>
                  ))}
                  {!linked.length && <p>No task is explicitly linked yet.</p>}
                </details>
              </div>
              <div className="requirement-actions">
                <button
                  className="icon-button"
                  aria-label={`Edit requirement ${r.title}`}
                  onClick={() =>
                    setEditing({ ...r, keywords: [...r.keywords] })
                  }
                >
                  <Pencil size={14} />
                </button>
                <button
                  className="icon-button"
                  aria-label={`Delete requirement ${r.title}`}
                  onClick={() => setDeleting(r)}
                >
                  <Trash2 size={14} />
                </button>
                <button
                  className="button"
                  onClick={() => {
                    const now = new Date().toISOString();
                    update((w) => ({
                      ...w,
                      tasks: [
                        ...w.tasks,
                        {
                          id: crypto.randomUUID(),
                          title: r.title,
                          description: r.description ?? "",
                          owner: "",
                          initials: "?",
                          status: "TODO",
                          due: r.official_deadline ?? "",
                          mappedReqId: r.req_id,
                          completionPct: 0,
                          sourceRef: r.source_ref,
                          createdAt: now,
                          updatedAt: now,
                        },
                      ],
                    }));
                    notify(
                      "Task created and linked to the requirement. Owner remains unspecified.",
                    );
                  }}
                >
                  Create task
                  <ArrowRight size={13} />
                </button>
              </div>
            </article>
          );
        })}
        {!filtered.length && (
          <div className="empty-slot">
            {rows.length
              ? "No requirements match this search."
              : "Add an official requirement to start mapping your tasks."}
          </div>
        )}
      </div>
      {editing && (
        <Modal
          title={
            rows.some((r) => r.req_id === editing.req_id)
              ? "Edit requirement"
              : "Add requirement"
          }
          onClose={() => setEditing(null)}
        >
          <form
            className="edit-task-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!editing.title.trim()) return;
              const row = {
                ...editing,
                title: editing.title.trim(),
                keywords: editing.keywords.map((k) => k.trim()).filter(Boolean),
                updated_at: new Date().toISOString(),
              };
              update((w) => ({
                ...w,
                requirements: rows.some((r) => r.req_id === row.req_id)
                  ? (w.requirements ?? []).map((r) =>
                      r.req_id === row.req_id ? row : r,
                    )
                  : [...(w.requirements ?? []), row],
              }));
              setEditing(null);
              notify("Requirement saved on this device.");
            }}
          >
            <label>
              Title
              <input
                autoFocus
                required
                value={editing.title}
                onChange={(e) =>
                  setEditing({ ...editing, title: e.target.value })
                }
              />
            </label>
            <label>
              Description
              <textarea
                value={editing.description ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, description: e.target.value })
                }
              />
            </label>
            <label>
              Official deadline
              <input
                type="date"
                value={editing.official_deadline ?? ""}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    official_deadline: e.target.value || null,
                  })
                }
              />
            </label>
            <label className="schema-check">
              <input
                type="checkbox"
                checked={editing.mandatory_flag}
                onChange={(e) =>
                  setEditing({ ...editing, mandatory_flag: e.target.checked })
                }
              />
              Mandatory requirement
            </label>
            <label>
              Source document
              <select
                value={editing.doc_id ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, doc_id: e.target.value || null })
                }
              >
                <option value="">Unspecified</option>
                {workspace.sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Source reference
              <input
                placeholder="Document name, page and lines"
                value={editing.source_ref}
                onChange={(e) =>
                  setEditing({ ...editing, source_ref: e.target.value })
                }
              />
            </label>
            <label>
              Keywords (comma separated)
              <input
                value={editing.keywords.join(",")}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    keywords: e.target.value.split(","),
                  })
                }
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button"
                onClick={() => setEditing(null)}
              >
                Cancel
              </button>
              <button className="button primary">Save requirement</button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal title="Delete requirement?" onClose={() => setDeleting(null)}>
          <p>{deleting.title}</p>
          <p>
            {
              workspace.tasks.filter((t) => t.mappedReqId === deleting.req_id)
                .length
            }{" "}
            linked tasks will be kept and unlinked. Previous report snapshots
            are kept.
          </p>
          <div className="modal-actions">
            <button className="button" onClick={() => setDeleting(null)}>
              Cancel
            </button>
            <button
              className="button primary"
              onClick={() => {
                update((w) => ({
                  ...w,
                  requirements: (w.requirements ?? []).filter(
                    (r) => r.req_id !== deleting.req_id,
                  ),
                  tasks: w.tasks.map((t) =>
                    t.mappedReqId === deleting.req_id
                      ? {
                          ...t,
                          mappedReqId: undefined,
                          updatedAt: new Date().toISOString(),
                        }
                      : t,
                  ),
                }));
                setDeleting(null);
              }}
            >
              Delete requirement
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
