import {
  memo,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";
import {
  ArrowLeft,
  BookOpen,
  Bookmark,
  ChevronDown,
  Copy,
  Files,
  ListChecks,
  MessageSquare,
  PanelLeftOpen,
  PanelRightOpen,
  Pencil,
  Settings2,
  Share2,
  UserRound,
} from "lucide-react";
import { DialogCancel, Citation, EvidenceContext, Modal } from "./components";
import type { Handoff, View, Workspace } from "./data";
import Chat from "./Chat";
import Sources from "./Sources";
import Studio from "./Studio";
import EmailWorkspace from "./EmailWorkspace";
import { PanelDivider, usePanelWidths } from "./panel-resize";
import DocumentInspector from "./DocumentInspector";
import { useEntrance } from "./useEntrance";
import {
  captureChatOutputs,
  defaultStudioConfig,
  isRetiredThread,
  visibleChatMessages,
  visibleStudioResults,
  type StudioConfig,
} from "./notebook-model";
import { workspaceColor } from "./home-model";
import {
  studyConfig,
  studyEvidence,
  type StudyCitation,
  type StudyConfig,
  type StudyKind,
} from "./study-model";

type Pane = "sources" | "chat" | "studio";
type Rail = Exclude<Pane, "chat">;
type RailExit = {
  frame: CSSProperties;
  direction: "left" | "right";
};
const paneEntranceDuration = 200;
const SourcesPanel = memo(Sources);
const ChatPanel = memo(Chat);
const StudioPanel = memo(Studio);
function useViewport(query: string) {
  const [matches, setMatches] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const media = matchMedia(query);
    const changed = () => setMatches(media.matches);
    media.addEventListener("change", changed);
    return () => media.removeEventListener("change", changed);
  }, [query]);
  return matches;
}

export default function NotebookWorkspace({
  workspace,
  update,
  goHome,
  notify,
  tools,
  onSignIn,
  active,
  fromHome,
  intakeFiles,
  onIntakeComplete,
  autoAsk,
  view,
}: {
  workspace: Workspace;
  update: (fn: (current: Workspace) => Workspace) => void;
  goHome: () => void;
  notify: (message: string) => void;
  tools: ReactNode;
  onSignIn: () => void;
  active: boolean;
  fromHome: boolean;
  intakeFiles?: File[];
  onIntakeComplete: (ready: boolean) => void;
  autoAsk: boolean;
  view: View;
}) {
  const mobile = useViewport("(max-width: 767px)");
  const desktop = useViewport("(min-width: 1200px)");
  // The hash update after opening a workspace must not restart its entrance.
  const [animateEntry] = useState(fromHome);
  const [pane, setPane] = useState<Pane>("chat");
  const [secondary, setSecondary] = useState<"sources" | "studio">("sources");
  const [leftClosed, setLeftClosed] = useState(false);
  const [rightClosed, setRightClosed] = useState(false);
  const [sideHidden, setSideHidden] = useState(false);
  const [dialog, setDialog] = useState<
    "rename" | "share" | "settings" | "notes" | null
  >(null);
  const [name, setName] = useState(workspace.name);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);
  const [launch, setLaunch] = useState<StudioConfig | null>(null);
  const [emailOpen, setEmailOpen] = useState(false);
  const [studyId, setStudyId] = useState<string | null>(null);
  const [studyLaunch, setStudyLaunch] = useState<StudyConfig | null>(null);
  const [studyCitation, setStudyCitation] = useState<StudyCitation | null>(
    null,
  );
  const [expanded, setExpanded] = useState(false);
  const sourcesPanel = useRef<HTMLDivElement>(null);
  const chatPanel = useRef<HTMLElement>(null);
  const studioPanel = useRef<HTMLDivElement>(null);
  const [railExits, setRailExits] = useState<Partial<Record<Rail, RailExit>>>(
    {},
  );
  const sourceExit = railExits.sources;
  const studioExit = railExits.studio;
  const sourcesHidden = mobile
    ? pane !== "sources"
    : !desktop && (sideHidden || secondary !== "sources");
  const studioHidden = mobile
    ? pane !== "studio"
    : !desktop && (sideHidden || secondary !== "studio");
  const study = workspace.studySets?.find(
    (set) => set.id === studyId && set.status === "ready",
  );
  const studyExpanded = !!study && expanded;
  const chatHidden = studyExpanded || (mobile && pane !== "chat");
  const sourcesMotion = desktop || mobile ? "left" : "right";
  useEntrance(sourcesPanel, !sourcesHidden && !(desktop && leftClosed), {
    motion: sourcesMotion,
    revealOnly: true,
    mountMotion: animateEntry ? sourcesMotion : undefined,
    duration: paneEntranceDuration,
  });
  useEntrance(studioPanel, !studioHidden && !(desktop && rightClosed), {
    revision: studyExpanded,
    motion: "right",
    revealOnly: true,
    mountMotion: animateEntry ? "right" : undefined,
    duration: paneEntranceDuration,
  });
  useEntrance(chatPanel, !chatHidden, {
    motion: "fade",
    revealOnly: true,
    mountMotion: animateEntry ? "rise" : undefined,
    duration: paneEntranceDuration,
  });
  const widths = usePanelWidths({
    desktop,
    leftClosed,
    rightClosed,
    expanded: studyExpanded,
    secondary,
  });
  const thread = workspace.threads[0];
  const savedNotes = useMemo(
    () =>
      visibleChatMessages(workspace, thread).filter((message) => message.saved),
    [workspace, thread],
  );
  const commit = useCallback(
    (fn: (current: Workspace) => Workspace) =>
      update((current) => captureChatOutputs(fn(current))),
    [update],
  );
  const clearRailExit = useCallback((rail: Rail) => {
    setRailExits((current) =>
      current[rail] ? { ...current, [rail]: undefined } : current,
    );
  }, []);
  useEffect(() => {
    const preference = matchMedia("(prefers-reduced-motion: reduce)");
    const clear = () => {
      if (preference.matches) setRailExits({});
    };
    preference.addEventListener("change", clear);
    return () => preference.removeEventListener("change", clear);
  }, []);
  const reveal = useCallback(
    (target: Pane) => {
      setPane(target);
      if (
        target === "chat" ||
        (mobile && target === "sources") ||
        (!desktop && target === "sources")
      )
        setExpanded(false);
      if (target !== "chat") {
        clearRailExit(target);
        setSecondary(target);
        setSideHidden(false);
      }
      if (target === "sources") setLeftClosed(false);
      if (target === "studio") setRightClosed(false);
    },
    [mobile, desktop, clearRailExit],
  );
  const revealSources = useCallback(() => reveal("sources"), [reveal]);
  const openEmail = useCallback((id: string) => {
    setResultId(id);
    setEmailOpen(true);
  }, []);
  const openEmailHandoff = useCallback((context: Handoff) => {
    setLaunch({ ...defaultStudioConfig(), goal: context.question });
    setEmailOpen(true);
  }, []);
  const openLatestEmail = useCallback(() => {
    setEmailOpen(true);
    setResultId(visibleStudioResults(workspace)[0]?.id || null);
  }, [workspace]);
  const closePane = useCallback(
    (target: Rail) => {
      const panel = (
        target === "sources" ? sourcesPanel : studioPanel
      ).current?.closest(".nb-panel");
      if (panel && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
        // Keep the old panel over the resized grid while it slides away.
        const { top, left, width, height } = panel.getBoundingClientRect();
        if (width && height) {
          setRailExits((current) => ({
            ...current,
            [target]: {
              frame: { top, left, width, height },
              direction:
                target === "sources" && (desktop || mobile) ? "left" : "right",
            },
          }));
        }
      }
      if (mobile) reveal("chat");
      else if (!desktop) setSideHidden(true);
      else if (target === "sources") setLeftClosed(true);
      else setRightClosed(true);
    },
    [desktop, mobile, reveal],
  );
  const closeSources = useCallback(() => closePane("sources"), [closePane]);
  const closeStudio = useCallback(() => closePane("studio"), [closePane]);
  const clearStudyLaunch = useCallback(() => setStudyLaunch(null), []);
  const toggleStudyExpanded = useCallback(
    () => setExpanded(!studyExpanded),
    [studyExpanded],
  );
  useEffect(() => {
    if (view === "email") {
      setEmailOpen(true);
      setResultId(
        workspace.studioResults?.find((result) => result.kind === "email")
          ?.id || null,
      );
    }
  }, [view]);
  const selectStudy = useCallback(
    (id: string | null) => {
      setStudyId(id);
      if (id) reveal("studio");
      else setExpanded(false);
    },
    [reveal],
  );
  const suggestStudy = useCallback(
    (kind: StudyKind, focus: string) => {
      reveal("studio");
      selectStudy(null);
      setStudyLaunch({
        ...studyConfig(workspace, kind),
        focus: focus.slice(0, 160),
      });
    },
    [reveal, selectStudy, workspace],
  );
  const evidence = studyCitation
    ? studyEvidence(studyCitation)
    : evidenceId
      ? workspace.evidence[evidenceId]
      : undefined;
  const evidenceSource = evidence
    ? workspace.sources.find((source) =>
        studyCitation
          ? source.id === studyCitation.docId
          : (source.id === evidence.id || source.name === evidence.file) &&
            (!evidence.docHash || source.fileHash === evidence.docHash),
      )
    : undefined;
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(
        `${location.origin}${location.pathname}#workspace/${workspace.id}/chat/${thread.id}`,
      );
      notify("Note link copied.");
    } catch {
      notify(
        "Could not copy the link. You can select it and copy it manually.",
      );
    }
  };
  return (
    <EvidenceContext.Provider value={workspace.evidence}>
      <div
        className="notebook"
        data-workspace-color={workspaceColor(workspace)}
      >
        <header className="nb-header">
          <h1 className="sr-only">{workspace.name}</h1>
          <div className="nb-header-title">
            <button
              className="icon-button"
              onClick={goHome}
              aria-label="Back to recent notes"
              title="Back to recent notes"
            >
              <ArrowLeft size={20} />
            </button>
            <BookOpen className="nb-brand-mark" size={22} />
            <button
              className="nb-workspace-name"
              onClick={() => {
                setName(workspace.name);
                setDialog("rename");
              }}
              title="Rename note"
            >
              <span>{workspace.name}</span>
              <Pencil size={14} />
            </button>
          </div>
          <div className="nb-header-actions">
            <button
              className="nb-share-button"
              onClick={() => setDialog("share")}
              aria-label="Share note"
            >
              <Share2 size={17} />
              <span>Share</span>
            </button>
            <button
              className="icon-button"
              onClick={() => setDialog("settings")}
              aria-label="Note settings"
              title="Settings"
            >
              <Settings2 size={19} />
            </button>
            <button
              className="nb-avatar"
              onClick={onSignIn}
              aria-label="Account · Sign in"
              title="Guest · Sign in"
            >
              <UserRound size={19} />
            </button>
          </div>
        </header>
        {!desktop && !mobile && (
          <div className="nb-tablet-tools">
            <div role="group" aria-label="Side panel">
              <button
                aria-pressed={!sideHidden && secondary === "sources"}
                onClick={() => reveal("sources")}
              >
                <Files size={16} />
                Sources
              </button>
              <button
                aria-pressed={!sideHidden && secondary === "studio"}
                onClick={() => reveal("studio")}
              >
                <ListChecks size={16} />
                Studio
              </button>
            </div>
            <span>One conversation per note</span>
          </div>
        )}
        <main
          id="main-content"
          style={widths.style}
          className={`nb-layout ${sideHidden ? "nb-side-hidden" : ""} ${studyExpanded ? "nb-study-expanded" : ""}`}
        >
          <section
            className="nb-panel nb-sources"
            id="nb-pane-sources"
            aria-label="Document sources"
            hidden={sourcesHidden && !sourceExit}
            data-exit-only={sourcesHidden && !!sourceExit}
          >
            {desktop && leftClosed && (
              <button
                className="nb-collapsed"
                onClick={() => reveal("sources")}
                aria-label="Open Sources"
              >
                <PanelLeftOpen size={19} />
                <span>Sources</span>
                <small>{workspace.sources.length}</small>
              </button>
            )}
            <div
              className="nb-panel-content nb-rail-body"
              data-collapsed={desktop && leftClosed}
              data-exiting={sourceExit?.direction}
              style={sourceExit?.frame}
              inert={(desktop && leftClosed) || !!sourceExit}
              onAnimationEnd={(event) => {
                if (event.target === event.currentTarget)
                  clearRailExit("sources");
              }}
            >
              <SourcesPanel
                workspace={workspace}
                update={commit}
                notify={notify}
                isDrawer={false}
                notebook
                onClose={closeSources}
                motionRef={sourcesPanel}
                intakeFiles={intakeFiles}
                onIntakeComplete={onIntakeComplete}
              />
            </div>
          </section>
          {desktop && !leftClosed && (
            <PanelDivider {...widths.handle("sources")} />
          )}
          <section
            className="nb-panel nb-chat"
            ref={chatPanel}
            aria-label="Note conversation"
            hidden={chatHidden}
          >
            <header className="nb-panel-header">
              <h2>Conversation</h2>
              <span className="nb-chat-label">WorkspaceAI</span>
              <button
                className="icon-button study-chat-notes"
                aria-label="Saved replies"
                title="Saved replies"
                onClick={() => setDialog("notes")}
              >
                <Bookmark size={17} />
              </button>
              {!desktop && !mobile && sideHidden && (
                <button
                  className="icon-button"
                  onClick={() => reveal(secondary)}
                  aria-label="Open side panel"
                >
                  <PanelRightOpen size={18} />
                </button>
              )}
            </header>
            <ChatPanel
              notebook
              workspace={workspace}
              thread={thread}
              update={commit}
              onEvidence={setEvidenceId}
              active={active && !studyExpanded && (!mobile || pane === "chat")}
              onFiles={revealSources}
              onStudioOpen={openEmail}
              onStudy={suggestStudy}
              onEmailHandoff={openEmailHandoff}
              onEmailDraft={openLatestEmail}
              autoAsk={autoAsk}
            />
          </section>
          {desktop && !rightClosed && !studyExpanded && (
            <PanelDivider {...widths.handle("studio")} />
          )}
          {!desktop && !mobile && !sideHidden && !studyExpanded && (
            <PanelDivider key={secondary} {...widths.handle(secondary)} />
          )}
          <section
            className="nb-panel nb-studio"
            id="nb-pane-studio"
            aria-label="Studio and result history"
            hidden={studioHidden && !studioExit}
            data-exit-only={studioHidden && !!studioExit}
          >
            {desktop && rightClosed && (
              <button
                className="nb-collapsed"
                onClick={() => reveal("studio")}
                aria-label="Open Studio"
              >
                <PanelRightOpen size={19} />
                <span>Studio</span>
                <small>{workspace.studySets?.length ?? 0}</small>
              </button>
            )}
            <div
              className="nb-panel-content nb-rail-body"
              data-collapsed={desktop && rightClosed}
              data-exiting={studioExit?.direction}
              style={studioExit?.frame}
              inert={(desktop && rightClosed) || !!studioExit}
              onAnimationEnd={(event) => {
                if (event.target === event.currentTarget)
                  clearRailExit("studio");
              }}
            >
              <StudioPanel
                workspace={workspace}
                update={commit}
                selected={study}
                onSelect={selectStudy}
                expanded={studyExpanded}
                onExpand={toggleStudyExpanded}
                launch={studyLaunch}
                clearLaunch={clearStudyLaunch}
                onSource={setStudyCitation}
                onClose={closeStudio}
                motionRef={studioPanel}
              />
            </div>
          </section>
        </main>
        {mobile && (
          <nav className="nb-bottom-tabs" aria-label="Note sections">
            {(
              [
                { id: "sources", label: "Sources", icon: Files },
                { id: "chat", label: "Chat", icon: MessageSquare },
                { id: "studio", label: "Studio", icon: ListChecks },
              ] as const
            ).map((item) => (
              <button
                key={item.id}
                aria-current={pane === item.id ? "page" : undefined}
                onClick={() => reveal(item.id)}
              >
                <item.icon size={20} />
                <span>{item.label}</span>
              </button>
            ))}
          </nav>
        )}
      </div>
      {dialog === "rename" && (
        <Modal title="Rename note" onClose={() => setDialog(null)}>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (name.trim()) {
                update((current) => ({ ...current, name: name.trim() }));
                setDialog(null);
              }
            }}
          >
            <label>
              Note name
              <input
                autoFocus
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <div className="modal-actions">
              <DialogCancel />
              <button className="button primary" disabled={!name.trim()}>
                Save name
              </button>
            </div>
          </form>
        </Modal>
      )}
      {dialog === "share" && (
        <Modal title="Note link" onClose={() => setDialog(null)}>
          <div className="form-stack">
            <p>
              This note is saved on this device. The link reopens it in this
              browser and grants no access to others.
            </p>
            <label>
              Link
              <input
                readOnly
                value={`${location.origin}${location.pathname}#workspace/${workspace.id}/chat/${thread.id}`}
                onFocus={(event) => event.target.select()}
              />
            </label>
            <button className="button primary" onClick={() => void copyLink()}>
              <Copy size={16} />
              Copy link
            </button>
          </div>
        </Modal>
      )}
      {dialog === "settings" && (
        <Modal title="Display settings" onClose={() => setDialog(null)}>
          <div className="nb-settings">
            {tools}
            <p>
              Choose light, dark, or system appearance. The connected server
              processes sources using the current AI settings.
            </p>
            <details>
              <summary>
                Archived conversations <ChevronDown size={14} />
              </summary>
              <p>
                Kept{" "}
                {workspace.legacyThreads?.filter(
                  (thread) => !isRetiredThread(thread),
                ).length || 0}{" "}
                older chats in the archive. Their contents are available in the
                main conversation and Studio history.
              </p>
            </details>
          </div>
        </Modal>
      )}
      {dialog === "notes" && (
        <Modal
          title="Saved replies"
          onClose={() => setDialog(null)}
          deferContent
        >
          <SavedNotes notes={savedNotes} onEvidence={setEvidenceId} />
        </Modal>
      )}
      {emailOpen && (
        <Modal
          title="Draft email"
          onClose={() => {
            setEmailOpen(false);
            setLaunch(null);
          }}
          wide
          deferContent
        >
          <EmailWorkspace
            workspace={workspace}
            update={commit}
            notify={notify}
            onEvidence={setEvidenceId}
            selectedId={resultId}
            onSelect={setResultId}
            launch={launch}
            clearLaunch={() => setLaunch(null)}
          />
        </Modal>
      )}
      {(evidenceId || studyCitation) && (
        <Modal
          title="Source text and citations"
          onClose={() => {
            setEvidenceId(null);
            setStudyCitation(null);
          }}
          wide
          deferContent
        >
          <DocumentInspector
            key={evidenceId || `${studyCitation?.docId}-${studyCitation?.page}`}
            source={evidenceSource}
            evidence={evidence}
            workspaceId={workspace.id}
            studyExcerpt={!!studyCitation}
          />
        </Modal>
      )}
    </EvidenceContext.Provider>
  );
}

function SavedNotes({
  notes,
  onEvidence,
}: {
  notes: Workspace["threads"][number]["messages"];
  onEvidence: (id: string) => void;
}) {
  const evidence = useContext(EvidenceContext);
  return (
    <div className="study-notes">
      {notes.length ? (
        notes.map((message) => (
          <article key={message.id}>
            <strong>{message.request}</strong>
            <p>
              {message.answerText ||
                message.evidenceIds
                  .map((id) => evidence[id]?.finding)
                  .filter(Boolean)
                  .join("\n\n")}
            </p>
            <div className="inline-evidence">
              {message.evidenceIds.map((id) => (
                <Citation key={id} id={id} onOpen={onEvidence} />
              ))}
            </div>
          </article>
        ))
      ) : (
        <p>Save replies from the conversation to revisit them here.</p>
      )}
    </div>
  );
}
