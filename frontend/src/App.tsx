import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  ArrowLeft,
  ArrowUpRight,
  Plus,
  MessageSquare,
  Columns3,
  Mail,
  Files,
  Menu,
  X,
  ChevronDown,
  ShieldCheck,
  FileText,
  Check,
  Search,
  Home as HomeIcon,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightOpen,
  LogIn,
} from "lucide-react";
import {
  Brand,
  ThemeControl,
  EvidenceContext,
  Modal,
  Badge,
  Notice,
  usePanelFocus,
} from "./components";
import {
  seedWorkspaces,
  emptyWorkspace,
  blankDraft,
  initialEmail,
  type Workspace,
  type Thread,
  type Mode,
  type View,
  type Handoff,
  type Task,
  type Suggestion,
} from "./data";
import Home from "./Home";
import Chat from "./Chat";
import Tasks from "./Tasks";
import Email from "./Email";
import Sources from "./Sources";
import DevicePreview, { DeviceControl } from "./DevicePreview";
import Auth, { type AuthMode } from "./Auth";
const STORE = "workspaceai-v2";
const AUTH_PATHS: Record<AuthMode, string> = {
  signin: "#login",
  signup: "#signup",
  reset: "#forgot-password",
};
function safeAuthReturn(value: string | null) {
  return value &&
    /^#(?:home|workspace\/[A-Za-z0-9_-]+\/(?:chat|tasks|email)\/[A-Za-z0-9_-]+)$/.test(
      value,
    )
    ? value
    : "#home";
}
const EMBEDDED_PREVIEW =
  new URLSearchParams(location.search).get("preview") === "phone";
type Route = {
  workspace?: string;
  thread?: string;
  view: View;
  auth?: AuthMode;
};
function readRoute(hash = location.hash): Route {
  const p = hash.slice(1).split("/");
  const auth =
    p[0] === "login"
      ? "signin"
      : p[0] === "signup"
        ? "signup"
        : p[0] === "forgot-password"
          ? "reset"
          : undefined;
  if (auth) return { view: "chat", auth };
  return p[0] === "workspace"
    ? {
        workspace: p[1],
        view: ["tasks", "email"].includes(p[2]) ? (p[2] as View) : "chat",
        thread: p[3],
      }
    : { view: "chat" };
}
function newThread(mode: Mode = "Ask"): Thread {
  return {
    id: crypto.randomUUID(),
    title: "New conversation",
    mode,
    view: "chat",
    updated: new Date().toISOString(),
    messages: [],
  };
}
export default function App() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(STORE) || "null");
      if (!Array.isArray(stored) || !stored.length) return seedWorkspaces();
      const seed = seedWorkspaces();
      return stored.map((w: Workspace) => ({
        ...w,
        threads: w.threads.map((t) => ({
          ...t,
          draft:
            t.draft ??
            seed.find((s) => s.id === w.id)?.threads.find((s) => s.id === t.id)
              ?.draft,
        })),
      }));
    } catch {
      return seedWorkspaces();
    }
  });
  const [route, setRoute] = useState(readRoute);
  const [authReturnTo, setAuthReturnTo] = useState(() => {
    try {
      return safeAuthReturn(sessionStorage.getItem("wai-auth-return"));
    } catch {
      return "#home";
    }
  });
  const [notice, setNotice] = useState("");
  const [phonePreview, setPhonePreview] = useState(false);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key !== STORE || !event.newValue) return;
      try {
        const next = JSON.parse(event.newValue) as Workspace[];
        if (Array.isArray(next) && next.length) {
          setWorkspaces((current) =>
            JSON.stringify(current) === event.newValue ? current : next,
          );
        }
      } catch {
        /* Ignore incomplete external storage updates. */
      }
    };
    addEventListener("storage", sync);
    return () => removeEventListener("storage", sync);
  }, []);
  useEffect(() => {
    if (!EMBEDDED_PREVIEW) return;
    parent.postMessage(
      { type: "workspaceai:preview-route", hash: location.hash || "#home" },
      location.origin,
    );
  }, [route]);
  useEffect(() => {
    if (!EMBEDDED_PREVIEW) return;
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== location.origin || event.source !== parent) return;
      if (
        event.data?.type === "workspaceai:preview-location" &&
        /^#(?:home$|workspace\/)/.test(event.data.hash) &&
        event.data.hash !== location.hash
      ) {
        location.hash = event.data.hash;
      }
    };
    const onEscape = (event: KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        !document.querySelector('[role="dialog"], select:open')
      ) {
        parent.postMessage(
          { type: "workspaceai:preview-close" },
          location.origin,
        );
      }
    };
    addEventListener("message", onMessage);
    addEventListener("keydown", onEscape);
    return () => {
      removeEventListener("message", onMessage);
      removeEventListener("keydown", onEscape);
    };
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify(workspaces));
    } catch {
      setNotice(
        "Device storage is full. Recent changes may not survive a refresh.",
      );
    }
  }, [workspaces]);
  useEffect(() => {
    const onHash = (event: HashChangeEvent) => {
      const next = readRoute();
      const previousHash = new URL(event.oldURL).hash;
      if (next.auth && !readRoute(previousHash).auth) {
        const target = safeAuthReturn(previousHash);
        setAuthReturnTo(target);
        try {
          sessionStorage.setItem("wai-auth-return", target);
        } catch {
          /* The in-memory return route remains available. */
        }
        setPhonePreview(false);
        setNotice("");
      }
      setRoute(next);
    };
    addEventListener("hashchange", onHash);
    return () => removeEventListener("hashchange", onHash);
  }, []);
  useEffect(() => {
    if (notice) {
      const t = setTimeout(() => setNotice(""), 4800);
      return () => clearTimeout(t);
    }
  }, [notice]);
  const goHome = () => {
    location.hash = "home";
    setRoute({ view: "chat" });
  };
  const open = (id: string, threadId?: string, view?: View) => {
    const w = workspaces.find((x) => x.id === id);
    if (!w) return;
    let t = threadId ? w.threads.find((x) => x.id === threadId) : w.threads[0];
    if (!t) {
      t = newThread();
      const fresh = t;
      setWorkspaces((ws) =>
        ws.map((x) =>
          x.id === id ? { ...x, threads: [fresh, ...x.threads] } : x,
        ),
      );
    }
    const next = { workspace: id, thread: t.id, view: view ?? t.view };
    setRoute(next);
    location.hash = `workspace/${id}/${next.view}/${t.id}`;
    setWorkspaces((ws) =>
      ws.map((x) =>
        x.id === id
          ? {
              ...x,
              draft: t!.draft ?? x.draft,
              sources:
                threadId && !view && (t!.handoff || t!.messages.length)
                  ? x.sources.map((s) => ({
                      ...s,
                      selected:
                        (
                          t!.handoff?.sourceIds ??
                          t!.messages.at(-1)?.sourceIds ??
                          []
                        ).includes(s.id) && s.status === "Processed",
                    }))
                  : x.sources,
              threads: x.threads.map((a) =>
                a.id === t!.id ? { ...a, view: next.view } : a,
              ),
            }
          : x,
      ),
    );
  };
  const create = (name: string, description: string) => {
    const w = emptyWorkspace(name, description),
      t = newThread();
    w.threads = [t];
    setWorkspaces((ws) => [...ws, w]);
    const next = { workspace: w.id, thread: t.id, view: "chat" as View };
    setRoute(next);
    location.hash = `workspace/${w.id}/chat/${t.id}`;
  };
  const updateThread = (wid: string, tid: string, title: string | null) =>
    setWorkspaces((ws) =>
      ws.map((w) =>
        w.id === wid
          ? {
              ...w,
              threads:
                title === null
                  ? w.threads.filter((t) => t.id !== tid)
                  : w.threads.map((t) => (t.id === tid ? { ...t, title } : t)),
            }
          : w,
      ),
    );
  const contentRoute = route.auth ? readRoute(authReturnTo) : route;
  const workspace = workspaces.find((w) => w.id === contentRoute.workspace);
  const thread =
    workspace?.threads.find((t) => t.id === contentRoute.thread) ??
    workspace?.threads[0];
  const openAuth = (mode: AuthMode) => {
    if (!route.auth) {
      const target = safeAuthReturn(location.hash);
      setAuthReturnTo(target);
      try {
        sessionStorage.setItem("wai-auth-return", target);
      } catch {
        /* Navigation still works without browser storage. */
      }
    }
    setPhonePreview(false);
    setNotice("");
    location.hash = AUTH_PATHS[mode];
    setRoute({ view: "chat", auth: mode });
  };
  const leaveAuth = () => {
    location.hash = safeAuthReturn(authReturnTo);
    setRoute(readRoute());
  };
  return (
    <>
      {route.auth && (
        <Auth
          mode={route.auth}
          onModeChange={openAuth}
          onClose={leaveAuth}
          onHome={goHome}
          onPreview={() => {
            leaveAuth();
            setNotice(
              "You’re exploring the demo workspace without signing in.",
            );
          }}
        />
      )}
      <div
        className="application-shell"
        hidden={!!route.auth}
        inert={!!route.auth}
      >
        <a
          className="skip-link"
          href="#main-content"
          onClick={(e) => {
            e.preventDefault();
            const main = document.querySelector<HTMLElement>("#main-content");
            main?.setAttribute("tabindex", "-1");
            main?.focus();
          }}
        >
          Skip to main content
        </a>
        {!route.auth && (
          <header className="app-header">
            <div className="header-left">
              <Brand onClick={goHome} />
              <span className="header-divider" />
              <button
                className={`header-home ${!workspace ? "active" : ""}`}
                onClick={goHome}
              >
                <HomeIcon size={15} />
                Home
              </button>
              {workspace && (
                <>
                  <span className="header-slash">/</span>
                  <span className="header-workspace">{workspace.name}</span>
                </>
              )}
            </div>
            <div className="header-right">
              <div className="toolbar-tool theme-tool">
                <span className="tool-label">Theme</span>
                <ThemeControl />
              </div>
              {!EMBEDDED_PREVIEW && (
                <DeviceControl
                  phone={phonePreview}
                  onPhone={() => setPhonePreview(true)}
                  onDesktop={() => setPhonePreview(false)}
                />
              )}
              <span className="preview-label">Local preview</span>
              <button
                className="button header-sign-in"
                aria-label="Sign in"
                title="Sign in"
                onClick={() => openAuth("signin")}
              >
                <LogIn size={16} />
                <span>Sign in</span>
              </button>
            </div>
          </header>
        )}
        {!contentRoute.workspace ? (
          <Home
            workspaces={workspaces}
            open={open}
            create={create}
            updateThread={updateThread}
          />
        ) : workspace && thread ? (
          <WorkspaceScreen
            key={workspace.id}
            workspace={workspace}
            workspaces={workspaces}
            thread={thread}
            view={contentRoute.view}
            active={!route.auth}
            open={open}
            goHome={goHome}
            notify={setNotice}
            update={(fn) =>
              setWorkspaces((ws) =>
                ws.map((w) =>
                  w.id === workspace.id
                    ? { ...fn(w), updated: new Date().toISOString() }
                    : w,
                ),
              )
            }
          />
        ) : (
          <main className="not-found" id="main-content">
            <h1>That workspace is no longer here.</h1>
            <button className="button" onClick={goHome}>
              Back to Home
            </button>
          </main>
        )}
        {notice && (
          <div className="toast" role="status">
            <Check size={16} />
            <span>{notice}</span>
            <button
              className="icon-button"
              aria-label="Dismiss notification"
              onClick={() => setNotice("")}
            >
              <X size={15} />
            </button>
          </div>
        )}
        {phonePreview && !EMBEDDED_PREVIEW && (
          <DevicePreview
            hash={location.hash}
            onClose={() => setPhonePreview(false)}
          />
        )}
      </div>
    </>
  );
}
function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const media = matchMedia(query);
    const sync = () => setMatches(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, [query]);
  return matches;
}

function WorkspaceScreen({
  workspace,
  workspaces,
  thread,
  view,
  open,
  goHome,
  update,
  notify,
  active,
}: {
  workspace: Workspace;
  workspaces: Workspace[];
  thread: Thread;
  view: View;
  open: (w: string, t?: string, v?: View) => void;
  goHome: () => void;
  update: (fn: (w: Workspace) => Workspace) => void;
  notify: (s: string) => void;
  active: boolean;
}) {
  const [navOpen, setNavOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [navCollapsed, setNavCollapsed] = useState(
    () => localStorage.getItem("wai-navigation-collapsed") === "true",
  );
  const [sourcesCollapsed, setSourcesCollapsed] = useState(
    () => localStorage.getItem("wai-sources-collapsed") === "true",
  );
  const wideNavigation = useMediaQuery("(min-width: 1001px)");
  const wideSources = useMediaQuery("(min-width: 1251px)");
  const navExpandRef = useRef<HTMLButtonElement>(null);
  const sourcesExpandRef = useRef<HTMLButtonElement>(null);
  const sourcesVisible = wideSources ? !sourcesCollapsed : filesOpen;
  const sourceCount = workspace.sources.filter(
    (source) => source.selected && source.status === "Processed",
  ).length;
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [threadSearch, setThreadSearch] = useState("");
  const [taskTab, setTaskTab] = useState("board");
  const [savedOpen, setSavedOpen] = useState(false);
  useEffect(() => {
    localStorage.setItem("wai-navigation-collapsed", String(navCollapsed));
    localStorage.setItem("wai-sources-collapsed", String(sourcesCollapsed));
  }, [navCollapsed, sourcesCollapsed]);
  useEffect(() => {
    if (wideNavigation) setNavOpen(false);
  }, [wideNavigation]);
  useEffect(() => {
    if (wideSources) setFilesOpen(false);
  }, [wideSources]);
  useEffect(() => {
    if (!active) {
      setNavOpen(false);
      setFilesOpen(false);
    }
  }, [active]);
  usePanelFocus(
    navOpen && !wideNavigation && active,
    ".workspace-sidebar",
    1000,
    () => setNavOpen(false),
  );
  usePanelFocus(
    filesOpen && !wideSources && active,
    ".repository-panel",
    1250,
    () => setFilesOpen(false),
  );
  const openNavigation = () => {
    if (wideNavigation) {
      setNavCollapsed(false);
      requestAnimationFrame(() =>
        document.querySelector<HTMLButtonElement>(".close-nav")?.focus(),
      );
    } else {
      setFilesOpen(false);
      setNavOpen(true);
    }
  };
  const closeNavigation = () => {
    setNavOpen(false);
    if (wideNavigation) {
      setNavCollapsed(true);
      requestAnimationFrame(() => navExpandRef.current?.focus());
    }
  };
  const openSources = () => {
    if (wideSources) {
      setSourcesCollapsed(false);
      requestAnimationFrame(() =>
        document.querySelector<HTMLButtonElement>(".collapse-sources")?.focus(),
      );
    } else {
      setNavOpen(false);
      setFilesOpen(true);
    }
  };
  const closeSources = () => {
    setFilesOpen(false);
    if (wideSources) {
      setSourcesCollapsed(true);
      requestAnimationFrame(() => sourcesExpandRef.current?.focus());
    }
  };
  const entry = evidenceId ? workspace.evidence[evidenceId] : null;
  const setTasks: Dispatch<SetStateAction<Task[]>> = (action) =>
    update((w) => ({
      ...w,
      tasks: typeof action === "function" ? action(w.tasks) : action,
    }));
  const setSuggestions: Dispatch<SetStateAction<Suggestion[]>> = (action) =>
    update((w) => ({
      ...w,
      suggestions:
        typeof action === "function" ? action(w.suggestions) : action,
    }));
  const openView = (v: View) => {
    if (v === "tasks" && thread.mode === "Tasks") setTaskTab("review");
    open(workspace.id, thread.id, v);
    setNavOpen(false);
  };
  const startNew = () => {
    const t = newThread();
    update((w) => ({ ...w, threads: [t, ...w.threads] }));
    location.hash = `workspace/${workspace.id}/chat/${t.id}`;
    setNavOpen(false);
  };
  const handoff = (mode: Mode, context: Handoff) => {
    const t = newThread(mode);
    const request =
      mode === "Tasks"
        ? "Break this answer down into tasks."
        : "Draft an email from this answer.";
    t.handoff = context;
    t.title = `${mode}: ${context.question.slice(0, 60)}`;
    t.messages = [
      {
        id: crypto.randomUUID(),
        request,
        mode,
        state: mode === "Tasks" ? "suggestions" : "draft",
        sourceIds: context.sourceIds,
        evidenceIds: context.evidenceIds,
        at: t.updated,
      },
    ];
    update((w) => {
      const next = {
        ...w,
        updated: t.updated,
        threads: [t, ...w.threads],
        sources: w.sources.map((s) => ({
          ...s,
          selected:
            context.sourceIds.includes(s.id) && s.status === "Processed",
        })),
      };
      if (mode === "Tasks") {
        next.suggestions = [
          ...w.suggestions,
          ...context.evidenceIds.map((id) => ({
            id: crypto.randomUUID(),
            title: `Review ${w.evidence[id].title.toLowerCase()}`,
            description: w.evidence[id].finding,
            owner: "",
            due: "",
            selected: true,
            source: id,
            threadId: t.id,
          })),
        ];
      } else {
        next.draft = {
          ...blankDraft(),
          to: context.evidenceIds.includes("cc") ? initialEmail.to : "",
          cc: context.evidenceIds.includes("cc") ? initialEmail.cc : "",
          subject: `[${w.name}] Clarification request`,
          body: `Dear recipient,\n\n${context.answer}\n\nCould you please clarify the next steps?\n\nThank you for your guidance.\n\nBest regards,\nPhạm Gia Khiêm`,
          evidenceIds: context.evidenceIds,
          context: context.question,
        };
        t.draft = next.draft;
      }
      return next;
    });
    location.hash = `workspace/${workspace.id}/chat/${t.id}`;
  };
  const requestTasks = (request: string) => {
    const t = newThread("Tasks");
    t.title = request.slice(0, 70);
    t.messages = [
      {
        id: crypto.randomUUID(),
        request,
        mode: "Tasks",
        state: "suggestions",
        sourceIds: [],
        evidenceIds: [],
        at: t.updated,
      },
    ];
    update((w) => ({
      ...w,
      threads: [t, ...w.threads],
      suggestions: [
        ...w.suggestions,
        {
          id: crypto.randomUUID(),
          title: request,
          description:
            "Requested directly by you. Review the scope and fill in missing details.",
          owner: "",
          due: "",
          selected: true,
          threadId: t.id,
        },
      ],
    }));
    notify("Suggestion saved to this workspace’s conversation history.");
  };
  const saved = workspace.threads.flatMap((t) =>
    t.messages.filter((m) => m.saved).map((m) => ({ t, m })),
  );
  return (
    <EvidenceContext.Provider value={workspace.evidence}>
      <div
        className={`workspace-layout ${filesOpen ? "files-open" : ""} ${navCollapsed ? "navigation-collapsed" : ""} ${sourcesCollapsed ? "sources-collapsed" : ""}`}
      >
        <aside className="navigation-rail" aria-label="Collapsed conversations">
          <button
            ref={navExpandRef}
            className="icon-button"
            aria-label="Expand conversations"
            title="Expand conversations"
            aria-expanded="false"
            aria-controls="workspace-navigation"
            onClick={openNavigation}
          >
            <PanelLeftOpen size={19} />
          </button>
          <button
            className="icon-button"
            aria-label="All workspaces"
            title="All workspaces"
            onClick={goHome}
          >
            <HomeIcon size={18} />
          </button>
          <button
            className="icon-button"
            aria-label="New conversation"
            title="New conversation"
            onClick={startNew}
          >
            <Plus size={19} />
          </button>
        </aside>
        <aside
          id="workspace-navigation"
          className={`workspace-sidebar ${navOpen ? "mobile-open" : ""}`}
          aria-label="Workspace navigation"
        >
          <div className="sidebar-top">
            <button className="back-home" onClick={goHome}>
              <ArrowLeft size={15} />
              All workspaces
            </button>
            <button
              className="icon-button close-nav"
              onClick={closeNavigation}
              aria-label={
                wideNavigation ? "Collapse conversations" : "Close navigation"
              }
              title={
                wideNavigation ? "Collapse conversations" : "Close navigation"
              }
              aria-expanded="true"
              aria-controls="workspace-navigation"
            >
              <PanelLeftClose size={18} />
            </button>
          </div>
          <label className="workspace-switcher">
            <span>Current workspace</span>
            <select
              aria-label="Switch workspace"
              value={workspace.id}
              onChange={(e) => open(e.target.value)}
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  {w.name}
                </option>
              ))}
            </select>
          </label>
          <button className="button new-chat" onClick={startNew}>
            <Plus size={16} />
            New conversation
          </button>
          <div className="sidebar-label">
            <span>Conversations</span>
            <span>{workspace.threads.length}</span>
          </div>
          <label className="thread-search">
            <Search size={14} />
            <input
              aria-label="Search workspace conversations"
              placeholder="Find a conversation"
              value={threadSearch}
              onChange={(e) => setThreadSearch(e.target.value)}
            />
          </label>
          <div className="thread-list">
            {workspace.threads
              .filter((t) =>
                t.title.toLowerCase().includes(threadSearch.toLowerCase()),
              )
              .map((t) => {
                const Icon =
                  t.mode === "Tasks"
                    ? Columns3
                    : t.mode === "Email"
                      ? Mail
                      : MessageSquare;
                return (
                  <button
                    className={`thread-item ${thread.id === t.id ? "active" : ""}`}
                    title={t.title}
                    key={t.id}
                    onClick={() => {
                      open(workspace.id, t.id);
                      setNavOpen(false);
                    }}
                  >
                    <Icon size={15} />
                    <span>{t.title}</span>
                  </button>
                );
              })}
          </div>
          <button className="saved-link" onClick={() => setSavedOpen(true)}>
            <ShieldCheck size={15} />
            Saved answers<span>{saved.length}</span>
          </button>
          <div className="sidebar-bottom">
            <div className="member-avatars">
              {workspace.members.slice(0, 4).map((m, i) => (
                <span className={`avatar member-${i}`} key={m} title={m}>
                  {m
                    .split(" ")
                    .slice(-2)
                    .map((x) => x[0])
                    .join("")}
                </span>
              ))}
            </div>
            <span>
              {workspace.members.length}{" "}
              {workspace.members.length === 1 ? "member" : "members"} · Private
              workspace
            </span>
            <p>
              One place for your evidence.
              <br />
              Every decision stays yours.
            </p>
          </div>
        </aside>
        {navOpen && (
          <button
            className="drawer-scrim"
            aria-label="Close navigation"
            onClick={() => setNavOpen(false)}
          />
        )}
        <main className="workspace-main" id="main-content">
          <header className="workspace-heading">
            <div className="workspace-heading-top">
              <button
                className="icon-button menu-toggle"
                aria-label="Open navigation"
                aria-controls="workspace-navigation"
                aria-expanded={navOpen}
                onClick={openNavigation}
              >
                <Menu size={19} />
              </button>
              <div>
                <h1>{workspace.name}</h1>
                <p>
                  {workspace.description ||
                    "A fresh space for your sources and ideas."}
                </p>
              </div>
              <button
                className="button files-toggle"
                aria-expanded={sourcesVisible}
                aria-controls="workspace-sources"
                onClick={() =>
                  sourcesVisible ? closeSources() : openSources()
                }
              >
                <Files size={15} />
                Sources{" "}
                <span>
                  {sourceCount}/{workspace.sources.length}
                </span>
              </button>
            </div>
            <div className="workspace-viewbar">
              <div className="segmented-nav" aria-label="Workspace views">
                {(
                  [
                    { v: "chat", label: "Chat", icon: MessageSquare },
                    { v: "tasks", label: "Tasks", icon: Columns3 },
                    { v: "email", label: "Email", icon: Mail },
                  ] as const
                ).map(({ v, label, icon: Icon }) => (
                  <button
                    key={v}
                    className={view === v ? "active" : ""}
                    aria-current={view === v ? "page" : undefined}
                    onClick={() => openView(v)}
                  >
                    <Icon size={14} />
                    {label}
                  </button>
                ))}
              </div>
              <span className="small muted current-thread">{thread.title}</span>
            </div>
          </header>
          <div className="workspace-content">
            <div hidden={view !== "chat"} className="view-pane chat-pane">
              <Chat
                key={thread.id}
                workspace={workspace}
                thread={thread}
                update={update}
                onEvidence={setEvidenceId}
                onHandoff={handoff}
                onView={openView}
                onFiles={openSources}
              />
            </div>
            <div hidden={view !== "tasks"} className="view-pane working-pane">
              <Tasks
                key={`${workspace.id}-${taskTab}`}
                tasks={workspace.tasks}
                setTasks={setTasks}
                suggestions={workspace.suggestions}
                setSuggestions={setSuggestions}
                members={workspace.members}
                onRequest={requestTasks}
                onEvidence={setEvidenceId}
                notify={notify}
                initialTab={taskTab}
              />
            </div>
            <div hidden={view !== "email"} className="view-pane working-pane">
              <Email
                draft={workspace.draft}
                onChange={(draft) =>
                  update((w) => ({
                    ...w,
                    draft,
                    threads: w.threads.map((t) =>
                      t.id === thread.id ? { ...t, draft } : t,
                    ),
                  }))
                }
                workspaceId={workspace.id}
                onEvidence={setEvidenceId}
                notify={notify}
              />
            </div>
          </div>
        </main>
        <aside
          id="workspace-sources"
          className={`repository-panel ${filesOpen ? "is-open" : ""}`}
          aria-label="File repository"
        >
          <Sources
            workspace={workspace}
            update={update}
            onClose={closeSources}
            notify={notify}
            isDrawer={!wideSources}
          />
        </aside>
        <aside className="sources-rail" aria-label="Collapsed sources">
          <button
            ref={sourcesExpandRef}
            className="icon-button"
            aria-label="Expand sources"
            title="Expand sources"
            aria-expanded="false"
            aria-controls="workspace-sources"
            onClick={openSources}
          >
            <PanelRightOpen size={19} />
          </button>
          <span
            className="rail-count"
            title={`${sourceCount} sources selected`}
          >
            {sourceCount}
            <span className="sr-only"> sources selected</span>
          </span>
        </aside>
        {filesOpen && (
          <button
            className="files-scrim"
            aria-label="Close file repository"
            onClick={() => setFilesOpen(false)}
          />
        )}
        {entry && (
          <Modal title="Source evidence" onClose={() => setEvidenceId(null)}>
            <div className="evidence-header">
              <FileText size={25} />
              <div>
                <strong>{entry.file}</strong>
                <p>{entry.context}</p>
              </div>
              <Badge>{entry.locator}</Badge>
            </div>
            <Badge tone="document">
              <Check size={11} />
              From document
            </Badge>
            <h3 className="evidence-title">{entry.title}</h3>
            <blockquote>
              <mark>{entry.quote}</mark>
            </blockquote>
            <p className="small muted">Exact passage · {workspace.name}</p>
            <Notice tone="neutral">
              Seed evidence for this local prototype. Uploaded files are not
              parsed or verified.
            </Notice>
          </Modal>
        )}
        {savedOpen && (
          <Modal title="Saved answers" onClose={() => setSavedOpen(false)}>
            {saved.map(({ t, m }) => (
              <button
                className="saved-answer-row"
                key={m.id}
                onClick={() => {
                  open(workspace.id, t.id, "chat");
                  setSavedOpen(false);
                }}
              >
                <MessageSquare size={16} />
                <span>{m.request}</span>
                <ArrowUpRight size={14} />
              </button>
            ))}
            {!saved.length && (
              <p className="muted">Bookmark an answer to keep it here.</p>
            )}
          </Modal>
        )}
      </div>
    </EvidenceContext.Provider>
  );
}
