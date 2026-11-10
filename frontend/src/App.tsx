import { useEffect, useState } from "react";
import { Check, LogIn, X } from "lucide-react";
import {
  type Workspace,
  type Thread,
  type Mode,
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
    createdAt: new Date().toISOString(),
    engineMode: "offline",
    messages: [],
  };
}
export default function App() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>(() => {
    try {
      const stored = JSON.parse(localStorage.getItem(STORE) || "null");
      if (!Array.isArray(stored) || !stored.length)
        return assignWorkspaceColors(
          seedWorkspaces().map((item) =>
            notebookWorkspace(migrateWorkspace(item)),
          ),
        );
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
      return assignWorkspaceColors(
        seedWorkspaces().map((item) =>
          notebookWorkspace(migrateWorkspace(item)),
        ),
      );
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
      if (next.auth && !readRoute(previousHash).auth) {
        const target = safeAuthReturn(previousHash);
        setAuthReturnTo(target);
        try {
          sessionStorage.setItem("wai-auth-return", target);
        } catch {
          /* The in-memory return route remains available. */
        }
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
    const t = w.threads[0];
    if (!t) return;
    const next = {
      workspace: id,
      thread: t.id,
      view: view ?? ("chat" as View),
    };
    setRoute(next);
    location.hash = `workspace/${id}/${next.view}/${t.id}`;
  };
  const create = (name: string, description: string) => {
    const w = emptyWorkspace(name, description),
      t = newThread();
    w.threads = [t];
    w.notebookVersion = 1;
    w.studioResults = [];
    setWorkspaces((ws) => assignWorkspaceColors([...ws, w]));
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
  const startFromHome = (workspaceId: string, prompt = "") => {
    setWorkspaces((items) =>
      items.map((item) =>
        item.id === workspaceId
          ? {
              ...item,
              threads: item.threads.map((thread) => ({
                ...thread,
                composerDraft: prompt,
              })),
            }
          : item,
      ),
    );
    open(workspaceId);
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
        {!contentRoute.workspace ? (
          <Home
            workspaces={workspaces}
            open={open}
            start={startFromHome}
            tools={displayTools}
            create={create}
            updateThread={updateThread}
          />
        ) : workspace && thread ? (
          <NotebookWorkspace
            key={workspace.id}
            workspace={workspace}
            view={contentRoute.view}
            active={!route.auth}
            tools={displayTools}
            onSignIn={() => openAuth("signin")}
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
      </div>
    </>
  );
}
