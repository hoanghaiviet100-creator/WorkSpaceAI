import { useState, Fragment } from "react";
import {
  Plus,
  ArrowUpRight,
  Search,
  MessageSquare,
  Columns3,
  Mail,
  Folder,
  MoreHorizontal,
  Pencil,
  Trash2,
  ArrowRight,
  Clock,
  Check,
} from "lucide-react";
import { Badge, Modal } from "./components";
import { type Workspace, type Thread, type Mode } from "./data";
import { isOpenTask } from "./task-status";
type Props = {
  workspaces: Workspace[];
  open: (w: string, t?: string) => void;
  create: (name: string, description: string) => void;
  updateThread: (w: string, t: string, title: string | null) => void;
};
export default function Home({
  workspaces,
  open,
  create,
  updateThread,
}: Props) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("All features");
  const [scope, setScope] = useState("All workspaces");
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<{ w: string; t: Thread } | null>(null);
  const [title, setTitle] = useState("");
  const [menu, setMenu] = useState<string | null>(null);
  const rows = workspaces
    .flatMap((w) => w.threads.map((t) => ({ w, t })))
    .filter(
      ({ w, t }) =>
        (scope === "All workspaces" || scope === w.id) &&
        (mode === "All features" || mode === t.mode) &&
        `${t.title} ${w.name}`.toLowerCase().includes(query.toLowerCase()),
    )
    .sort(
      (a, b) =>
        workspaces.indexOf(a.w) - workspaces.indexOf(b.w) ||
        b.t.updated.localeCompare(a.t.updated),
    );
  const icons = { Ask: MessageSquare, Tasks: Columns3, Email: Mail };
  return (
    <main className="home-page" id="main-content">
      <div className="home-intro">
        <div>
          <p className="desk-caption">Your personal research desk</p>
          <h1>A little clarity. A lot of possibility.</h1>
        </div>
        <span className="home-date">Wednesday, November 4</span>
      </div>
      <section className="brand-hero" aria-label="WorkspaceAI research hub">
        <div className="hero-top">
          <span>Ideas have a place here.</span>
          <span>Sources → Understanding → Action</span>
        </div>
        <div className="hero-middle">
          <p>
            Bring your documents.
            <br />
            Find your next move.
          </p>
          <span className="hero-plus" aria-hidden="true">
            +
          </span>
        </div>
        <div className="hero-bottom">
          <h2>
            WORKSPACE<span>+</span>
          </h2>
          <button className="button hero-cta" onClick={() => setCreating(true)}>
            Create workspace <Plus size={17} />
          </button>
        </div>
      </section>
      <section className="workspace-section">
        <div className="section-heading">
          <h2>
            Your workspaces <span className="count">{workspaces.length}</span>
          </h2>
          <button className="text-button" onClick={() => setCreating(true)}>
            <Plus size={15} />
            New workspace
          </button>
        </div>
        <div
          className="workspace-grid"
          data-layout={workspaces.length % 3 === 0 ? "three" : "two"}
        >
          {workspaces.map((w, i) => (
            <button
              className="workspace-card"
              data-tone={
                w.id === "midterm"
                  ? "course"
                  : w.id === "thesis"
                    ? "reading"
                    : "personal"
              }
              onClick={() => open(w.id)}
              key={w.id}
            >
              <div className="workspace-card-top">
                <span className="workspace-index">
                  <Folder size={19} />
                  {w.id === "midterm"
                    ? "Course project"
                    : w.id === "thesis"
                      ? "Reading group"
                      : "Personal workspace"}
                </span>
                <ArrowUpRight size={18} />
              </div>
              <h3>{w.name}</h3>
              <p>
                {w.description || "A new space for your sources and ideas."}
              </p>
              <div className="workspace-card-bottom">
                <span>
                  <strong>{w.sources.length}</strong> files{" "}
                  <span className="dot-separator">·</span>{" "}
                  <strong>{w.tasks.filter(isOpenTask).length}</strong> open
                  tasks
                </span>
                <span className="workspace-activity">
                  {`Active ${new Date(w.updated).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "Asia/Bangkok" })}`}
                </span>
              </div>
            </button>
          ))}
        </div>
      </section>
      <section className="recent-section">
        <div className="section-heading">
          <div>
            <h2>Pick up where you left off.</h2>
            <p>Your conversations, connected to their workspace.</p>
          </div>
          <span className="small muted">{rows.length} conversations</span>
        </div>
        <div className="history-toolbar">
          <label className="search-field">
            <Search size={16} />
            <input
              aria-label="Search conversations"
              placeholder="Search conversations…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="history-filters">
            <select
              aria-label="Filter by workspace"
              value={scope}
              onChange={(e) => setScope(e.target.value)}
            >
              <option>All workspaces</option>
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
            <select
              aria-label="Filter by feature"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option>All features</option>
              {["Ask", "Tasks", "Email"].map((m) => (
                <option key={m}>{m}</option>
              ))}
            </select>
          </div>
        </div>
        <div className="history-table">
          <div className="history-table-head">
            <span>Conversation</span>
            <span>Workspace</span>
            <span>Feature</span>
            <span>Last activity</span>
            <span />
          </div>
          {rows.map(({ w, t }, index) => {
            const Icon = icons[t.mode];
            return (
              <Fragment key={t.id}>
                {(index === 0 || rows[index - 1].w.id !== w.id) && (
                  <div className="history-group">
                    <Folder size={13} />
                    {w.name}
                    <span>
                      {rows.filter((row) => row.w.id === w.id).length}{" "}
                      conversations
                    </span>
                  </div>
                )}
                <div className="history-row">
                  <button
                    className="history-title"
                    onClick={() => open(w.id, t.id)}
                  >
                    <Icon size={16} />
                    <span>{t.title}</span>
                  </button>
                  <button
                    className="history-workspace"
                    onClick={() => open(w.id)}
                  >
                    {w.name}
                  </button>
                  <span className="feature-label">
                    <Icon size={12} />
                    {t.mode}
                  </span>
                  <span className="history-time">
                    {new Date(t.updated).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                      timeZone: "Asia/Bangkok",
                    })}
                  </span>
                  <div className="row-menu">
                    <button
                      className="icon-button"
                      aria-label={`Manage ${t.title}`}
                      aria-expanded={menu === t.id}
                      onClick={() => setMenu(menu === t.id ? null : t.id)}
                    >
                      <MoreHorizontal size={17} />
                    </button>
                    {menu === t.id && (
                      <div className="menu-popover">
                        <button
                          onClick={() => {
                            setEditing({ w: w.id, t });
                            setTitle(t.title);
                            setMenu(null);
                          }}
                        >
                          <Pencil size={14} />
                          Rename
                        </button>
                        <button
                          onClick={() => {
                            updateThread(w.id, t.id, null);
                            setMenu(null);
                          }}
                        >
                          <Trash2 size={14} />
                          Delete conversation
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </Fragment>
            );
          })}
          {!rows.length && (
            <div className="history-empty">
              <Search size={22} />
              <h3>No conversations found.</h3>
              <p>Try another search or start a conversation in a workspace.</p>
              <button
                className="button"
                onClick={() => {
                  setQuery("");
                  setMode("All features");
                  setScope("All workspaces");
                }}
              >
                Clear filters
              </button>
            </div>
          )}
        </div>
      </section>
      <footer className="home-footer">
        <span>Made for thoughtful work.</span>
        <span>
          <Check size={13} />
          Your evidence. Your decisions.
        </span>
      </footer>
      {creating && (
        <Modal title="Create a workspace" onClose={() => setCreating(false)}>
          <div className="create-preview">
            <Folder size={28} />
            <p>A fresh space for your next idea.</p>
          </div>
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
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
                placeholder="e.g. Research Methods – Group Project"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Description <span className="muted">(optional)</span>
              <textarea
                placeholder="What will you work on here?"
                value={description}
                maxLength={180}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <p className="small muted">
              Starts with an empty file repository and conversation history.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="button"
                onClick={() => setCreating(false)}
              >
                Cancel
              </button>
              <button className="button primary" disabled={!name.trim()}>
                Create workspace <ArrowRight size={15} />
              </button>
            </div>
          </form>
        </Modal>
      )}
      {editing && (
        <Modal title="Rename conversation" onClose={() => setEditing(null)}>
          <form
            className="form-stack"
            onSubmit={(e) => {
              e.preventDefault();
              if (title.trim()) {
                updateThread(editing.w, editing.t.id, title.trim());
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
                onChange={(e) => setTitle(e.target.value)}
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
    </main>
  );
}
