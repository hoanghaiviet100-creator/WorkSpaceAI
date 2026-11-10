import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Clipboard,
  Copy,
  Download,
  FileText,
  ListChecks,
  LoaderCircle,
  Mail,
  PanelRightClose,
  Pencil,
  RefreshCw,
  Trash2,
  Bookmark,
} from "lucide-react";
import type { Message, Workspace } from "./data";
import { Modal, Citation } from "./components";
import ActionMenu from "./ActionMenu";
import { apiFor } from "./api";
import {
  defaultStudioConfig,
  studioText,
  type StudioConfig,
  type StudioKind,
  type StudioResult,
} from "./notebook-model";
import { generateStudio } from "./studio-service";
import Tasks from "./Tasks";
import Email from "./Email";
import { KanbanSummary } from "./Kanban";

// Adding a future tool changes this registry and its generator, not the panel grid.
export const STUDIO_TOOLS = [
  {
    id: "plan" as const,
    title: "Lên kế hoạch",
    description: "Biến nguồn thành việc cần làm",
    icon: ListChecks,
  },
  {
    id: "email" as const,
    title: "Soạn email",
    description: "Tạo bản nháp có ngữ cảnh",
    icon: Mail,
  },
];
export function downloadStudio(result: StudioResult) {
  const href = URL.createObjectURL(
    new Blob([studioText(result)], { type: "text/plain;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = href;
  link.download = `${result.title.replace(/[\\/:*?"<>|]/g, "-") || "WorkspaceAI"}.${result.kind === "plan" ? "md" : "txt"}`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
export default function Studio({
  workspace,
  update,
  onClose,
  onEvidence,
  notify,
  selectedId,
  onSelect,
  launch,
  clearLaunch,
  boardRequest,
  onKanbanOpen,
}: {
  workspace: Workspace;
  update: (fn: (workspace: Workspace) => Workspace) => void;
  onClose: () => void;
  onEvidence: (id: string) => void;
  notify: (text: string) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  launch: StudioConfig | null;
  clearLaunch: () => void;
  boardRequest?: { tab: string; id: number } | null;
  onKanbanOpen: () => void;
}) {
  const [config, setConfig] = useState<StudioConfig | null>(null);
  const [renaming, setRenaming] = useState<StudioResult | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [deleting, setDeleting] = useState<StudioResult | null>(null);
  const [board, setBoard] = useState<string | null>(null);
  useEffect(() => {
    if (boardRequest) setBoard(boardRequest.tab);
  }, [boardRequest?.id]);
  const [emailEditor, setEmailEditor] = useState(false);
  const [editingText, setEditingText] = useState(false);
  const [tab, setTab] = useState<"results" | "notes">("results");
  const lock = useRef(new Set<string>());
  const settings = config || launch;
  const results = [...(workspace.studioResults || [])].sort(
    (a, b) => (Date.parse(b.createdAt) || 0) - (Date.parse(a.createdAt) || 0),
  );
  const selected = results.find((result) => result.id === selectedId);
  const notes =
    workspace.threads[0]?.messages.filter((message) => message.saved) || [];
  const sources = workspace.sources.filter(
    (source) =>
      source.selected &&
      source.status === "Processed" &&
      (!apiFor(workspace.id) || source.origin === "server"),
  );
  const closeConfig = () => {
    setConfig(null);
    clearLaunch();
  };
  const changeResult = (id: string, patch: Partial<StudioResult>) =>
    update((current) => ({
      ...current,
      studioResults: current.studioResults?.map((result) =>
        result.id === id
          ? { ...result, ...patch, updatedAt: new Date().toISOString() }
          : result,
      ),
    }));
  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      notify("Đã sao chép.");
    } catch {
      notify(
        "Trình duyệt chưa cho phép sao chép. Bạn có thể chọn và sao chép nội dung.",
      );
    }
  };
  const run = async (options: StudioConfig, retry?: StudioResult) => {
    const id = retry?.id || crypto.randomUUID();
    if (lock.current.has(id)) return;
    lock.current.add(id);
    const at = new Date().toISOString(),
      attemptId = crypto.randomUUID();
    const title =
      options.title.trim() ||
      (options.kind === "plan" ? "Kế hoạch" : "Email") +
        ": " +
        options.goal.trim().slice(0, 65);
    const pending: StudioResult = {
      id,
      kind: options.kind,
      title,
      createdAt: retry?.createdAt || at,
      updatedAt: at,
      status: "generating",
      sourceIds: sources.map((source) => source.id),
      sourceSnapshot: sources.map((source) => ({
        id: source.id,
        name: source.name,
      })),
      evidenceIds: [],
      content: "",
      config: { ...options, title },
      origin: "generated",
      attemptId,
    };
    update((current) => ({
      ...current,
      studioResults: retry
        ? current.studioResults?.map((result) =>
            result.id === id ? pending : result,
          )
        : [pending, ...(current.studioResults || [])],
    }));
    closeConfig();
    onSelect(null);
    setTab("results");
    try {
      const generated = await generateStudio(
        workspace,
        { ...options, title },
        id,
      );
      update((current) => {
        if (
          !current.studioResults?.some(
            (result) => result.id === id && result.attemptId === attemptId,
          )
        )
          return current;
        const finished = {
          ...pending,
          ...generated.patch,
          status: "ready" as const,
          error: undefined,
          updatedAt: new Date().toISOString(),
        };
        const conversation = current.threads[0];
        const message: Message = {
          id: `studio-${id}`,
          request: `${options.kind === "plan" ? "Lên kế hoạch" : "Soạn email"}: ${options.goal}`,
          mode: options.kind === "plan" ? "Tasks" : "Email",
          state: options.kind === "plan" ? "suggestions" : "draft",
          sourceIds: finished.sourceIds,
          evidenceIds: finished.evidenceIds,
          at,
          studioResultId: id,
          origin: "server",
        };
        return {
          ...current,
          evidence: { ...current.evidence, ...generated.evidence },
          suggestions: [
            ...current.suggestions.filter(
              (suggestion) =>
                !retry?.suggestions?.some((old) => old.id === suggestion.id),
            ),
            ...(finished.suggestions || []),
          ],
          studioResults: current.studioResults.map((result) =>
            result.id === id ? finished : result,
          ),
          threads: [
            {
              ...conversation,
              updated: at,
              messages: conversation.messages.some(
                (entry) => entry.studioResultId === id,
              )
                ? conversation.messages
                : [...conversation.messages, message],
            },
          ],
        };
      });
      notify(
        options.kind === "plan"
          ? "Kế hoạch đã được lưu vào Studio."
          : "Bản nháp email đã được lưu. Email chưa được gửi.",
      );
    } catch (error) {
      changeResult(id, {
        status: "error",
        error:
          error instanceof Error
            ? error.message
            : "Chưa tạo được kết quả. Hãy thử lại.",
      });
    } finally {
      lock.current.delete(id);
    }
  };
  const menu = (result: StudioResult) => [
    {
      label: "Đổi tên",
      icon: <Pencil size={15} />,
      run: () => {
        setRenaming(result);
        setNewTitle(result.title);
      },
    },
    {
      label: "Sao chép",
      icon: <Copy size={15} />,
      disabled: result.status !== "ready",
      run: () => void copy(studioText(result)),
    },
    {
      label: "Tải xuống",
      icon: <Download size={15} />,
      disabled: result.status !== "ready",
      run: () => downloadStudio(result),
    },
    {
      label: "Xóa kết quả",
      icon: <Trash2 size={15} />,
      danger: true,
      run: () => setDeleting(result),
    },
  ];
  return (
    <>
      <header className="nb-panel-header">
        <h2>Studio</h2>
        <button
          className="icon-button"
          onClick={onClose}
          aria-label="Thu gọn Studio"
          title="Thu gọn Studio"
        >
          <PanelRightClose size={18} />
        </button>
      </header>
      <div className="nb-studio-body">
        {!selected ? (
          <>
            <div className="nb-tool-grid">
              {STUDIO_TOOLS.map((tool) => (
                <div className="nb-tool-card" key={tool.id}>
                  <button
                    className="nb-tool-main"
                    onClick={() => setConfig(defaultStudioConfig(tool.id))}
                  >
                    <tool.icon size={20} />
                    <strong>{tool.title}</strong>
                    <span>{tool.description}</span>
                  </button>
                  <button
                    className="icon-button nb-tool-edit"
                    aria-label={`Tùy chỉnh ${tool.title.toLowerCase()}`}
                    onClick={() => setConfig(defaultStudioConfig(tool.id))}
                  >
                    <Pencil size={14} />
                  </button>
                </div>
              ))}
            </div>
            <KanbanSummary workspace={workspace} onOpen={onKanbanOpen} />
            <div className="nb-studio-section">
              <h3>Kết quả của bạn</h3>
              <button
                className="nb-text-button"
                onClick={() => setBoard("board")}
              >
                <ListChecks size={14} />
                Bảng công việc
              </button>
            </div>
            <div
              className="nb-studio-tabs"
              role="tablist"
              aria-label="Nội dung Studio"
              onKeyDown={(event) => {
                if (
                  !["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                    event.key,
                  )
                )
                  return;
                event.preventDefault();
                const tabs = [
                  ...event.currentTarget.querySelectorAll<HTMLButtonElement>(
                    '[role="tab"]',
                  ),
                ];
                const position = tabs.indexOf(
                  document.activeElement as HTMLButtonElement,
                );
                const index =
                  event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? tabs.length - 1
                      : (position +
                          (event.key === "ArrowLeft" ? -1 : 1) +
                          tabs.length) %
                        tabs.length;
                tabs[index]?.focus();
                tabs[index]?.click();
              }}
            >
              <button
                role="tab"
                aria-selected={tab === "results"}
                onClick={() => setTab("results")}
              >
                Kết quả <span>{results.length}</span>
              </button>
              <button
                role="tab"
                aria-selected={tab === "notes"}
                onClick={() => setTab("notes")}
              >
                Ghi chú đã lưu <span>{notes.length}</span>
              </button>
            </div>
            {tab === "results" ? (
              <div className="nb-results" aria-live="polite">
                {results.map((result) => {
                  const Icon = result.kind === "plan" ? ListChecks : Mail;
                  return (
                    <article
                      className={`nb-result-row is-${result.status}`}
                      key={result.id}
                    >
                      <button
                        className="nb-result-open"
                        onClick={() => {
                          onSelect(result.id);
                          setEditingText(false);
                        }}
                      >
                        <Icon size={19} />
                        <span>
                          <strong>{result.title}</strong>
                          <small>
                            {result.sourceIds.length} nguồn ·{" "}
                            {result.createdAt
                              ? new Date(result.createdAt).toLocaleDateString(
                                  "vi-VN",
                                  {
                                    timeZone: "Asia/Bangkok",
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  },
                                )
                              : "Chưa rõ thời gian"}
                          </small>
                        </span>
                      </button>
                      <ActionMenu
                        label={`Tùy chọn ${result.title}`}
                        actions={menu(result)}
                      />
                      {result.status === "generating" && (
                        <div className="nb-generating" role="status">
                          <LoaderCircle size={14} />
                          <span>
                            Đang tạo{" "}
                            {result.kind === "plan" ? "kế hoạch" : "bản nháp"}…
                          </span>
                          <span className="nb-progress-line" />
                        </div>
                      )}
                      {result.status === "error" && (
                        <div className="nb-result-error">
                          <p>{result.error}</p>
                          <button
                            onClick={() => void run(result.config, result)}
                            disabled={lock.current.has(result.id)}
                          >
                            <RefreshCw size={14} />
                            Thử lại
                          </button>
                        </div>
                      )}
                    </article>
                  );
                })}
                {!results.length && (
                  <div className="nb-studio-empty">
                    <FileText size={28} />
                    <h3>Kết quả bạn tạo sẽ xuất hiện ở đây</h3>
                    <p>
                      Chọn Lên kế hoạch hoặc Soạn email để bắt đầu từ các nguồn
                      đã chọn.
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="nb-saved-notes">
                {notes.map((message) => (
                  <article key={message.id}>
                    <Bookmark size={17} />
                    <strong>{message.request}</strong>
                    <p>
                      {message.answerText ||
                        message.evidenceIds
                          .map((id) => workspace.evidence[id]?.finding || "")
                          .join("\n\n")}
                    </p>
                    <div>
                      {message.evidenceIds.map((id, index) => (
                        <Citation
                          key={id}
                          id={id}
                          onOpen={onEvidence}
                          number={index + 1}
                        />
                      ))}
                    </div>
                    <button
                      className="nb-text-button"
                      onClick={() =>
                        void copy(
                          message.answerText ||
                            message.evidenceIds
                              .map(
                                (id) => workspace.evidence[id]?.finding || "",
                              )
                              .join("\n\n"),
                        )
                      }
                    >
                      <Copy size={14} />
                      Sao chép
                    </button>
                  </article>
                ))}
                {!notes.length && (
                  <div className="nb-studio-empty">
                    <Bookmark size={26} />
                    <h3>Chưa có ghi chú đã lưu</h3>
                    <p>Dùng nút Lưu ghi chú bên dưới câu trả lời trong chat.</p>
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="nb-result-detail">
            <div className="nb-detail-toolbar">
              <button className="nb-text-button" onClick={() => onSelect(null)}>
                <ArrowLeft size={15} />
                Tất cả kết quả
              </button>
              <ActionMenu
                label={`Tùy chọn ${selected.title}`}
                actions={menu(selected)}
              />
            </div>
            <h3>{selected.title}</h3>
            <p className="nb-result-meta">
              {selected.kind === "plan" ? "Kế hoạch" : "Bản nháp email"} ·{" "}
              {selected.sourceIds.length} nguồn
              {selected.origin === "imported" ? " · Nhập từ lịch sử cũ" : ""}
            </p>
            {selected.status === "generating" ? (
              <div className="nb-generating">
                <LoaderCircle size={18} />
                Đang tạo kết quả…
              </div>
            ) : selected.status === "error" ? (
              <div className="nb-result-error">
                <p>{selected.error}</p>
                <button
                  className="button"
                  onClick={() => void run(selected.config, selected)}
                >
                  <RefreshCw size={15} />
                  Thử lại
                </button>
              </div>
            ) : (
              <>
                <div className="nb-detail-actions">
                  <button onClick={() => void copy(studioText(selected))}>
                    <Copy size={15} />
                    Sao chép
                  </button>
                  <button onClick={() => downloadStudio(selected)}>
                    <Download size={15} />
                    Xuất file
                  </button>
                  <button
                    onClick={() =>
                      selected.kind === "email" && selected.draft
                        ? setEmailEditor(true)
                        : setEditingText(!editingText)
                    }
                  >
                    <Pencil size={15} />
                    Chỉnh sửa
                  </button>
                </div>
                {editingText ? (
                  <label className="nb-edit-content">
                    Nội dung kế hoạch
                    <textarea
                      value={selected.content}
                      onChange={(event) =>
                        changeResult(selected.id, {
                          content: event.target.value,
                        })
                      }
                      rows={15}
                    />
                    <span>
                      Đã lưu trên thiết bị. Các task đã xác nhận được quản lý
                      riêng trong bảng công việc.
                    </span>
                  </label>
                ) : (
                  <div className="nb-result-content">
                    {selected.kind === "email" && selected.draft && (
                      <dl>
                        <dt>Người nhận</dt>
                        <dd>{selected.draft.to}</dd>
                        <dt>Chủ đề</dt>
                        <dd>{selected.draft.subject}</dd>
                      </dl>
                    )}
                    <div className="nb-document-text">
                      {selected.kind === "email" && selected.draft
                        ? selected.draft.body
                        : selected.content}
                    </div>
                  </div>
                )}
                {!!selected.evidenceIds.length && (
                  <div className="nb-result-citations">
                    {selected.evidenceIds.map((id, index) => (
                      <Citation
                        id={id}
                        key={id}
                        number={index + 1}
                        onOpen={onEvidence}
                      />
                    ))}
                  </div>
                )}
                <div className="nb-result-source-list">
                  <strong>Nguồn tại thời điểm tạo</strong>
                  {selected.sourceSnapshot.map((source) => (
                    <span key={source.id}>
                      <FileText size={13} />
                      {source.name}
                      {!workspace.sources.some(
                        (current) => current.id === source.id,
                      ) && " · đã xóa khỏi thư viện"}
                    </span>
                  ))}
                </div>
                {selected.kind === "plan" ? (
                  <button
                    className="button nb-primary-action"
                    onClick={() =>
                      setBoard(
                        selected.suggestions?.length ? "review" : "board",
                      )
                    }
                  >
                    <ListChecks size={16} />
                    {selected.suggestions?.length
                      ? "Xem và xác nhận task"
                      : "Mở bảng công việc"}
                    <ArrowRight size={15} />
                  </button>
                ) : selected.draft ? (
                  <button
                    className="button nb-primary-action"
                    onClick={() => setEmailEditor(true)}
                  >
                    <Mail size={16} />
                    Mở bản nháp và kiểm tra trước khi gửi
                    <ArrowRight size={15} />
                  </button>
                ) : (
                  <button
                    className="button"
                    onClick={() => setConfig(selected.config)}
                  >
                    Tạo lại bản nháp từ nguồn
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </div>
      {settings && (
        <Modal
          title={
            settings.kind === "plan"
              ? "Tạo kế hoạch từ nguồn"
              : "Soạn bản nháp email"
          }
          onClose={closeConfig}
        >
          <form
            className="form-stack nb-tool-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (settings.goal.trim()) void run(settings);
            }}
          >
            <p>
              Đang dùng <strong>{sources.length} nguồn</strong> đã chọn.{" "}
              {settings.kind === "email"
                ? "Tạo bản nháp; email chỉ được gửi sau khi bạn kiểm tra và duyệt."
                : "Các task cần được bạn xác nhận trước khi thêm vào bảng công việc."}
            </p>
            <label>
              Tên kết quả
              <input
                value={settings.title}
                maxLength={120}
                placeholder={
                  settings.kind === "plan"
                    ? "Kế hoạch ôn tập tuần này"
                    : "Email báo cáo tiến độ"
                }
                onChange={(event) => {
                  clearLaunch();
                  setConfig({ ...settings, title: event.target.value });
                }}
              />
            </label>
            <label>
              {settings.kind === "plan" ? "Mục tiêu" : "Nội dung cần trao đổi"}
              <textarea
                autoFocus
                required
                rows={3}
                maxLength={1500}
                value={settings.goal}
                placeholder={
                  settings.kind === "plan"
                    ? "Bạn muốn hoàn thành điều gì?"
                    : "Bạn muốn viết email về việc gì?"
                }
                onChange={(event) => {
                  clearLaunch();
                  setConfig({ ...settings, goal: event.target.value });
                }}
              />
            </label>
            {settings.kind === "plan" ? (
              <div className="nb-form-row">
                <label>
                  Thời gian
                  <input
                    value={settings.timeframe}
                    maxLength={80}
                    onChange={(event) => {
                      clearLaunch();
                      setConfig({ ...settings, timeframe: event.target.value });
                    }}
                  />
                </label>
                <label>
                  Mức chi tiết
                  <select
                    value={settings.detail}
                    onChange={(event) => {
                      clearLaunch();
                      setConfig({
                        ...settings,
                        detail: event.target.value as StudioConfig["detail"],
                      });
                    }}
                  >
                    <option value="concise">Ngắn gọn</option>
                    <option value="standard">Tiêu chuẩn</option>
                    <option value="detailed">Chi tiết</option>
                  </select>
                </label>
              </div>
            ) : (
              <>
                <label>
                  Người nhận
                  <input
                    type="email"
                    required
                    value={settings.recipient}
                    placeholder="Nhập email người nhận"
                    onChange={(event) => {
                      clearLaunch();
                      setConfig({ ...settings, recipient: event.target.value });
                    }}
                  />
                </label>
                <div className="nb-form-row">
                  <label>
                    Giọng điệu
                    <select
                      value={settings.tone}
                      onChange={(event) => {
                        clearLaunch();
                        setConfig({ ...settings, tone: event.target.value });
                      }}
                    >
                      <option>Trang trọng</option>
                      <option>Thân thiện</option>
                      <option>Ngắn gọn, trực tiếp</option>
                    </select>
                  </label>
                  <label>
                    Độ dài
                    <select
                      value={settings.length}
                      onChange={(event) => {
                        clearLaunch();
                        setConfig({ ...settings, length: event.target.value });
                      }}
                    >
                      <option>Ngắn</option>
                      <option>Vừa phải</option>
                      <option>Chi tiết</option>
                    </select>
                  </label>
                </div>
              </>
            )}
            {!sources.length && (
              <p className="nb-inline-warning">
                Chọn ít nhất một nguồn đã sẵn sàng trong cột Nguồn.
              </p>
            )}
            <div className="modal-actions">
              <button type="button" className="button" onClick={closeConfig}>
                Hủy
              </button>
              <button
                className="button primary"
                disabled={
                  !sources.length ||
                  !settings.goal.trim() ||
                  !apiFor(workspace.id)
                }
              >
                {settings.kind === "plan" ? (
                  <ListChecks size={16} />
                ) : (
                  <Mail size={16} />
                )}
                Tạo
              </button>
            </div>
          </form>
        </Modal>
      )}
      {renaming && (
        <Modal title="Đổi tên kết quả" onClose={() => setRenaming(null)}>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (newTitle.trim()) {
                changeResult(renaming.id, { title: newTitle.trim() });
                setRenaming(null);
              }
            }}
          >
            <label>
              Tên kết quả
              <input
                autoFocus
                value={newTitle}
                maxLength={120}
                onChange={(event) => setNewTitle(event.target.value)}
              />
            </label>
            <div className="modal-actions">
              <button
                className="button"
                type="button"
                onClick={() => setRenaming(null)}
              >
                Hủy
              </button>
              <button className="button primary" disabled={!newTitle.trim()}>
                Lưu tên
              </button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal title="Xóa kết quả này?" onClose={() => setDeleting(null)}>
          <p>
            “{deleting.title}” sẽ bị xóa khỏi Studio. Tài liệu và các task đã
            xác nhận vẫn được giữ.
          </p>
          <div className="modal-actions">
            <button className="button" onClick={() => setDeleting(null)}>
              Hủy
            </button>
            <button
              className="button nb-danger"
              onClick={() => {
                update((current) => ({
                  ...current,
                  studioResults: current.studioResults?.filter(
                    (result) => result.id !== deleting.id,
                  ),
                }));
                if (selectedId === deleting.id) onSelect(null);
                setDeleting(null);
              }}
            >
              Xóa kết quả
            </button>
          </div>
        </Modal>
      )}
      {board && (
        <Modal
          title="Kế hoạch và công việc"
          onClose={() => setBoard(null)}
          wide
          className="nb-editor-modal"
        >
          <Tasks
            key={board}
            workspace={workspace}
            updateWorkspace={update}
            tasks={workspace.tasks}
            setTasks={(action) =>
              update((current) => ({
                ...current,
                tasks:
                  typeof action === "function" ? action(current.tasks) : action,
              }))
            }
            suggestions={workspace.suggestions}
            setSuggestions={(action) =>
              update((current) => ({
                ...current,
                suggestions:
                  typeof action === "function"
                    ? action(current.suggestions)
                    : action,
              }))
            }
            members={workspace.members}
            initialTab={board}
            onEvidence={onEvidence}
            notify={notify}
            onRequest={(goal) => {
              setBoard(null);
              setConfig({ ...defaultStudioConfig("plan"), goal });
            }}
          />
        </Modal>
      )}
      {emailEditor && selected?.draft && (
        <Modal
          title="Kiểm tra bản nháp email"
          onClose={() => setEmailEditor(false)}
          wide
          className="nb-editor-modal"
        >
          <Email
            draft={selected.draft}
            sources={workspace.sources}
            workspaceId={workspace.id}
            onEvidence={onEvidence}
            notify={notify}
            onChange={(draft) => {
              changeResult(selected.id, { draft, content: draft.body });
            }}
          />
        </Modal>
      )}
    </>
  );
}
