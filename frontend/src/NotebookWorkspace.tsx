import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  BookOpen,
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
import { EvidenceContext, Modal } from "./components";
import type { View, Workspace } from "./data";
import Chat from "./Chat";
import Sources from "./Sources";
import Studio from "./Studio";
import Kanban from "./Kanban";
import DocumentInspector from "./DocumentInspector";
import {
  captureChatOutputs,
  defaultStudioConfig,
  type StudioConfig,
} from "./notebook-model";
import { workspaceColor } from "./home-model";

type Pane = "sources" | "chat" | "studio";
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
  view,
}: {
  workspace: Workspace;
  update: (fn: (current: Workspace) => Workspace) => void;
  goHome: () => void;
  notify: (message: string) => void;
  tools: ReactNode;
  onSignIn: () => void;
  active: boolean;
  view: View;
}) {
  const mobile = useViewport("(max-width: 767px)");
  const desktop = useViewport("(min-width: 1200px)");
  const [pane, setPane] = useState<Pane>("chat");
  const [secondary, setSecondary] = useState<"sources" | "studio">("sources");
  const [leftClosed, setLeftClosed] = useState(false);
  const [rightClosed, setRightClosed] = useState(false);
  const [sideHidden, setSideHidden] = useState(false);
  const [dialog, setDialog] = useState<"rename" | "share" | "settings" | null>(
    null,
  );
  const [name, setName] = useState(workspace.name);
  const [evidenceId, setEvidenceId] = useState<string | null>(null);
  const [resultId, setResultId] = useState<string | null>(null);
  const [kanbanOpen, setKanbanOpen] = useState(false);
  const [launch, setLaunch] = useState<StudioConfig | null>(null);
  const [boardRequest, setBoardRequest] = useState<{
    tab: string;
    id: number;
  } | null>(null);
  const thread = workspace.threads[0];
  const commit = (fn: (current: Workspace) => Workspace) =>
    update((current) => captureChatOutputs(fn(current)));
  const reveal = (target: Pane) => {
    setPane(target);
    if (target !== "chat") {
      setSecondary(target);
      setSideHidden(false);
    }
    if (target === "sources") setLeftClosed(false);
    if (target === "studio") setRightClosed(false);
  };
  useEffect(() => {
    if (view === "tasks") {
      reveal("studio");
      setBoardRequest({ tab: "board", id: Date.now() });
    }
    if (view === "email") {
      reveal("studio");
      setResultId(
        workspace.studioResults?.find((result) => result.kind === "email")
          ?.id || null,
      );
    }
  }, [view]);
  const evidence = evidenceId ? workspace.evidence[evidenceId] : undefined;
  const evidenceSource = evidence
    ? workspace.sources.find(
        (source) =>
          (source.id === evidence.id || source.name === evidence.file) &&
          (!evidence.docHash || source.fileHash === evidence.docHash),
      )
    : undefined;
  const copyLink = async () => {
    try {
      await navigator.clipboard.writeText(
        `${location.origin}${location.pathname}#workspace/${workspace.id}/chat/${thread.id}`,
      );
      notify("Đã sao chép liên kết workspace trên thiết bị này.");
    } catch {
      notify(
        "Chưa sao chép được. Bạn có thể chọn liên kết và sao chép thủ công.",
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
              aria-label="Về danh sách workspace"
              title="Về danh sách workspace"
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
              title="Đổi tên workspace"
            >
              <span>{workspace.name}</span>
              <Pencil size={14} />
            </button>
          </div>
          <div className="nb-header-actions">
            <button
              className="nb-share-button"
              onClick={() => setDialog("share")}
              aria-label="Chia sẻ workspace"
            >
              <Share2 size={17} />
              <span>Chia sẻ</span>
            </button>
            <button
              className="icon-button"
              onClick={() => setDialog("settings")}
              aria-label="Cài đặt workspace"
              title="Cài đặt"
            >
              <Settings2 size={19} />
            </button>
            <button
              className="nb-avatar"
              onClick={onSignIn}
              aria-label="Tài khoản · đăng nhập"
              title="Khách · Đăng nhập"
            >
              <UserRound size={19} />
            </button>
          </div>
        </header>
        {!desktop && !mobile && (
          <div className="nb-tablet-tools">
            <div role="group" aria-label="Cột bên cạnh hội thoại">
              <button
                aria-pressed={!sideHidden && secondary === "sources"}
                onClick={() => reveal("sources")}
              >
                <Files size={16} />
                Nguồn
              </button>
              <button
                aria-pressed={!sideHidden && secondary === "studio"}
                onClick={() => reveal("studio")}
              >
                <ListChecks size={16} />
                Studio
              </button>
            </div>
            <span>Một hội thoại cho workspace</span>
          </div>
        )}
        <main
          id="main-content"
          className={`nb-layout ${leftClosed ? "nb-left-closed" : ""} ${rightClosed ? "nb-right-closed" : ""} ${sideHidden ? "nb-side-hidden" : ""}`}
        >
          <section
            className="nb-panel nb-sources"
            aria-label="Nguồn tài liệu"
            hidden={
              mobile
                ? pane !== "sources"
                : !desktop && (sideHidden || secondary !== "sources")
            }
          >
            {desktop && leftClosed && (
              <button
                className="nb-collapsed"
                onClick={() => reveal("sources")}
                aria-label="Mở cột Nguồn"
              >
                <PanelLeftOpen size={19} />
                <span>Nguồn</span>
                <small>{workspace.sources.length}</small>
              </button>
            )}
            <div className="nb-panel-content" hidden={desktop && leftClosed}>
              <Sources
                workspace={workspace}
                update={commit}
                notify={notify}
                isDrawer={false}
                notebook
                onClose={() => {
                  if (mobile) setPane("chat");
                  else if (desktop) setLeftClosed(true);
                  else setSideHidden(true);
                }}
              />
            </div>
          </section>
          <section
            className="nb-panel nb-chat"
            aria-label="Hội thoại workspace"
            hidden={mobile && pane !== "chat"}
          >
            <header className="nb-panel-header">
              <h2>Hội thoại</h2>
              <span className="nb-chat-label">WorkspaceAI</span>
              {!desktop && !mobile && sideHidden && (
                <button
                  className="icon-button"
                  onClick={() => reveal(secondary)}
                  aria-label="Mở cột công cụ"
                >
                  <PanelRightOpen size={18} />
                </button>
              )}
            </header>
            <Chat
              notebook
              workspace={workspace}
              thread={thread}
              update={commit}
              onEvidence={setEvidenceId}
              active={active && (!mobile || pane === "chat")}
              onFiles={() => reveal("sources")}
              onStudioOpen={(id) => {
                setResultId(id);
                reveal("studio");
              }}
              onKanbanOpen={() => setKanbanOpen(true)}
              onHandoff={(mode, context) => {
                setLaunch({
                  ...defaultStudioConfig(mode === "Email" ? "email" : "plan"),
                  goal: context.question,
                });
                reveal("studio");
              }}
              onView={(target, tab) => {
                reveal("studio");
                if (target === "tasks")
                  setBoardRequest({ tab: tab || "board", id: Date.now() });
                else
                  setResultId(
                    workspace.studioResults?.find(
                      (result) => result.kind === "email",
                    )?.id || null,
                  );
              }}
            />
          </section>
          <section
            className="nb-panel nb-studio"
            aria-label="Studio và lịch sử kết quả"
            hidden={
              mobile
                ? pane !== "studio"
                : !desktop && (sideHidden || secondary !== "studio")
            }
          >
            {desktop && rightClosed && (
              <button
                className="nb-collapsed"
                onClick={() => reveal("studio")}
                aria-label="Mở cột Studio"
              >
                <PanelRightOpen size={19} />
                <span>Studio</span>
                <small>{workspace.studioResults?.length || 0}</small>
              </button>
            )}
            <div className="nb-panel-content" hidden={desktop && rightClosed}>
              <Studio
                workspace={workspace}
                update={commit}
                notify={notify}
                onEvidence={setEvidenceId}
                selectedId={resultId}
                onSelect={setResultId}
                launch={launch}
                clearLaunch={() => setLaunch(null)}
                boardRequest={boardRequest}
                onKanbanOpen={() => setKanbanOpen(true)}
                onClose={() => {
                  if (mobile) setPane("chat");
                  else if (desktop) setRightClosed(true);
                  else setSideHidden(true);
                }}
              />
            </div>
          </section>
        </main>
        {mobile && (
          <nav className="nb-bottom-tabs" aria-label="Các phần của workspace">
            {(
              [
                { id: "sources", label: "Nguồn", icon: Files },
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
      <Kanban
        workspace={workspace}
        update={commit}
        notify={notify}
        open={kanbanOpen}
        onClose={() => setKanbanOpen(false)}
      />
      {dialog === "rename" && (
        <Modal title="Đổi tên workspace" onClose={() => setDialog(null)}>
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
              Tên workspace
              <input
                autoFocus
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button"
                onClick={() => setDialog(null)}
              >
                Hủy
              </button>
              <button className="button primary" disabled={!name.trim()}>
                Lưu tên
              </button>
            </div>
          </form>
        </Modal>
      )}
      {dialog === "share" && (
        <Modal title="Liên kết workspace" onClose={() => setDialog(null)}>
          <div className="form-stack">
            <p>
              Workspace hiện được lưu trên thiết bị này. Liên kết mở lại đúng
              workspace trong trình duyệt hiện tại; chưa cấp quyền truy cập cho
              người khác.
            </p>
            <label>
              Liên kết
              <input
                readOnly
                value={`${location.origin}${location.pathname}#workspace/${workspace.id}/chat/${thread.id}`}
                onFocus={(event) => event.target.select()}
              />
            </label>
            <button className="button primary" onClick={() => void copyLink()}>
              <Copy size={16} />
              Sao chép liên kết
            </button>
          </div>
        </Modal>
      )}
      {dialog === "settings" && (
        <Modal title="Cài đặt hiển thị" onClose={() => setDialog(null)}>
          <div className="nb-settings">
            {tools}
            <p>
              Chọn giao diện sáng, tối hoặc theo thiết bị. Nguồn được xử lý bởi
              backend đang kết nối; cấu hình AI hiện tại được giữ nguyên.
            </p>
            <details>
              <summary>
                Lịch sử trước khi gộp hội thoại <ChevronDown size={14} />
              </summary>
              <p>
                Đã giữ {workspace.legacyThreads?.length || 0} cuộc chat cũ trong
                bản lưu dữ liệu. Nội dung được đưa vào hội thoại chung và lịch
                sử Studio.
              </p>
            </details>
          </div>
        </Modal>
      )}
      {evidenceId && (
        <Modal
          title="Văn bản nguồn và trích dẫn"
          onClose={() => setEvidenceId(null)}
          wide
        >
          <DocumentInspector
            key={evidenceId}
            source={evidenceSource}
            evidence={evidence}
            workspaceId={workspace.id}
          />
        </Modal>
      )}
    </EvidenceContext.Provider>
  );
}
