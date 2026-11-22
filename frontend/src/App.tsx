import { useEffect, useState } from "react";
import { Check, LogIn, X } from "lucide-react";
import {
  type Workspace,
  type Thread,
  type View,
  seedWorkspaces,
  emptyWorkspace,
} from "./data";
import NotebookWorkspace from "./NotebookWorkspace";
import { notebookWorkspace } from "./notebook-model";
import Home from "./Landing";
import { migrateWorkspace } from "./workflow-model";
import AppTools from "./AppTools";
import { assignWorkspaceColors } from "./home-model";
import Auth, { type AuthMode } from "./Auth";
import { ThemeRuntime } from "./components";
import { sampleStudy } from "./study-sample";
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
type Route = {
  workspace?: string;
  thread?: string;
  view: View;
  auth?: AuthMode;
  fromHome?: boolean;
  fromNote?: boolean;
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
        view: p[2] === "email" ? "email" : "chat",
        thread: p[3],
      }
    : { view: "chat" };
}
function newThread(): Thread {
  return {
    id: crypto.randomUUID(),
    title: "New conversation",
    mode: "Ask",
    view: "chat",
    updated: new Date().toISOString(),
    createdAt: new Date().toISOString(),
    engineMode: "offline",
    messages: [],
  };
}
function initialNotes() {
  const extra = [
    [
      "demo-algorithms",
      "Algorithms and data structures",
      "Search, sorting, and complexity.",
    ],
    ["demo-biology", "Biology revision", "A study space for cell biology."],
    ["demo-writing", "Academic writing", "Plan and revise your next paper."],
  ].map(([id, name, description], index) => {
    const updated = new Date(Date.now() - (index + 2) * 86400000).toISOString();
    const note = {
      ...emptyWorkspace(name, description),
      id,
      updated,
      notebookVersion: 1 as const,
      threads: [
        { ...newThread(), id: `${id}-chat`, updated, createdAt: updated },
      ],
    };
    if (index !== 0) return note;
    const cards = sampleStudy("flashcard");
    const quiz = sampleStudy("quiz");
    return {
      ...note,
      studySets: [
        {
          ...cards,
          mastered: Object.fromEntries(
            cards.items.slice(0, 3).map((item) => [item.id, true]),
          ),
        },
        {
          ...quiz,
          quiz: {
            order: quiz.items.map((item) => item.id),
            answers: Object.fromEntries(
              quiz.items.map((item, position) => [
                item.id,
                position === 0 ? 1 : (item.correctIndex ?? 0),
              ]),
            ),
            complete: true,
          },
          lastScore: { correct: 4, total: 5 },
        },
      ],
    };
  });
  return assignWorkspaceColors([
    ...seedWorkspaces().map((item) =>
      notebookWorkspace(migrateWorkspace(item)),
    ),
    ...extra,
  ]);
}
export default function App() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(STORE) || "null");
      if (!Array.isArray(stored)) return initialNotes();
      if (
        stored.some((w) => !w.schemaVersion) &&
        !localStorage.getItem(`${STORE}-before-schema-v3`)
      ) {
        try {
          localStorage.setItem(
            `${STORE}-before-schema-v3`,
            JSON.stringify(stored),
          );
        } catch {
          /* A full quota must not discard the existing workspace. */
        }
      }
      if (
        stored.some((item: Workspace) => !item.notebookVersion) &&
        !localStorage.getItem(`${STORE}-before-notebook-v1`)
      ) {
        try {
          localStorage.setItem(
            `${STORE}-before-notebook-v1`,
            JSON.stringify(stored),
          );
        } catch {
          /* Each workspace also retains its original sessions. */
        }
      }
      const seed = seedWorkspaces();
      return assignWorkspaceColors(
        stored.map((w: Workspace) =>
          notebookWorkspace(
            migrateWorkspace({
              ...w,
              threads: w.threads.map((t) => ({
                ...t,
                draft:
                  t.draft ??
                  seed
                    .find((s) => s.id === w.id)
                    ?.threads.find((s) => s.id === t.id)?.draft,
              })),
            }),
          ),
        ),
      );
    } catch {
      return initialNotes();
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
  const [intake, setIntake] = useState<{
    id: string;
    files: File[];
    ask: boolean;
  }>();
  useEffect(() => {
    // Fast Refresh can retain pre-migration state without rerunning the initializer.
    if (workspaces.every((item) => item.notebookVersion === 1)) return;
    try {
      if (!localStorage.getItem(`${STORE}-before-notebook-v1`))
        localStorage.setItem(
          `${STORE}-before-notebook-v1`,
          JSON.stringify(workspaces),
        );
    } catch {
      /* Original sessions are also retained in each workspace. */
    }
    setWorkspaces((items) =>
      items.map((item) => notebookWorkspace(item, false)),
    );
  }, [workspaces]);
  useEffect(() => {
    const sync = (event: StorageEvent) => {
      if (event.key !== STORE || !event.newValue) return;
      try {
        const next = assignWorkspaceColors(
          (JSON.parse(event.newValue) as Workspace[]).map((item) =>
            notebookWorkspace(migrateWorkspace(item), false),
          ),
        );
        if (Array.isArray(next)) {
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
    try {
      if (workspaces.some((item) => item.notebookVersion !== 1)) return;
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
      const previous = readRoute(previousHash);
      if (next.auth && !previous.auth) {
        const target = safeAuthReturn(previousHash);
        setAuthReturnTo(target);
        try {
          sessionStorage.setItem("wai-auth-return", target);
        } catch {
          /* The in-memory return route remains available. */
        }
        setNotice("");
      }
      setRoute({
        ...next,
        fromHome: !!next.workspace && !previous.workspace && !previous.auth,
        fromNote: !!previous.workspace && !next.workspace && !next.auth,
      });
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
    setIntake(undefined);
    location.hash = "home";
    setRoute({ view: "chat", fromNote: !!route.workspace });
  };
  const enter = (
    id: string,
    threadId: string,
    prompt = "",
    files: File[] = [],
  ) => {
    setIntake(
      prompt || files.length ? { id, files, ask: !!prompt } : undefined,
    );
    const next = {
      workspace: id,
      thread: threadId,
      view: "chat" as const,
      fromHome: true,
    };
    setRoute(next);
    location.hash = `workspace/${id}/${next.view}/${threadId}`;
  };
  const open = (id: string) => {
    const threadId = workspaces.find((item) => item.id === id)?.threads[0]?.id;
    if (threadId) enter(id, threadId);
  };
  const create = (
    name: string,
    description: string,
    prompt = "",
    files: File[] = [],
  ) => {
    const w = emptyWorkspace(name, description),
      t = newThread();
    w.threads = [t];
    if (prompt) t.composerDraft = prompt;
    w.notebookVersion = 1;
    w.studioResults = [];
    setWorkspaces((ws) => assignWorkspaceColors([...ws, w]));
    enter(w.id, t.id, prompt, files);
  };
  const start = (prompt: string, files: File[], noteId: string) => {
    const note = workspaces.find((item) => item.id === noteId);
    const threadId = note?.threads[0]?.id;
    if (!note || !threadId) {
      const title =
        files[0]?.name.replace(/\.[^.]+$/, "") || prompt || "Untitled note";
      create(
        title.replace(/\s+/g, " ").trim().slice(0, 72) || "Untitled note",
        "",
        prompt,
        files,
      );
      return;
    }
    if (prompt) {
      setWorkspaces((current) =>
        current.map((item) =>
          item.id === noteId
            ? {
                ...item,
                threads: item.threads.map((thread) =>
                  thread.id === threadId
                    ? { ...thread, composerDraft: prompt }
                    : thread,
                ),
              }
            : item,
        ),
      );
    }
    enter(noteId, threadId, prompt, files);
  };
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
    setNotice("");
    location.hash = AUTH_PATHS[mode];
    setRoute({ view: "chat", auth: mode });
  };
  const leaveAuth = () => {
    location.hash = safeAuthReturn(authReturnTo);
    setRoute(readRoute());
  };
  const displayTools = (
    <>
      <AppTools compact={!workspace} />
      <button
        className="button header-sign-in"
        aria-label="Sign in"
        title="Sign in"
        onClick={() => openAuth("signin")}
      >
        <LogIn size={16} />
        <span>Sign in</span>
      </button>
    </>
  );
  return (
    <>
      <ThemeRuntime />
      {route.auth && (
        <Auth
          mode={route.auth}
          onModeChange={openAuth}
          onClose={leaveAuth}
          onHome={goHome}
          onPreview={() => {
            leaveAuth();
            setNotice("You’re exploring the demo without signing in.");
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
        {!contentRoute.workspace ? (
          <Home
            fromNote={contentRoute.fromNote === true}
            workspaces={workspaces}
            open={open}
            create={create}
            start={start}
            rename={(id, name) =>
              setWorkspaces((current) =>
                current.map((item) =>
                  item.id === id
                    ? { ...item, name, updated: new Date().toISOString() }
                    : item,
                ),
              )
            }
            remove={(id) =>
              setWorkspaces((current) =>
                current.filter((item) => item.id !== id),
              )
            }
          />
        ) : workspace && thread ? (
          <NotebookWorkspace
            key={workspace.id}
            workspace={workspace}
            view={contentRoute.view}
            active={!route.auth}
            fromHome={contentRoute.fromHome === true}
            tools={displayTools}
            onSignIn={() => openAuth("signin")}
            goHome={goHome}
            notify={setNotice}
            intakeFiles={intake?.id === workspace.id ? intake.files : undefined}
            autoAsk={
              intake?.id === workspace.id && intake.ask && !intake.files.length
            }
            onIntakeComplete={(ready) =>
              setIntake((current) =>
                current?.id === workspace.id
                  ? { ...current, files: [], ask: current.ask && ready }
                  : current,
              )
            }
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
            <h1>That note is no longer here.</h1>
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
      </div>
    </>
  );
}
