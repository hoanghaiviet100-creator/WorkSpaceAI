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
import { type Task, type EvidenceKey, type Suggestion } from "./data";
import { Badge, Citation, Notice, Modal } from "./components";
import {
  TASK_STATUSES,
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
}: {
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
        status: s.status ?? ("To do" as const),
        source: s.source,
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
  const activeTasks = tasks.filter((t) => t.status !== "Archived");
  const lanes: BoardLane[] =
    statusFilter !== "All statuses"
      ? [taskLane(statusFilter)]
      : [
          "To do",
          "In progress",
          "Done",
          ...(visible.some((t) => t.status === "Archived")
            ? ["Archived" as const]
            : []),
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
      {tab === "board" ? (
        <>
          <div className="board-summary">
            <div>
              <span className="small muted">
                Project progress <span className="badge">Computed</span>
              </span>
              <strong>
                {activeTasks.filter((t) => t.status === "Done").length}{" "}
                <span>of {activeTasks.length} active tasks complete</span>
              </strong>
            </div>
            <div className="progress-track">
              <span
                style={{
                  width: `${activeTasks.length ? (activeTasks.filter((t) => t.status === "Done").length / activeTasks.length) * 100 : 0}%`,
                }}
              />
            </div>
            <div className="team-compact">
              <span className="avatar tint-0">GK</span>
              <span className="small muted">{members.length} members</span>
            </div>
          </div>
          <div className="board-toolbar">
            <span className="small muted">
              Workspace task board · Reviewed by you
            </span>
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
              Task statuses <span>10 available</span>
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
          {suggestions.some((s) => s.source === "rubric") &&
            !tasks.some((t) => /computational thinking/i.test(t.title)) && (
              <div className="requirement-gap">
                <div>
                  <AlertTriangle size={17} />
                  <strong>Missing work</strong>
                  <span>
                    No confirmed task covers the computational thinking
                    analysis.
                  </span>
                  <Citation id="rubric" onOpen={onEvidence} />
                </div>
                <button onClick={() => setTab("review")}>
                  Review suggestion <ArrowRight size={14} />
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
                  {visible.filter((t) => taskLane(t.status) === status).length}
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
                      visible.filter((t) => taskLane(t.status) === status)
                        .length
                    }
                  </span>
                </header>
                <div className="task-stack">
                  {visible
                    .filter((t) => taskLane(t.status) === status)
                    .map((t) => (
                      <article
                        className="task-card"
                        data-status={t.status}
                        data-lane={taskLane(t.status)}
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
                                        flag:
                                          x.flag === "Overdue" &&
                                          ["Done", "Archived"].includes(
                                            e.target.value,
                                          )
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
                  {!visible.some((t) => taskLane(t.status) === status) && (
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
                    <TaskStatusPill status={s.status ?? "To do"} />
                  </span>
                  <select
                    aria-label={`Initial status for ${s.title}`}
                    value={s.status ?? "To do"}
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
              setTasks((ts) =>
                ts.map((t) => (t.id === editing.id ? editing : t)),
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
                    flag:
                      editing.flag === "Overdue" &&
                      ["Done", "Archived"].includes(e.target.value)
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
                {team.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
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
