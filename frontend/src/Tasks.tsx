import { useState, type Dispatch, type SetStateAction } from "react";
import {
  Plus,
  Check,
  ArrowRight,
  AlertTriangle,
  Trash2,
  Columns3,
  ListFilter,
  CalendarDays,
  UserRound,
  Pencil,
  X,
  Circle,
  CircleCheck,
  Clock3,
  ChevronDown,
} from "lucide-react";
import {
  type Task,
  type EvidenceKey,
  type Suggestion,
  type Workspace,
} from "./data";
import Requirements from "./Requirements";
import Reconciliation from "./Reconciliation";
import { clampProgress } from "./schema";
import { Badge, Citation, Notice, Modal } from "./components";
import {
  TASK_STATUSES,
  LOCAL_TASK_LABELS,
  TaskStatusPill,
  taskLane,
  type BoardLane,
  type TaskStatus,
} from "./task-status";
export default function Tasks({
  tasks,
  setTasks,
  suggestions,
  setSuggestions,
  members,
  onRequest,
  onEvidence,
  notify,
  initialTab = "board",
  workspace,
  updateWorkspace,
}: {
  workspace: Workspace;
  updateWorkspace: (fn: (w: Workspace) => Workspace) => void;
  tasks: Task[];
  setTasks: Dispatch<SetStateAction<Task[]>>;
  suggestions: Suggestion[];
  setSuggestions: Dispatch<SetStateAction<Suggestion[]>>;
  members: string[];
  onRequest: (s: string) => void;
  onEvidence: (id: EvidenceKey) => void;
  notify: (s: string) => void;
  initialTab?: string;
}) {
  const team = members;
  const [tab, setTab] = useState(initialTab);
  const [editing, setEditing] = useState<Task | null>(null);
  const [filter, setFilter] = useState("All members");
  const [mobileStatus, setMobileStatus] = useState<BoardLane>("To do");
  const [statusFilter, setStatusFilter] = useState<TaskStatus | "All statuses">(
    "All statuses",
  );
  const [request, setRequest] = useState("");
  const generating = false;
  const confirm = (ids: string[]) => {
    const chosen = suggestions.filter(
      (s) => ids.includes(s.id) && s.title.trim(),
    );
    if (!chosen.length) return;
    setTasks((ts) => [
      ...ts,
      ...chosen.map((s) => ({
        id: crypto.randomUUID(),
        title: s.title,
        description: s.description,
        owner: s.owner,
        initials: s.owner
          ? s.owner
              .split(" ")
              .slice(-2)
              .map((x) => x[0])
              .join("")
          : "?",
        due: s.due,
        status: s.status ?? ("TODO" as const),
        source: s.source,
        sourceRef:
          s.source && workspace.evidence[s.source]
            ? `${workspace.evidence[s.source].file} ${workspace.evidence[s.source].locator}`
            : "",
        mappedReqId: s.mappedReqId,
        completionPct:
          s.status === "DONE" ? 100 : clampProgress(s.completionPct),
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      })),
    ]);
    setSuggestions((ss) => ss.filter((s) => !ids.includes(s.id)));
    notify(
      `${chosen.length} reviewed task${chosen.length === 1 ? "" : "s"} created.`,
    );
  };
  const update = (
    id: string,
    field: keyof Suggestion,
    value: string | boolean,
  ) =>
    setSuggestions((ss) =>
      ss.map((s) =>
        s.id === id ? ({ ...s, [field]: value } as Suggestion) : s,
      ),
    );
  const visible = tasks.filter(
    (t) =>
      (filter === "All members" || t.owner === filter) &&
      (statusFilter === "All statuses" || t.status === statusFilter),
  );
  const activeTasks = tasks.filter((t) => !t.archived);
  const lanes: BoardLane[] =
    statusFilter !== "All statuses"
      ? [taskLane(statusFilter)]
      : [
          "To do",
          "In progress",
          "In Review",
          "Done",
          ...(visible.some((t) => t.archived) ? ["Archived" as const] : []),
        ];
  const mobileLane = lanes.includes(mobileStatus) ? mobileStatus : lanes[0];
  return (
    <div className="tasks-screen">
      <div className="tabs-row">
        <div className="tabs">
          <button
            className={tab === "board" ? "selected" : ""}
            onClick={() => setTab("board")}
          >
            <Columns3 size={15} />
            Task board <span>{tasks.length}</span>
          </button>
          <button
            className={tab === "review" ? "selected" : ""}
            onClick={() => setTab("review")}
          >
            Suggestion review <span>{suggestions.length}</span>
          </button>
          <button
            className={tab === "requirements" ? "selected" : ""}
            onClick={() => setTab("requirements")}
          >
            Requirements <span>{workspace.requirements?.length ?? 0}</span>
          </button>
          <button
            className={tab === "reconciliation" ? "selected" : ""}
            onClick={() => setTab("reconciliation")}
          >
            Reconciliation
          </button>
        </div>
        <button
          className="button primary"
          onClick={() => {
            setTab("review");
            document.getElementById("task-request")?.focus();
          }}
        >
          <Plus size={14} />
          Suggest tasks
        </button>
      </div>
      {tab === "requirements" ? (
        <Requirements
          workspace={workspace}
          update={updateWorkspace}
          notify={notify}
        />
      ) : tab === "reconciliation" ? (
        <Reconciliation workspace={workspace} update={updateWorkspace} />
      ) : tab === "board" ? (
        <>
          <div className="board-summary">
            <div>
              <span className="small muted">
                Project progress <span className="badge">Computed</span>
              </span>
              <strong>
                {activeTasks.filter((t) => t.status === "DONE").length}{" "}
                <span>of {activeTasks.length} active tasks complete</span>
              </strong>
            </div>
            <div className="progress-track">
              <span
                style={{
                  width: `${activeTasks.length ? (activeTasks.filter((t) => t.status === "DONE").length / activeTasks.length) * 100 : 0}%`,
                }}
              />
            </div>
            <div className="team-compact">
              <span className="avatar tint-0">GK</span>
              <span className="small muted">{members.length} members</span>
            </div>
          </div>
          <div className="board-toolbar">
            <button
              className="button"
              onClick={() => {
                const now = new Date().toISOString();
                setEditing({
                  id: crypto.randomUUID(),
                  title: "",
                  description: "",
                  owner: "",
                  initials: "?",
                  due: "",
                  status: "TODO",
                  completionPct: 0,
                  createdAt: now,
                  updatedAt: now,
                });
              }}
            >
              <Plus size={14} />
              New task
            </button>
            <div className="board-filter-controls">
              <label>
                <ListFilter size={14} />
                <select
                  aria-label="Filter tasks by member"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                >
                  <option>All members</option>
                  {team.map((n) => (
                    <option key={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label>
                <select
                  aria-label="Filter tasks by status"
                  value={statusFilter}
                  onChange={(e) =>
                    setStatusFilter(
                      e.target.value as TaskStatus | "All statuses",
                    )
                  }
                >
                  <option>All statuses</option>
                  {TASK_STATUSES.map((item) => (
                    <option
                      key={item.value}
                      value={item.value}
                      data-task-tag={item.tone}
                    >
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          </div>
          <details className="task-status-guide">
            <summary>
              Task statuses <span>4 workflow states</span>
              <ChevronDown size={14} />
            </summary>
            <div className="task-status-legend">
              {TASK_STATUSES.map((item) => (
                <button
                  key={item.value}
                  title={item.help}
                  aria-label={`Show ${item.label} tasks`}
                  aria-pressed={statusFilter === item.value}
                  onClick={() =>
                    setStatusFilter(
                      statusFilter === item.value ? "All statuses" : item.value,
                    )
                  }
                >
                  <TaskStatusPill status={item.value} />
                </button>
              ))}
            </div>
          </details>
          {(workspace.requirements ?? []).some(
            (r) =>
              r.mandatory_flag &&
              !tasks.some((t) => t.mappedReqId === r.req_id),
          ) && (
            <div className="requirement-gap">
              <div>
                <AlertTriangle size={17} />
                <strong>Missing work</strong>
                <span>
                  Some mandatory requirements have no explicitly linked task.
                </span>
              </div>
              <button onClick={() => setTab("requirements")}>
                Review requirements <ArrowRight size={14} />
              </button>
            </div>
          )}
          <div
            className="mobile-board-nav"
            role="group"
            aria-label="Task status on phone"
          >
            {lanes.map((status) => (
              <button
                key={status}
                className={mobileLane === status ? "selected" : ""}
                data-status={status}
                aria-pressed={mobileLane === status}
                onClick={() => setMobileStatus(status)}
              >
                {status === "In progress" ? "Active" : status}
                <span>
                  {
                    visible.filter(
                      (t) => taskLane(t.status, t.archived) === status,
                    ).length
                  }
                </span>
              </button>
            ))}
          </div>
          <div
            className="kanban"
            data-mobile-status={mobileLane}
            data-lane-count={lanes.length}
          >
            {lanes.map((status) => (
              <section
                className="kanban-column"
                data-status={status}
                key={status}
              >
                <header>
                  <h2>
                    <span
                      className={`column-dot ${status.replace(" ", "-").toLowerCase()}`}
                    />
                    {status === "In progress" ? "Active work" : status}
                  </h2>
                  <span className="small muted">
                    {
                      visible.filter(
                        (t) => taskLane(t.status, t.archived) === status,
                      ).length
                    }
                  </span>
                </header>
                <div className="task-stack">
                  {visible
                    .filter((t) => taskLane(t.status, t.archived) === status)
                    .map((t) => (
                      <article
                        className="task-card"
                        data-status={t.status}
                        data-lane={taskLane(t.status, t.archived)}
                        key={t.id}
                      >
                        <div className="task-card-top">
                          <TaskStatusPill status={t.status} />
                          <span className="task-id">
                            {t.id.startsWith("t")
                              ? `WAI-${t.id.slice(1).padStart(2, "0")}`
                              : "New task"}
                          </span>
                          <button
                            className="icon-button"
                            aria-label={`Edit ${t.title}`}
                            onClick={() => setEditing({ ...t })}
                          >
                            <Pencil size={14} />
                          </button>
                        </div>
                        <h3>{t.title}</h3>
                        <p>{t.description}</p>
                        <div className="task-mapping">
                          <span>
                            {t.mappedReqId
                              ? ((workspace.requirements ?? []).find(
                                  (r) => r.req_id === t.mappedReqId,
                                )?.title ??
                                `Unavailable requirement: ${t.mappedReqId}`)
                              : "No linked requirement"}
                          </span>
                          <strong>{t.completionPct ?? 0}%</strong>
                        </div>
                        {t.localLabel && (
                          <span
                            className="task-status-pill"
                            data-task-tag={t.localLabel
                              .toLowerCase()
                              .replaceAll(" ", "-")}
                          >
                            {t.localLabel}
                          </span>
                        )}
                        {t.archived && (
                          <span
                            className="task-status-pill"
                            data-task-tag="archived"
                          >
                            Archived locally
                          </span>
                        )}
                        {t.flag && (
                          <Badge
                            tone={t.flag === "Overdue" ? "danger" : "warning"}
                          >
                            <AlertTriangle size={12} />
                            {t.flag}
                          </Badge>
                        )}
                        {t.source ? (
                          <>
                            <Citation id={t.source} onOpen={onEvidence} />
                            {t.secondarySource && (
                              <Citation
                                id={t.secondarySource}
                                onOpen={onEvidence}
                              />
                            )}
                          </>
                        ) : (
                          <Badge>You provided</Badge>
                        )}
                        <div className="task-meta">
                          <span
                            className={`avatar small-avatar tint-${Math.max(0, team.indexOf(t.owner)) % 5}`}
                            title={t.owner || "Unspecified owner"}
                          >
                            {t.initials}
                          </span>
                          <span>
                            {t.owner
                              ? t.owner.split(" ").slice(-2).join(" ")
                              : "Unspecified"}
                          </span>
                          <span
                            className={t.flag === "Overdue" ? "overdue" : ""}
                          >
                            <CalendarDays size={12} />
                            {t.due
                              ? new Date(
                                  t.due + "T12:00:00",
                                ).toLocaleDateString("en-US", {
                                  month: "short",
                                  day: "numeric",
                                })
                              : "Unspecified"}
                          </span>
                        </div>
                        <label className="task-status-label">
                          Move to
                          <select
                            aria-label={`Status of ${t.title}`}
                            value={t.status}
                            onChange={(e) =>
                              setTasks((ts) =>
                                ts.map((x) =>
                                  x.id === t.id
                                    ? {
                                        ...x,
                                        status: e.target
                                          .value as Task["status"],
                                        completionPct:
                                          e.target.value === "DONE"
                                            ? 100
                                            : x.status === "DONE"
                                              ? 0
                                              : x.completionPct,
                                        updatedAt: new Date().toISOString(),
                                        flag:
                                          x.flag === "Overdue" &&
                                          ["DONE"].includes(e.target.value)
                                            ? undefined
                                            : x.flag,
                                      }
                                    : x,
                                ),
                              )
                            }
                          >
                            {TASK_STATUSES.map((s) => (
                              <option
                                key={s.value}
                                value={s.value}
                                data-task-tag={s.tone}
                              >
                                {s.label}
                              </option>
                            ))}
                          </select>
                        </label>
                      </article>
                    ))}
                  {!visible.some(
                    (t) => taskLane(t.status, t.archived) === status,
                  ) && (
                    <div className="empty-slot">
                      No tasks{" "}
                      {status === "Done" ? "completed yet" : "in this column"}.
                    </div>
                  )}
                </div>
              </section>
            ))}
          </div>
        </>
      ) : (
        <div className="suggestion-review">
          <div className="review-intro">
            <div>
              <h2>Review before you commit.</h2>
              <p>Suggestions stay provisional until you confirm them.</p>
            </div>
            <Badge>AI-suggested · Draft</Badge>
          </div>
          <form
            className="task-request"
            onSubmit={(e) => {
              e.preventDefault();
              if (!request.trim()) return;
              onRequest(request);
              setRequest("");
            }}
          >
            <input
              id="task-request"
              value={request}
              onChange={(e) => setRequest(e.target.value)}
              placeholder="Describe the work you want to plan…"
              aria-label="Task suggestion request"
            />
            <button className="button" disabled={generating || !request.trim()}>
              {generating ? "Preparing…" : "Suggest"}
            </button>
          </form>
          <Notice tone="neutral">
            Missing owners and dates remain <strong>Unspecified</strong>.
            Complete them when you have reliable information.
          </Notice>
          <div className="bulk-actions">
            <label>
              <input
                type="checkbox"
                checked={
                  suggestions.length > 0 && suggestions.every((s) => s.selected)
                }
                onChange={(e) =>
                  setSuggestions((ss) =>
                    ss.map((s) => ({ ...s, selected: e.target.checked })),
                  )
                }
              />
              Select all
            </label>
            <button
              className="button primary"
              disabled={
                !suggestions.some((s) => s.selected) ||
                suggestions.some((s) => s.selected && !s.title.trim())
              }
              onClick={() =>
                confirm(suggestions.filter((s) => s.selected).map((s) => s.id))
              }
            >
              <Check size={14} />
              Confirm selected ({suggestions.filter((s) => s.selected).length})
            </button>
          </div>
          {suggestions.map((s) => (
            <article className="suggestion-card" key={s.id}>
              <div className="suggestion-title">
                <input
                  type="checkbox"
                  aria-label={`Select suggestion ${s.title}`}
                  checked={s.selected}
                  onChange={(e) => update(s.id, "selected", e.target.checked)}
                />
                <input
                  aria-label="Suggested task title"
                  value={s.title}
                  onChange={(e) => update(s.id, "title", e.target.value)}
                />
                <Badge>Draft</Badge>
              </div>
              <textarea
                aria-label="Suggested task description"
                value={s.description}
                onChange={(e) => update(s.id, "description", e.target.value)}
              />
              <div className="suggestion-fields">
                <label>
                  <span>
                    <UserRound size={13} />
                    Owner
                  </span>
                  <select
                    aria-label={`Owner for ${s.title}`}
                    value={s.owner}
                    onChange={(e) => update(s.id, "owner", e.target.value)}
                  >
                    <option value="">Unspecified</option>
                    {team.map((n) => (
                      <option key={n}>{n}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>
                    <CalendarDays size={13} />
                    Deadline {s.due ? "" : "· Unspecified"}
                  </span>
                  <input
                    type="date"
                    aria-label={`Deadline for ${s.title}`}
                    value={s.due}
                    onChange={(e) => update(s.id, "due", e.target.value)}
                  />
                </label>
                <label className="suggestion-status-field">
                  <span>
                    Initial status{" "}
                    <TaskStatusPill status={s.status ?? "TODO"} />
                  </span>
                  <select
                    aria-label={`Initial status for ${s.title}`}
                    value={s.status ?? "TODO"}
                    onChange={(e) => update(s.id, "status", e.target.value)}
                  >
                    {TASK_STATUSES.map((item) => (
                      <option
                        key={item.value}
                        value={item.value}
                        data-task-tag={item.tone}
                      >
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="suggestion-footer">
                <label className="suggestion-requirement">
                  Linked requirement
                  <select
                    aria-label={`Requirement for ${s.title}`}
                    value={s.mappedReqId ?? ""}
                    onChange={(e) =>
                      update(s.id, "mappedReqId", e.target.value)
                    }
                  >
                    <option value="">Unspecified</option>
                    {(workspace.requirements ?? []).map((r) => (
                      <option value={r.req_id} key={r.req_id}>
                        {r.title}
                      </option>
                    ))}
                  </select>
                </label>
                {s.source ? (
                  <Citation id={s.source} onOpen={onEvidence} />
                ) : (
                  <Badge>You provided</Badge>
                )}
                <div>
                  <button
                    className="text-button"
                    onClick={() =>
                      setSuggestions((ss) => ss.filter((x) => x.id !== s.id))
                    }
                  >
                    Reject
                  </button>
                  <button
                    className="button"
                    disabled={!s.title.trim()}
                    onClick={() => confirm([s.id])}
                  >
                    <Check size={14} />
                    Confirm
                  </button>
                </div>
              </div>
            </article>
          ))}
          {!suggestions.length && (
            <div className="empty-slot">
              All suggestions reviewed. Your confirmed tasks are on the board.
            </div>
          )}
        </div>
      )}
      {editing && (
        <Modal title="Edit task" onClose={() => setEditing(null)}>
          <form
            className="edit-task-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (!editing.title.trim()) {
                notify("Enter a task title before saving.");
                return;
              }
              setTasks((ts) =>
                ts.some((t) => t.id === editing.id)
                  ? ts.map((t) =>
                      t.id === editing.id
                        ? {
                            ...editing,
                            title: editing.title.trim(),
                            completionPct:
                              editing.status === "DONE"
                                ? 100
                                : clampProgress(editing.completionPct),
                            updatedAt: new Date().toISOString(),
                          }
                        : t,
                    )
                  : [
                      ...ts,
                      {
                        ...editing,
                        title: editing.title.trim(),
                        completionPct:
                          editing.status === "DONE"
                            ? 100
                            : clampProgress(editing.completionPct),
                      },
                    ],
              );
              setEditing(null);
              notify("Task updated.");
            }}
          >
            <label>
              Task title
              <input
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
                value={editing.description}
                onChange={(e) =>
                  setEditing({ ...editing, description: e.target.value })
                }
              />
            </label>
            <label>
              Status
              <TaskStatusPill status={editing.status} />
              <select
                aria-label="Edit task status"
                value={editing.status}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    status: e.target.value as TaskStatus,
                    completionPct:
                      e.target.value === "DONE"
                        ? 100
                        : editing.status === "DONE"
                          ? 0
                          : editing.completionPct,
                    flag:
                      editing.flag === "Overdue" &&
                      ["DONE"].includes(e.target.value)
                        ? undefined
                        : editing.flag,
                  })
                }
              >
                {TASK_STATUSES.map((item) => (
                  <option
                    key={item.value}
                    value={item.value}
                    data-task-tag={item.tone}
                  >
                    {item.label}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Owner
              <select
                value={editing.owner}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    owner: e.target.value,
                    initials:
                      e.target.value
                        .split(" ")
                        .slice(-2)
                        .map((x) => x[0])
                        .join("") || "?",
                  })
                }
              >
                <option value="">Unspecified</option>
                {editing.owner && !team.includes(editing.owner) && (
                  <option value={editing.owner}>{editing.owner}</option>
                )}
                {team.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <label>
              Linked requirement
              <select
                aria-label="Linked requirement"
                value={editing.mappedReqId ?? ""}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    mappedReqId: e.target.value || undefined,
                  })
                }
              >
                <option value="">Unspecified</option>
                {(workspace.requirements ?? []).map((r) => (
                  <option key={r.req_id} value={r.req_id}>
                    {r.title}
                  </option>
                ))}
                {editing.mappedReqId &&
                  !(workspace.requirements ?? []).some(
                    (r) => r.req_id === editing.mappedReqId,
                  ) && (
                    <option value={editing.mappedReqId}>
                      Unavailable requirement ({editing.mappedReqId})
                    </option>
                  )}
              </select>
            </label>
            <label>
              Completion (%)
              <input
                aria-label="Task completion"
                type="number"
                min="0"
                max="100"
                step="0.1"
                required
                value={editing.completionPct ?? 0}
                readOnly={editing.status === "DONE"}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    completionPct: e.target.valueAsNumber,
                  })
                }
              />
            </label>
            <label>
              Additional label
              <select
                aria-label="Additional task label"
                value={editing.localLabel ?? ""}
                onChange={(e) =>
                  setEditing({
                    ...editing,
                    localLabel: e.target.value || undefined,
                  })
                }
              >
                <option value="">None</option>
                {LOCAL_TASK_LABELS.map((label) => (
                  <option key={label}>{label}</option>
                ))}
                {editing.localLabel &&
                  !(LOCAL_TASK_LABELS as readonly string[]).includes(
                    editing.localLabel,
                  ) && <option>{editing.localLabel}</option>}
              </select>
            </label>
            <label className="schema-check">
              <input
                type="checkbox"
                checked={editing.archived ?? false}
                onChange={(e) =>
                  setEditing({ ...editing, archived: e.target.checked })
                }
              />
              Archived on this device
            </label>
            <label>
              Source reference
              <input
                value={editing.sourceRef ?? ""}
                onChange={(e) =>
                  setEditing({ ...editing, sourceRef: e.target.value })
                }
              />
            </label>
            <label>
              Deadline
              <input
                type="date"
                value={editing.due}
                onChange={(e) =>
                  setEditing({ ...editing, due: e.target.value })
                }
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button danger-text"
                onClick={() => {
                  setTasks((ts) => ts.filter((t) => t.id !== editing.id));
                  setEditing(null);
                }}
              >
                <Trash2 size={14} />
                Delete task
              </button>
              <button className="button primary">Save changes</button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
