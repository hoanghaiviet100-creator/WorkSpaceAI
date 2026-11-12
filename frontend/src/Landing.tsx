import { useRef, useState, type ComponentProps } from "react";
import {
  ArrowRight,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronDown,
  FileText,
  Menu,
  Plus,
  Search,
  Upload,
  X,
} from "lucide-react";
import ActionMenu from "./ActionMenu";
import { Brand, DialogCancel, Modal, ThemeControl } from "./components";
import { activityLabel, workspaceColor, workspaceHistory } from "./home-model";
import type { Workspace } from "./data";
import flashcardIcon from "./flashcard-icon.svg";
import quizIcon from "./quiz-icon.svg";

const sessionKey = "wai-landing-demo-name";
const draftKey = "wai-landing-prompt";
function readSession(key: string) {
  try {
    return sessionStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}
function saveSession(key: string, value: string) {
  try {
    sessionStorage.setItem(key, value);
  } catch {
    /* The current page still retains the value. */
  }
}

const features = [
  {
    id: "upload",
    title: "Upload your sources",
    description: "Bring PDFs, Word documents, slides, and links.",
    icon: FileText,
  },
  {
    id: "answers",
    title: "Ask with citations",
    description: "Follow each citation back to the original passage.",
    icon: BookOpen,
  },
  {
    id: "cards",
    title: "Review with flashcards",
    description: "Turn key ideas into cards you can flip and review.",
    image: flashcardIcon,
  },
  {
    id: "quiz",
    title: "Check your understanding",
    description: "See which topics you know and which need practice.",
    image: quizIcon,
  },
] as const;

function Features({ compact = false }: { compact?: boolean }) {
  return (
    <div
      className={
        compact ? "landing-feature-grid is-compact" : "landing-feature-grid"
      }
    >
      {features.map((feature) => (
        <article className="landing-feature" key={feature.id}>
          {!compact && (
            <div
              className={`landing-mini landing-mini-${feature.id}`}
              aria-hidden="true"
            >
              {feature.id === "upload" && (
                <div className="mini-sheet">
                  <FileText size={19} />
                  <span>
                    Lecture notes.pdf<small>Ready</small>
                  </span>
                  <Check size={13} />
                </div>
              )}
              {feature.id === "answers" && (
                <div className="mini-sheet mini-answer">
                  <span>What is spaced repetition?</span>
                  <span>
                    Reviewing at increasing intervals.
                    <small>
                      <b>[1]</b>
                      <b>[2]</b>
                    </small>
                  </span>
                </div>
              )}
              {feature.id === "cards" && (
                <div className="mini-card">
                  <small>FLASHCARD 01</small>
                  <span>What is active recall?</span>
                </div>
              )}
              {feature.id === "quiz" && (
                <div className="mini-sheet mini-quiz">
                  <span>
                    <strong>4 / 5</strong> correct
                  </span>
                  <i />
                  <small>Quiz results</small>
                </div>
              )}
            </div>
          )}
          <div className="landing-feature-copy">
            {"image" in feature ? (
              <img src={feature.image} width={32} height={32} alt="" />
            ) : (
              <feature.icon size={21} aria-hidden="true" />
            )}
            <div>
              <h3>{feature.title}</h3>
              <p>{feature.description}</p>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function LandingDialog(props: ComponentProps<typeof Modal>) {
  return <Modal {...props} className="landing-dialog" exitDuration={150} />;
}

type Dialog =
  | "signin"
  | "signup"
  | "new"
  | "features"
  | "about"
  | "settings"
  | "terms"
  | "privacy";

export default function Landing({
  workspaces,
  open,
  create,
  start,
  rename,
  remove,
}: {
  workspaces: Workspace[];
  open: (id: string) => void;
  create: (name: string, description: string) => void;
  start: (prompt: string, files: File[], noteId: string) => void;
  rename: (id: string, name: string) => void;
  remove: (id: string) => void;
}) {
  const [profile, setProfile] = useState(() => readSession(sessionKey));
  const [prompt, setPrompt] = useState(() => readSession(draftKey));
  const [displayName, setDisplayName] = useState("");
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState("");
  const [target, setTarget] = useState("");
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("recent");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editing, setEditing] = useState<{
    note: Workspace;
    action: "rename" | "delete";
  } | null>(null);
  const picker = useRef<HTMLInputElement>(null);
  const uploadFirst = useRef(false);
  const composer = useRef<HTMLTextAreaElement>(null);
  const signedIn = !!profile;
  const history = workspaceHistory(workspaces).filter(({ workspace }) =>
    workspace.name
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );
  if (sort === "name")
    history.sort((a, b) => a.workspace.name.localeCompare(b.workspace.name));

  const changePrompt = (value: string) => {
    setPrompt(value);
    saveSession(draftKey, value);
  };
  const changeProfile = (value: string) => {
    setProfile(value);
    saveSession(sessionKey, value);
    if (!value) {
      setFiles([]);
      setFileError("");
      setTarget("");
    }
    setDialog(null);
    setMobileMenu(false);
  };
  const chooseFiles = (first = false) => {
    if (!signedIn) {
      setDialog("signin");
      return;
    }
    uploadFirst.current = first;
    picker.current?.click();
  };
  const acceptFiles = (picked: File[], first = false) => {
    const allowed = picked.filter(
      (file) =>
        /\.(pdf|docx|pptx|txt|md|csv)$/i.test(file.name) &&
        file.size > 0 &&
        file.size <= 25 * 1024 * 1024,
    );
    setFileError(
      allowed.length < picked.length
        ? "Choose supported files between 1 byte and 25 MB."
        : "",
    );
    if (first && allowed.length !== picked.length) composer.current?.focus();
    if (!allowed.length) return;
    if (first && allowed.length === picked.length) {
      start("", allowed, "");
      return;
    }
    setFiles((current) => {
      const keys = new Set(
        current.map((file) => `${file.name}:${file.size}:${file.lastModified}`),
      );
      return [
        ...current,
        ...allowed.filter((file) => {
          const key = `${file.name}:${file.size}:${file.lastModified}`;
          if (keys.has(key)) return false;
          keys.add(key);
          return true;
        }),
      ];
    });
  };
  const show = (next: Dialog) => {
    setMobileMenu(false);
    if (next === "new") {
      setName("");
      setDescription("");
    }
    setDialog(next);
  };
  const navigate = (section: "home" | "features" | "about") => {
    setMobileMenu(false);
    if (section === "home") window.scrollTo({ top: 0 });
    else if (signedIn) show(section);
    else
      document
        .getElementById(`landing-${section}`)
        ?.scrollIntoView({ block: "start" });
  };
  const action = signedIn ? (
    <button
      className="landing-gloss landing-primary-action"
      onClick={() => show("new")}
    >
      <Plus size={16} /> New note
    </button>
  ) : (
    <button
      className="landing-gloss landing-primary-action"
      onClick={() => show("signup")}
    >
      Get started free <ArrowRight size={16} />
    </button>
  );

  return (
    <div className="workspace-landing">
      <div className="landing-frame" data-signed-in={signedIn}>
        <header className="landing-header">
          <Brand onClick={() => navigate("home")} />
          <nav
            className="landing-navigation"
            data-open={mobileMenu}
            aria-label="Main navigation"
            id="landing-navigation"
          >
            <button onClick={() => navigate("home")}>Home</button>
            <button onClick={() => navigate("features")}>Features</button>
            <button onClick={() => navigate("about")}>About</button>
            <div className="landing-mobile-action">{action}</div>
          </nav>
          <div className="landing-header-actions">
            <div className="landing-desktop-action">{action}</div>
            {signedIn && (
              <div className="landing-avatar">
                <ActionMenu
                  exitDuration={150}
                  label={`Account menu for ${profile}`}
                  triggerContent={profile.slice(0, 1).toLocaleUpperCase()}
                  actions={[
                    { label: "Settings", run: () => show("settings") },
                    { label: "Sign out", run: () => changeProfile("") },
                  ]}
                />
              </div>
            )}
            <button
              className="landing-menu-toggle"
              aria-label={mobileMenu ? "Close navigation" : "Open navigation"}
              aria-expanded={mobileMenu}
              aria-controls="landing-navigation"
              onClick={() => setMobileMenu(!mobileMenu)}
            >
              {mobileMenu ? <X size={21} /> : <Menu size={21} />}
            </button>
          </div>
        </header>

        <main id="main-content">
          <section className="landing-hero" aria-labelledby="landing-title">
            <div className="landing-hero-atmosphere" aria-hidden="true" />
            <div className="landing-hero-content">
              {!signedIn && (
                <p className="landing-kicker">
                  <span /> Learn smarter with AI
                </p>
              )}
              <h1 id="landing-title">
                {signedIn ? (
                  `Hi, ${profile}. What would you like to learn today?`
                ) : (
                  <>
                    Turn your documents
                    <br />
                    into understanding.
                  </>
                )}
              </h1>
              {!signedIn && (
                <p className="landing-description">
                  Ask questions with citations, then turn key ideas into
                  flashcards and quizzes.
                </p>
              )}
              <form
                className="landing-composer"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!signedIn) {
                    show("signin");
                    return;
                  }
                  if (!prompt.trim() && !files.length) return;
                  start(prompt.trim(), files, target);
                  changePrompt("");
                  setFiles([]);
                }}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => {
                  event.preventDefault();
                  if (signedIn)
                    acceptFiles(Array.from(event.dataTransfer.files));
                  else show("signin");
                }}
              >
                <textarea
                  ref={composer}
                  aria-label="What would you like to learn today?"
                  placeholder={
                    signedIn
                      ? "Ask a question about your documents…"
                      : "What would you like to learn today?"
                  }
                  value={prompt}
                  maxLength={4000}
                  onClick={() => {
                    if (!signedIn) show("signin");
                  }}
                  onChange={(event) => changePrompt(event.target.value)}
                  onKeyDown={(event) => {
                    if (
                      event.key === "Enter" &&
                      !event.shiftKey &&
                      !event.nativeEvent.isComposing
                    ) {
                      event.preventDefault();
                      event.currentTarget.form?.requestSubmit();
                    }
                  }}
                />
                {files.length > 0 && (
                  <ul
                    className="landing-attachments"
                    aria-label="Attached documents"
                  >
                    {files.map((file, index) => (
                      <li
                        key={`${file.name}-${file.size}-${file.lastModified}`}
                      >
                        <span>{file.name}</span>
                        <button
                          type="button"
                          aria-label={`Remove ${file.name}`}
                          onClick={() =>
                            setFiles((current) =>
                              current.filter((_, i) => i !== index),
                            )
                          }
                        >
                          <X size={15} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {fileError && (
                  <p className="landing-file-error" role="alert">
                    {fileError}
                  </p>
                )}
                <div className="landing-composer-actions">
                  <button
                    type="button"
                    className="landing-attach"
                    aria-label="Attach documents"
                    onClick={() => chooseFiles()}
                  >
                    <Plus size={21} />
                  </button>
                  <input
                    ref={picker}
                    type="file"
                    hidden
                    multiple
                    accept=".pdf,.docx,.pptx,.txt,.md,.csv"
                    onChange={(event) => {
                      acceptFiles(
                        Array.from(event.target.files ?? []),
                        uploadFirst.current,
                      );
                      event.currentTarget.value = "";
                    }}
                  />
                  {signedIn && workspaces.length > 0 && (
                    <label className="landing-note-target">
                      <span className="sr-only">Destination note</span>
                      <select
                        value={target}
                        onChange={(event) => setTarget(event.target.value)}
                      >
                        <option value="">New note</option>
                        {workspaces.map((note) => (
                          <option key={note.id} value={note.id}>
                            {note.name}
                          </option>
                        ))}
                      </select>
                      <ChevronDown size={14} aria-hidden="true" />
                    </label>
                  )}
                  <button
                    type="submit"
                    className="landing-gloss landing-send"
                    aria-label="Send question"
                    disabled={signedIn && !prompt.trim() && !files.length}
                  >
                    <ArrowUp size={19} aria-hidden="true" />
                  </button>
                </div>
              </form>
            </div>
          </section>

          {signedIn ? (
            <section
              className="landing-section landing-recent"
              aria-labelledby="landing-recent"
            >
              <header className="landing-recent-heading">
                <div>
                  <h2 id="landing-recent">Recent notes</h2>
                  <p>
                    {workspaces.length}{" "}
                    {workspaces.length === 1 ? "note" : "notes"}
                  </p>
                </div>
                <div className="landing-note-controls">
                  <label>
                    <Search size={17} />
                    <input
                      type="search"
                      aria-label="Search notes"
                      placeholder="Search notes"
                      value={query}
                      onChange={(event) => setQuery(event.target.value)}
                    />
                  </label>
                  <select
                    aria-label="Sort notes"
                    value={sort}
                    onChange={(event) => setSort(event.target.value)}
                  >
                    <option value="recent">Most recent</option>
                    <option value="name">Name</option>
                  </select>
                </div>
              </header>
              {workspaces.length ? (
                <div className="landing-note-grid">
                  <button
                    className="landing-new-tile"
                    onClick={() => show("new")}
                  >
                    <span>
                      <Plus size={23} />
                    </span>
                    <strong>New note</strong>
                    <small>Start with a document or question.</small>
                  </button>
                  {history.map(({ workspace, updated }) => {
                    const sets = (workspace.studySets ?? []).filter(
                      (set) => set.status === "ready",
                    );
                    const cards = sets.filter(
                      (set) => set.config.kind === "flashcard",
                    );
                    const total = cards.reduce(
                      (sum, set) => sum + set.items.length,
                      0,
                    );
                    const mastered = cards.reduce(
                      (sum, set) =>
                        sum +
                        set.items.filter((item) => set.mastered?.[item.id])
                          .length,
                      0,
                    );
                    const score = sets
                      .filter(
                        (set) => set.config.kind === "quiz" && set.lastScore,
                      )
                      .sort(
                        (a, b) =>
                          Date.parse(b.lastScore?.completedAt ?? b.createdAt) -
                          Date.parse(a.lastScore?.completedAt ?? a.createdAt),
                      )[0]?.lastScore;
                    return (
                      <article
                        className="landing-note-card workspace-identity"
                        key={workspace.id}
                        data-workspace-color={workspaceColor(workspace)}
                      >
                        <button
                          className="landing-note-open"
                          aria-label={`Open note: ${workspace.name}`}
                          onClick={() => open(workspace.id)}
                        >
                          <span className="landing-note-mark">
                            <BookOpen size={19} />
                          </span>
                          <strong>{workspace.name}</strong>
                          <span className="landing-note-meta">
                            {workspace.sources.length}{" "}
                            {workspace.sources.length === 1
                              ? "source"
                              : "sources"}{" "}
                            · {activityLabel(updated)}
                          </span>
                          <span className="landing-note-progress">
                            <span>
                              {total
                                ? `${mastered}/${total} cards mastered`
                                : "No flashcards"}
                            </span>
                            <span>
                              {score?.total
                                ? `Quiz ${Math.round((score.correct / score.total) * 100)}%`
                                : "No quiz score"}
                            </span>
                          </span>
                        </button>
                        <ActionMenu
                          exitDuration={150}
                          label={`Options for ${workspace.name}`}
                          actions={[
                            {
                              label: "Rename",
                              run: () => {
                                setName(workspace.name);
                                setEditing({
                                  note: workspace,
                                  action: "rename",
                                });
                              },
                            },
                            {
                              label: "Delete",
                              danger: true,
                              run: () =>
                                setEditing({
                                  note: workspace,
                                  action: "delete",
                                }),
                            },
                          ]}
                        />
                      </article>
                    );
                  })}
                  {history.length === 0 && (
                    <p className="landing-no-results">
                      No notes match “{query}”.
                    </p>
                  )}
                </div>
              ) : (
                <div className="landing-empty">
                  <Upload size={25} />
                  <h3>Add your first source</h3>
                  <p>
                    Upload a document to start a note, or create a blank note.
                  </p>
                  <button
                    className="landing-gloss"
                    onClick={() => chooseFiles(true)}
                  >
                    Upload your first document <ArrowUpRight size={16} />
                  </button>
                  <button className="landing-link" onClick={() => show("new")}>
                    Create a blank note
                  </button>
                </div>
              )}
            </section>
          ) : (
            <>
              <section className="landing-section" id="landing-features">
                <h2>Learn from your own documents.</h2>
                <Features />
              </section>
              <section
                className="landing-section landing-steps"
                id="landing-about"
              >
                <h2>How it works</h2>
                <ol>
                  <li>
                    <span>1</span>
                    <div>
                      <strong>Upload your sources</strong>
                      <p>Add the documents you want to study.</p>
                    </div>
                  </li>
                  <li>
                    <span>2</span>
                    <div>
                      <strong>Ask in one conversation</strong>
                      <p>Check answers against cited passages.</p>
                    </div>
                  </li>
                  <li>
                    <span>3</span>
                    <div>
                      <strong>Review and test yourself</strong>
                      <p>
                        Use flashcards and quizzes to find what needs practice.
                      </p>
                    </div>
                  </li>
                </ol>
              </section>
              <section className="landing-section landing-start">
                <h2>Start with a document.</h2>
                <button
                  className="landing-gloss"
                  onClick={() => show("signup")}
                >
                  Get started free <ArrowRight size={17} />
                </button>
              </section>
            </>
          )}
        </main>

        <footer className="landing-footer">
          <span>WorkspaceAI</span>
          <nav aria-label="Footer">
            <a
              href="https://github.com/hoanghaiviet100-creator/WorkSpaceAI/issues"
              target="_blank"
              rel="noreferrer"
            >
              Contact
            </a>
            <button onClick={() => show("terms")}>Terms</button>
            <button onClick={() => show("privacy")}>Privacy</button>
          </nav>
          <button
            className="landing-preview-toggle"
            role="switch"
            aria-checked={signedIn}
            aria-label="Preview signed-in experience"
            onClick={() => changeProfile(signedIn ? "" : "Alex")}
          >
            Preview <span>{signedIn ? "Signed in" : "Guest"}</span>
          </button>
        </footer>
      </div>

      {(dialog === "signin" || dialog === "signup") && (
        <LandingDialog
          title={dialog === "signin" ? "Sign in" : "Create account"}
          onClose={() => setDialog(null)}
        >
          <p className="landing-dialog-note">
            This preview uses a demo profile on this browser.
          </p>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              changeProfile(displayName.trim() || "Alex");
              requestAnimationFrame(() =>
                composer.current?.focus({ preventScroll: true }),
              );
            }}
          >
            <label>
              Display name{" "}
              <input
                value={displayName}
                onChange={(event) => setDisplayName(event.target.value)}
                placeholder="Alex"
                autoComplete="given-name"
                maxLength={40}
              />
            </label>
            <button className="landing-gloss" type="submit">
              Continue with demo <ArrowRight size={16} />
            </button>
          </form>
          <button
            className="landing-link"
            onClick={() => setDialog(dialog === "signin" ? "signup" : "signin")}
          >
            {dialog === "signin"
              ? "Create account"
              : "Already have an account? Sign in"}
          </button>
        </LandingDialog>
      )}
      {(dialog === "new" || editing?.action === "rename") && (
        <LandingDialog
          title={editing ? "Rename note" : "New note"}
          onClose={() => {
            setDialog(null);
            setEditing(null);
          }}
        >
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (!name.trim()) return;
              if (editing) rename(editing.note.id, name.trim());
              else create(name.trim(), description.trim());
              setDialog(null);
              setEditing(null);
            }}
          >
            <label>
              Note name{" "}
              <input
                autoFocus
                required
                maxLength={80}
                placeholder="e.g. Research methods"
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            {!editing && (
              <label>
                Description{" "}
                <textarea
                  maxLength={180}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Optional"
                />
              </label>
            )}
            <div className="modal-actions">
              <DialogCancel />
              <button
                className="landing-gloss"
                type="submit"
                disabled={!name.trim()}
              >
                {editing ? "Save name" : "Create note"}
              </button>
            </div>
          </form>
        </LandingDialog>
      )}
      {editing?.action === "delete" && (
        <LandingDialog title="Delete note?" onClose={() => setEditing(null)}>
          <p>
            “{editing.note.name}” will be removed from Recent notes on this
            browser.
          </p>
          <div className="modal-actions">
            <DialogCancel />
            <button
              className="landing-gloss"
              onClick={() => {
                remove(editing.note.id);
                if (target === editing.note.id) setTarget("");
                setEditing(null);
              }}
            >
              Delete note
            </button>
          </div>
        </LandingDialog>
      )}
      {dialog === "features" && (
        <LandingDialog title="Features" onClose={() => setDialog(null)}>
          <Features compact />
        </LandingDialog>
      )}
      {dialog === "about" && (
        <LandingDialog
          title="About WorkspaceAI"
          onClose={() => setDialog(null)}
        >
          <p>
            WorkspaceAI is a study space for your documents. Each note brings
            together sources, one conversation with citations, and study tools.
          </p>
        </LandingDialog>
      )}
      {dialog === "settings" && (
        <LandingDialog title="Settings" onClose={() => setDialog(null)}>
          <div className="form-stack">
            <p>Workspace appearance</p>
            <ThemeControl />
          </div>
        </LandingDialog>
      )}
      {dialog === "terms" && (
        <LandingDialog title="Terms" onClose={() => setDialog(null)}>
          <p>
            WorkspaceAI is a project preview. Check cited passages before
            relying on an answer, and upload documents you have permission to
            use.
          </p>
        </LandingDialog>
      )}
      {dialog === "privacy" && (
        <LandingDialog title="Privacy" onClose={() => setDialog(null)}>
          <p>
            This browser stores your notes and demo preferences. Uploads and
            chat requests go to the configured WorkspaceAI server. The demo does
            not collect a password.
          </p>
        </LandingDialog>
      )}
    </div>
  );
}
