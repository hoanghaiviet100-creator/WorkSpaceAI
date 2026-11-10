import { useState } from "react";
import { ArrowUpRight, ArrowRight, Plus } from "lucide-react";
import { Brand, Modal } from "./components";
import { activityLabel, workspaceColor, workspaceHistory } from "./home-model";
import type { HomeProps } from "./Home";

export default function Landing({
  workspaces,
  open,
  create,
  tools,
}: HomeProps) {
  const [creating, setCreating] = useState(false);
  const [howOpen, setHowOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const history = workspaceHistory(workspaces);
  const newWorkspace = () => setCreating(true);
  return (
    <div className="workspace-landing">
      <header className="landing-header landing-wrap">
        <Brand
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        />
        <nav className="landing-navigation" aria-label="Main navigation">
          <button className="landing-how-link" onClick={() => setHowOpen(true)}>
            How it works
          </button>
          <div className="landing-utilities">{tools}</div>
        </nav>
      </header>
      <main id="main-content" className="landing-wrap">
        <section className="landing-hero" aria-labelledby="landing-title">
          <div className="landing-hero-copy">
            <p className="landing-kicker">Ask · Tasks · Email</p>
            <h1 id="landing-title">
              From course
              <br />
              files to a report
              <br />
              you can stand
              <br />
              behind.
            </h1>
            <p className="landing-description">
              Upload your documents, tick the ones to use, and get cited
              answers, confirmed tasks and approved emails. Nothing happens
              without you.
            </p>
            <button
              className="landing-button landing-primary landing-main-create"
              onClick={newWorkspace}
            >
              New workspace
            </button>
          </div>
          <div className="landing-hero-rule" aria-hidden="true">
            <span />
          </div>
        </section>
        <section
          className="landing-history"
          aria-labelledby="workspace-history-title"
          data-ui
        >
          <header className="landing-history-heading">
            <h2 id="workspace-history-title">Your workspaces</h2>
            <span>
              {workspaces.length}{" "}
              {workspaces.length === 1 ? "workspace" : "workspaces"}
            </span>
          </header>
          {history.length ? (
            <div className="landing-workspace-grid">
              {history.map(({ workspace, thread, updated }) => (
                <button
                  key={workspace.id}
                  className="landing-workspace workspace-identity"
                  data-workspace-color={workspaceColor(workspace)}
                  aria-label={`Open workspace ${workspace.name}`}
                  onClick={() => open(workspace.id, thread?.id, "chat")}
                >
                  <span className="workspace-bookmark" aria-hidden="true">
                    <span />
                  </span>
                  <span className="landing-workspace-info">
                    <strong>{workspace.name}</strong>
                    <span>
                      {workspace.sources.length}{" "}
                      {workspace.sources.length === 1 ? "file" : "files"} ·{" "}
                      {workspace.threads.length}{" "}
                      {workspace.threads.length === 1
                        ? "conversation"
                        : "conversations"}
                    </span>
                  </span>
                  <span className="landing-workspace-end">
                    <time
                      dateTime={updated || undefined}
                      title={
                        updated
                          ? new Date(updated).toLocaleString("en-US", {
                              timeZone: "Asia/Bangkok",
                            })
                          : undefined
                      }
                    >
                      {activityLabel(updated)}
                    </time>
                    <ArrowUpRight size={16} />
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <p className="landing-history-empty">
              Your workspaces will appear here. Create one to keep your
              documents and conversations together.
            </p>
          )}
        </section>
        <section
          className="landing-start"
          aria-labelledby="landing-start-title"
        >
          <h2 id="landing-start-title">Start with one workspace.</h2>
        </section>
      </main>
      <footer className="landing-footer landing-wrap">
        <p>WorkspaceAI · Computational Thinking (CSC10014)</p>
        <p>VNU-HCM University of Science</p>
      </footer>
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
                maxLength={180}
                placeholder="What are you working on?"
                value={description}
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
      {howOpen && (
        <Modal title="How WorkspaceAI works" onClose={() => setHowOpen(false)}>
          <ol className="landing-how-steps">
            <li>
              <strong>Add your sources.</strong>
              <p>
                Create a workspace and upload text-based PDF, TXT, MD or CSV
                files. Select the files you want to use.
              </p>
            </li>
            <li>
              <strong>Ask with the evidence beside you.</strong>
              <p>
                Ask about the selected documents, then open the citations to
                check the source.
              </p>
            </li>
            <li>
              <strong>Review the next action.</strong>
              <p>
                Confirm task suggestions or review an email draft before taking
                action. Current local email delivery is a simulation.
              </p>
            </li>
          </ol>
          <div className="modal-actions">
            <button className="button" onClick={() => setHowOpen(false)}>
              Close
            </button>
            <button
              className="button primary"
              onClick={() => {
                setHowOpen(false);
                setCreating(true);
              }}
            >
              New workspace
              <Plus size={15} />
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
