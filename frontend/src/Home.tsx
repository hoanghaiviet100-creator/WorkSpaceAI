import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import {
  Plus,
  ArrowUpRight,
  Search,
  MessageSquare,
  Columns3,
  Mail,
  MoreHorizontal,
  Pencil,
  Trash2,
  ArrowRight,
  FileText,
  ChevronDown,
  X,
  Check,
  FolderOpen,
  LayoutDashboard,
  Menu,
  BookOpen,
} from "lucide-react";
import { Brand, Modal } from "./components";
import type { Workspace, Thread, Mode, View } from "./data";
import { isOpenTask } from "./task-status";
import {
  activityLabel,
  conversationRows,
  conversationSources,
  dashboardData,
  workspaceColor,
} from "./home-model";
import { HomeMetrics, HomeAssistant, HomeInsights } from "./HomeOverview";

export type HomeProps = {
  workspaces: Workspace[];
  open: (workspaceId: string, threadId?: string, view?: View) => void;
  start: (workspaceId: string, prompt?: string) => void;
  create: (name: string, description: string) => void;
  updateThread: (
    workspaceId: string,
    threadId: string,
    title: string | null,
  ) => void;
  tools: ReactNode;
};
const features = [
  { mode: null, label: "All" },
  { mode: "Ask", label: "Q&A" },
  { mode: "Tasks", label: "Tasks" },
  { mode: "Email", label: "Email" },
] as const;
const featureNames = {
  Ask: "Document Q&A",
  Tasks: "Task planning",
  Email: "Email draft",
};
const featureIcons = { Ask: MessageSquare, Tasks: Columns3, Email: Mail };
const RECENT_LIMIT = 4;

export default function Home({
  workspaces,
  open,
  start,
  create,
  updateThread,
  tools,
}: HomeProps) {
  const [panel, setPanel] = useState<"overview" | "conversations">("overview");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<Mode | null>(null);
  const [scope, setScope] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [pendingView, setPendingView] = useState<View | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<{
    workspace: Workspace;
    thread: Thread;
  } | null>(null);
  const [deleting, setDeleting] = useState<{
    workspace: Workspace;
    thread: Thread;
  } | null>(null);
  const [title, setTitle] = useState("");
  const current = workspaces.find((workspace) => workspace.id === scope);
  const activeScope = current?.id ?? null;
  const data = dashboardData(workspaces, activeScope);
  const target = current ?? data.recent[0]?.workspace ?? workspaces[0];
  const all = conversationRows(workspaces, activeScope, null, query);
  const rows = conversationRows(workspaces, activeScope, mode, query);
  const filtered = !!query.trim() || mode !== null;
  const visible = showAll || filtered ? rows : rows.slice(0, RECENT_LIMIT);
  const threadCount = workspaces.reduce(
    (count, workspace) => count + workspace.threads.length,
    0,
  );
  const showPanel = (next: "overview" | "conversations") => {
    setPanel(next);
    setScopeOpen(false);
    setPendingView(null);
    setQuery("");
    setMode(null);
    setShowAll(false);
  };
  const selectScope = (id: string | null) => {
    setScope(id);
    setShowAll(false);
    setScopeOpen(false);
    if (id && pendingView) open(id, undefined, pendingView);
    setPendingView(null);
  };
  const chooseWorkspace = () => {
    setPendingView(null);
    setScopeOpen(true);
  };
  const openFeature = (view: View) => {
    if (current) {
      setScopeOpen(false);
      open(current.id, undefined, view);
    } else if (!workspaces.length) setCreating(true);
    else {
      setPendingView(view);
      setScopeOpen(true);
    }
  };
  const reset = () => {
    setQuery("");
    setMode(null);
    setShowAll(false);
  };
  const navigation = (
    <nav className="home-navigation" aria-label="Home navigation">
      <button
        aria-current={panel === "overview" ? "page" : undefined}
        onClick={() => showPanel("overview")}
      >
        <LayoutDashboard size={17} />
        Overview
      </button>
      <button
        aria-current={panel === "conversations" ? "page" : undefined}
        onClick={() => showPanel("conversations")}
      >
        <MessageSquare size={17} />
        Conversations
      </button>
      <button onClick={() => openFeature("tasks")}>
        <Columns3 size={17} />
        Tasks
      </button>
      <button onClick={() => openFeature("email")}>
        <Mail size={17} />
        Email drafts
      </button>
    </nav>
  );
  const directory = (
    <div className="desk-workspace-list">
      {!pendingView && (
        <button
          className={`desk-workspace all-workspaces ${!current ? "is-current" : ""}`}
          aria-pressed={!current}
          onClick={() => selectScope(null)}
        >
          <FolderOpen size={17} />
          <span>
            <strong>All workspaces</strong>
            <small>{threadCount} conversations</small>
          </span>
          {!current && <Check size={14} />}
        </button>
      )}
      {workspaces.map((workspace) => (
        <button
          key={workspace.id}
          className={`desk-workspace workspace-identity ${workspace.id === activeScope ? "is-current" : ""}`}
          data-workspace-color={workspaceColor(workspace)}
          aria-label={`Show conversations in ${workspace.name}`}
          aria-pressed={workspace.id === activeScope}
          onClick={() => selectScope(workspace.id)}
        >
          <span className="workspace-bookmark" aria-hidden="true">
            <span />
          </span>
          <span>
            <strong>{workspace.name}</strong>
            <small>
              {workspace.sources.length}{" "}
              {workspace.sources.length === 1 ? "file" : "files"} ·{" "}
              {workspace.tasks.filter(isOpenTask).length} open tasks
            </small>
          </span>
          {workspace.id === activeScope && <Check size={14} />}
        </button>
      ))}
    </div>
  );
  return (
    <div className="research-home">
      <aside className="home-sidebar" aria-label="Workspace navigation">
        <Brand
          onClick={() => {
            selectScope(null);
            showPanel("overview");
          }}
        />
        <button
          className="home-new-chat"
          onClick={() => (target ? start(target.id) : setCreating(true))}
        >
          <Plus size={17} />
          New chat
          <ArrowUpRight size={15} />
        </button>
        {navigation}
        <div className="home-directory-heading">
          <h2>Workspaces</h2>
          <button
            aria-label="New workspace"
            title="New workspace"
            onClick={() => setCreating(true)}
          >
            <Plus size={17} />
          </button>
        </div>
        {directory}
        {!workspaces.length && (
          <p className="home-sidebar-empty">
            Create a workspace for your first documents.
          </p>
        )}
        <div className="home-sidebar-footer">
          <BookOpen size={18} />
          <div>
            <strong>Your research, connected.</strong>
            <span>Workspaces saved on this device</span>
          </div>
        </div>
      </aside>
      <main className="home-main" id="main-content">
        <header className="home-topbar">
          <div className="home-mobile-brand">
            <button
              className="icon-button"
              aria-label="Open navigation"
              onClick={chooseWorkspace}
            >
              <Menu size={19} />
            </button>
            <Brand onClick={() => showPanel("overview")} />
          </div>
          <div className="home-title">
            <h1>{panel === "overview" ? "Overview" : "Conversations"}</h1>
            <p>
              {new Date().toLocaleDateString("en-US", {
                weekday: "long",
                month: "short",
                day: "numeric",
                timeZone: "Asia/Bangkok",
              })}
            </p>
          </div>
          <div className="home-global-search">
            <Search size={17} />
            <input
              type="search"
              aria-label="Search conversations"
              placeholder="Search conversations, workspaces…"
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setPanel("conversations");
                setShowAll(false);
              }}
            />
            {query && (
              <button
                aria-label="Clear conversation search"
                onClick={() => setQuery("")}
              >
                <X size={15} />
              </button>
            )}
          </div>
          <div className="header-right">{tools}</div>
        </header>
        <div className="home-canvas">
          <div className="home-scope-row">
            <button
              onClick={chooseWorkspace}
              aria-label="Choose workspace"
              aria-haspopup="dialog"
            >
              <span
                className="workspace-identity"
                data-workspace-color={
                  current ? workspaceColor(current) : undefined
                }
              >
                {current && <span className="workspace-dot" />}
                {current?.name ?? "All workspaces"}
              </span>
              <ChevronDown size={14} />
            </button>
            <span>
              {current
                ? `${current.sources.length} files · ${current.threads.length} conversations`
                : `${workspaces.length} workspaces · ${threadCount} conversations`}
            </span>
          </div>
          <div className="home-dashboard-grid">
            <div className="home-primary-column">
              <HomeMetrics data={data} />
              {panel === "overview" ? (
                <HomeAssistant
                  data={data}
                  target={target}
                  workspaces={workspaces}
                  choose={selectScope}
                  start={start}
                  open={open}
                  create={() => setCreating(true)}
                />
              ) : (
                <section
                  className="desk-conversations"
                  aria-labelledby="conversations-title"
                >
                  <div className="desk-section-heading">
                    <div>
                      <h2 id="conversations-title">
                        {current ? current.name : "Recent conversations"}
                      </h2>
                      <p>
                        {current
                          ? `${current.threads.length} ${current.threads.length === 1 ? "conversation" : "conversations"} in this workspace`
                          : "Your latest conversations, across every workspace."}
                      </p>
                    </div>
                    {current && (
                      <button
                        className="desk-open-workspace"
                        aria-label={`Open workspace ${current.name}`}
                        onClick={() => open(current.id)}
                      >
                        Open workspace
                        <ArrowUpRight size={16} />
                      </button>
                    )}
                  </div>
                  <div className="desk-list-controls">
                    <div
                      className="desk-feature-filters"
                      role="group"
                      aria-label="Filter conversations by feature"
                    >
                      {features.map((feature) => {
                        const count = feature.mode
                          ? all.filter(
                              (row) => row.thread.mode === feature.mode,
                            ).length
                          : all.length;
                        return (
                          <button
                            key={feature.label}
                            aria-pressed={mode === feature.mode}
                            onClick={() => {
                              setMode(feature.mode);
                              setShowAll(false);
                            }}
                          >
                            {feature.label}
                            <span>{count}</span>
                          </button>
                        );
                      })}
                    </div>
                    <span className="desk-sort-label">Newest first</span>
                  </div>
                  <div
                    className="desk-conversation-list"
                    aria-label="Saved conversations"
                  >
                    {visible.map(({ workspace, thread }) => {
                      const Icon = featureIcons[thread.mode];
                      const trail = conversationSources(workspace, thread);
                      const trailLabel = trail.sources.length
                        ? `${trail.sources[0].name}${trail.sources.length > 1 ? ` · +${trail.sources.length - 1} ${trail.sources.length === 2 ? "file" : "files"}` : ""}${trail.missing ? ` · ${trail.missing} unavailable` : ""}`
                        : trail.missing
                          ? `${trail.missing} ${trail.missing === 1 ? "source" : "sources"} no longer in the library`
                          : "No sources linked";
                      return (
                        <article
                          className="desk-conversation"
                          key={`${workspace.id}:${thread.id}`}
                        >
                          <button
                            className="desk-conversation-main"
                            onClick={() =>
                              open(workspace.id, thread.id, "chat")
                            }
                            aria-label={`Open conversation: ${thread.title}`}
                          >
                            <strong className="desk-conversation-title">
                              {thread.title}
                            </strong>
                            <span className="desk-conversation-context">
                              <span
                                className="workspace-identity desk-workspace-tag"
                                data-workspace-color={workspaceColor(workspace)}
                              >
                                <span className="workspace-dot" />
                                {workspace.name}
                              </span>
                              <span
                                className="desk-context-separator"
                                aria-hidden="true"
                              >
                                /
                              </span>
                              <span className="desk-feature">
                                <Icon size={13} />
                                {featureNames[thread.mode]}
                              </span>
                            </span>
                            <span
                              className="desk-source-trail"
                              title={
                                trail.sources.length
                                  ? trail.sources
                                      .map((source) => source.name)
                                      .join(", ")
                                  : trailLabel
                              }
                            >
                              <FileText size={13} />
                              <span>{trailLabel}</span>
                            </span>
                          </button>
                          <div className="desk-conversation-end">
                            <time
                              dateTime={thread.updated}
                              title={new Date(thread.updated).toLocaleString(
                                "en-US",
                                {
                                  timeZone: "Asia/Bangkok",
                                },
                              )}
                            >
                              {activityLabel(thread.updated)}
                            </time>
                            <ConversationActions
                              title={thread.title}
                              onRename={() => {
                                setEditing({ workspace, thread });
                                setTitle(thread.title);
                              }}
                              onDelete={() =>
                                setDeleting({ workspace, thread })
                              }
                            />
                          </div>
                        </article>
                      );
                    })}
                    {!rows.length && (
                      <div className="desk-empty">
                        <h3>
                          {filtered
                            ? "No matching conversations"
                            : current
                              ? "This workspace is ready for its first conversation."
                              : "Your research starts here."}
                        </h3>
                        <p>
                          {filtered
                            ? "Try another title, workspace name, or phrase from a question."
                            : current
                              ? "Open the workspace to add sources and ask your first question."
                              : "Create a workspace to keep your documents and conversations together."}
                        </p>
                        {filtered ? (
                          <button className="button" onClick={reset}>
                            Clear filters
                          </button>
                        ) : current ? (
                          <button
                            className="button"
                            onClick={() => open(current.id)}
                          >
                            Open workspace
                            <ArrowUpRight size={15} />
                          </button>
                        ) : (
                          <button
                            className="button"
                            onClick={() => setCreating(true)}
                          >
                            Create workspace
                            <Plus size={15} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  {rows.length > 0 && (
                    <footer className="desk-list-footer">
                      <span>
                        {filtered
                          ? `${rows.length} ${rows.length === 1 ? "result" : "results"}`
                          : `${visible.length} of ${rows.length} conversations`}
                      </span>
                      {!filtered && rows.length > RECENT_LIMIT && (
                        <button onClick={() => setShowAll(!showAll)}>
                          {showAll
                            ? "Show recent only"
                            : `View all ${rows.length} conversations`}
                          <ArrowRight size={15} />
                        </button>
                      )}
                    </footer>
                  )}
                </section>
              )}
            </div>
            <HomeInsights
              data={data}
              open={open}
              onTasks={() => openFeature("tasks")}
              onWorkspaces={chooseWorkspace}
              onHistory={() => {
                showPanel("conversations");
                setShowAll(true);
              }}
            />
          </div>
        </div>
      </main>
      {scopeOpen && (
        <Modal
          title={
            pendingView === "tasks"
              ? "Choose a task board"
              : pendingView === "email"
                ? "Choose an email workspace"
                : "Choose workspace"
          }
          onClose={() => {
            setScopeOpen(false);
            setPendingView(null);
          }}
          className="desk-scope-modal"
        >
          {navigation}
          {directory}
          <button
            className="button"
            onClick={() => {
              setScopeOpen(false);
              setCreating(true);
            }}
          >
            <Plus size={15} />
            New workspace
          </button>
        </Modal>
      )}
      {creating && (
        <Modal title="New workspace" onClose={() => setCreating(false)}>
          <p className="desk-modal-description">
            Keep one project's documents and conversations together.
          </p>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (!name.trim()) return;
              create(name.trim(), description.trim());
              setCreating(false);
              setName("");
              setDescription("");
            }}
          >
            <label>
              Workspace name
              <input
                autoFocus
                required
                maxLength={80}
                placeholder="e.g. Network programming"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <label>
              Description <span className="muted">(optional)</span>
              <textarea
                placeholder="What are you working on?"
                value={description}
                maxLength={180}
                onChange={(event) => setDescription(event.target.value)}
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button"
                onClick={() => setCreating(false)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={!name.trim()}>
                Create workspace
                <ArrowRight size={15} />
              </button>
            </div>
          </form>
        </Modal>
      )}
      {editing && (
        <Modal title="Rename conversation" onClose={() => setEditing(null)}>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (title.trim()) {
                updateThread(
                  editing.workspace.id,
                  editing.thread.id,
                  title.trim(),
                );
                setEditing(null);
              }
            }}
          >
            <label>
              Conversation name
              <input
                autoFocus
                required
                maxLength={120}
                value={title}
                onChange={(event) => setTitle(event.target.value)}
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
              <button className="button primary">Save name</button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal title="Delete conversation?" onClose={() => setDeleting(null)}>
          <p className="desk-modal-description">
            “{deleting.thread.title}” and its saved messages will be removed
            from {deleting.workspace.name}. This cannot be undone. Documents and
            tasks stay in the workspace.
          </p>
          <div className="modal-actions">
            <button className="button" onClick={() => setDeleting(null)}>
              Cancel
            </button>
            <button
              className="button desk-delete-confirm"
              onClick={() => {
                updateThread(deleting.workspace.id, deleting.thread.id, null);
                setDeleting(null);
              }}
            >
              Delete conversation
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ConversationActions({
  title,
  onRename,
  onDelete,
}: {
  title: string;
  onRename: () => void;
  onDelete: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (!open) return;
    menu.current?.querySelector<HTMLButtonElement>("button")?.focus();
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        trigger.current?.focus();
      }
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const items = [
          ...(menu.current?.querySelectorAll<HTMLButtonElement>("button") ??
            []),
        ];
        const index = items.indexOf(
          document.activeElement as HTMLButtonElement,
        );
        const next =
          event.key === "Home"
            ? 0
            : event.key === "End"
              ? items.length - 1
              : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) %
                items.length;
        items[next]?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    root.current?.addEventListener("keydown", keyboard);
    const element = root.current;
    return () => {
      document.removeEventListener("pointerdown", outside);
      element?.removeEventListener("keydown", keyboard);
    };
  }, [open]);
  const run = (action: () => void) => {
    setOpen(false);
    trigger.current?.focus();
    action();
  };
  return (
    <div
      className="desk-conversation-actions"
      ref={root}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node))
          setOpen(false);
      }}
    >
      <button
        className="icon-button"
        ref={trigger}
        aria-label={`Manage ${title}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen(!open)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <MoreHorizontal size={18} />
      </button>
      {open && (
        <div
          className="desk-row-menu"
          ref={menu}
          id={id}
          role="menu"
          aria-label={`Actions for ${title}`}
        >
          <button role="menuitem" onClick={() => run(onRename)}>
            <Pencil size={14} />
            Rename
          </button>
          <button
            role="menuitem"
            className="desk-delete-action"
            onClick={() => run(onDelete)}
          >
            <Trash2 size={14} />
            Delete conversation
          </button>
        </div>
      )}
    </div>
  );
}
