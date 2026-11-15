import { useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Copy,
  Download,
  FileText,
  LoaderCircle,
  Mail,
  Pencil,
  RefreshCw,
  Trash2,
  Bookmark,
} from "lucide-react";
import type { Message, Workspace } from "./data";
import { DialogCancel, Modal, Citation } from "./components";
import ActionMenu from "./ActionMenu";
import { apiFor } from "./api";
import {
  defaultStudioConfig,
  studioText,
  visibleChatMessages,
  visibleStudioResults,
  type StudioConfig,
  type StudioResult,
} from "./notebook-model";
import { generateStudio } from "./studio-service";
import Email from "./Email";

export function downloadStudio(result: StudioResult) {
  const href = URL.createObjectURL(
    new Blob([studioText(result)], { type: "text/plain;charset=utf-8" }),
  );
  const link = document.createElement("a");
  link.href = href;
  link.download = `${result.title.replace(/[\\/:*?"<>|]/g, "-") || "WorkspaceAI"}.txt`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
export default function EmailWorkspace({
  workspace,
  update,
  onEvidence,
  notify,
  selectedId,
  onSelect,
  launch,
  clearLaunch,
}: {
  workspace: Workspace;
  update: (fn: (workspace: Workspace) => Workspace) => void;
  onEvidence: (id: string) => void;
  notify: (text: string) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  launch: StudioConfig | null;
  clearLaunch: () => void;
}) {
  const [config, setConfig] = useState<StudioConfig | null>(null);
  const [renaming, setRenaming] = useState<StudioResult | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [deleting, setDeleting] = useState<StudioResult | null>(null);
  const [emailEditor, setEmailEditor] = useState(false);
  const [tab, setTab] = useState<"results" | "notes">("results");
  const lock = useRef(new Set<string>());
  const settings = config || launch;
  const results = visibleStudioResults(workspace).sort(
    (a, b) => (Date.parse(b.createdAt) || 0) - (Date.parse(a.createdAt) || 0),
  );
  const selected = results.find((result) => result.id === selectedId);
  const thread = workspace.threads[0];
  const notes = thread
    ? visibleChatMessages(workspace, thread).filter((message) => message.saved)
    : [];
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
      notify("Copied.");
    } catch {
      notify(
        "The browser blocked copying. You can select the text and copy it manually.",
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
      options.title.trim() || "Email: " + options.goal.trim().slice(0, 65);
    const pending: StudioResult = {
      id,
      kind: "email",
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
      const patch = await generateStudio(workspace, options);
      update((current) => {
        if (
          !current.studioResults?.some(
            (result) => result.id === id && result.attemptId === attemptId,
          )
        )
          return current;
        const finished = {
          ...pending,
          ...patch,
          status: "ready" as const,
          error: undefined,
          updatedAt: new Date().toISOString(),
        };
        const conversation = current.threads[0];
        const message: Message = {
          id: `studio-${id}`,
          request: `Draft an email: ${options.goal}`,
          mode: "Email",
          state: "draft",
          sourceIds: finished.sourceIds,
          evidenceIds: finished.evidenceIds,
          at,
          studioResultId: id,
          origin: "server",
        };
        return {
          ...current,
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
      notify("Email draft saved.");
    } catch (error) {
      changeResult(id, {
        status: "error",
        error:
          error instanceof Error
            ? error.message
            : "Could not create the result. Try again.",
      });
    } finally {
      lock.current.delete(id);
    }
  };
  const menu = (result: StudioResult) => [
    {
      label: "Rename",
      icon: <Pencil size={15} />,
      run: () => {
        setRenaming(result);
        setNewTitle(result.title);
      },
    },
    {
      label: "Copy",
      icon: <Copy size={15} />,
      disabled: result.status !== "ready",
      run: () => void copy(studioText(result)),
    },
    {
      label: "Download",
      icon: <Download size={15} />,
      disabled: result.status !== "ready",
      run: () => downloadStudio(result),
    },
    {
      label: "Delete result",
      icon: <Trash2 size={15} />,
      danger: true,
      run: () => setDeleting(result),
    },
  ];
  return (
    <>
      <div className="nb-studio-body">
        {!selected ? (
          <>
            <div className="nb-tool-grid">
              <div className="nb-tool-card">
                <button
                  className="nb-tool-main"
                  onClick={() => setConfig(defaultStudioConfig())}
                >
                  <Mail size={20} />
                  <strong>Draft email</strong>
                  <span>Draft an email from selected sources</span>
                </button>
                <button
                  className="icon-button nb-tool-edit"
                  aria-label="Customize email draft"
                  onClick={() => setConfig(defaultStudioConfig())}
                >
                  <Pencil size={14} />
                </button>
              </div>
            </div>
            <div className="nb-studio-section">
              <h3>Your results</h3>
            </div>
            <div
              className="nb-studio-tabs"
              role="tablist"
              aria-label="Studio content"
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
                Results <span>{results.length}</span>
              </button>
              <button
                role="tab"
                aria-selected={tab === "notes"}
                onClick={() => setTab("notes")}
              >
                Saved replies <span>{notes.length}</span>
              </button>
            </div>
            {tab === "results" ? (
              <div className="nb-results" aria-live="polite">
                {results.map((result) => {
                  return (
                    <article
                      className={`nb-result-row is-${result.status}`}
                      key={result.id}
                    >
                      <button
                        className="nb-result-open"
                        onClick={() => {
                          onSelect(result.id);
                        }}
                      >
                        <Mail size={19} />
                        <span>
                          <strong>{result.title}</strong>
                          <small>
                            {result.sourceIds.length}{" "}
                            {result.sourceIds.length === 1
                              ? "source"
                              : "sources"}{" "}
                            ·{" "}
                            {result.createdAt
                              ? new Date(result.createdAt).toLocaleDateString(
                                  "en-US",
                                  {
                                    timeZone: "Asia/Bangkok",
                                    month: "short",
                                    day: "numeric",
                                    hour: "2-digit",
                                    minute: "2-digit",
                                  },
                                )
                              : "Time unknown"}
                          </small>
                        </span>
                      </button>
                      <ActionMenu
                        label={`Options for ${result.title}`}
                        actions={menu(result)}
                      />
                      {result.status === "generating" && (
                        <div className="nb-generating" role="status">
                          <LoaderCircle size={14} />
                          <span>Creating draft…</span>
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
                            Retry
                          </button>
                        </div>
                      )}
                    </article>
                  );
                })}
                {!results.length && (
                  <div className="nb-studio-empty">
                    <FileText size={28} />
                    <h3>Your results will appear here</h3>
                    <p>
                      Choose Draft email to create a draft from your sources.
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
                      Copy
                    </button>
                  </article>
                ))}
                {!notes.length && (
                  <div className="nb-studio-empty">
                    <Bookmark size={26} />
                    <h3>No saved replies yet</h3>
                    <p>Use Save reply under a response in the conversation.</p>
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
                All results
              </button>
              <ActionMenu
                label={`Options for ${selected.title}`}
                actions={menu(selected)}
              />
            </div>
            <h3>{selected.title}</h3>
            <p className="nb-result-meta">
              Email draft · {selected.sourceIds.length}{" "}
              {selected.sourceIds.length === 1 ? "source" : "sources"}
              {selected.origin === "imported" ? " · Imported from history" : ""}
            </p>
            {selected.status === "generating" ? (
              <div className="nb-generating">
                <LoaderCircle size={18} />
                Creating result…
              </div>
            ) : selected.status === "error" ? (
              <div className="nb-result-error">
                <p>{selected.error}</p>
                <button
                  className="button"
                  onClick={() => void run(selected.config, selected)}
                >
                  <RefreshCw size={15} />
                  Retry
                </button>
              </div>
            ) : (
              <>
                <div className="nb-detail-actions">
                  <button onClick={() => void copy(studioText(selected))}>
                    <Copy size={15} />
                    Copy
                  </button>
                  <button onClick={() => downloadStudio(selected)}>
                    <Download size={15} />
                    Export
                  </button>
                  {selected.draft && (
                    <button onClick={() => setEmailEditor(true)}>
                      <Pencil size={15} />
                      Edit
                    </button>
                  )}
                </div>
                <div className="nb-result-content">
                  {selected.draft && (
                    <dl>
                      <dt>Recipient</dt>
                      <dd>{selected.draft.to}</dd>
                      <dt>Subject</dt>
                      <dd>{selected.draft.subject}</dd>
                    </dl>
                  )}
                  <div className="nb-document-text">
                    {selected.draft?.body ?? selected.content}
                  </div>
                </div>
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
                  <strong>Sources used for this draft</strong>
                  {selected.sourceSnapshot.map((source) => (
                    <span key={source.id}>
                      <FileText size={13} />
                      {source.name}
                      {!workspace.sources.some(
                        (current) => current.id === source.id,
                      ) && " · removed from the library"}
                    </span>
                  ))}
                </div>
                {selected.draft ? (
                  <button
                    className="button nb-primary-action"
                    onClick={() => setEmailEditor(true)}
                  >
                    <Mail size={16} />
                    Open the draft to review it before sending
                    <ArrowRight size={15} />
                  </button>
                ) : (
                  <button
                    className="button"
                    onClick={() =>
                      setConfig({
                        ...selected.config,
                        tone:
                          (
                            {
                              "Trang trọng": "Formal",
                              "Thân thiện": "Friendly",
                              "Ngắn gọn, trực tiếp": "Concise and direct",
                            } as Record<string, string>
                          )[selected.config.tone] ?? selected.config.tone,
                        length:
                          (
                            {
                              Ngắn: "Short",
                              "Vừa phải": "Medium",
                              "Chi tiết": "Detailed",
                            } as Record<string, string>
                          )[selected.config.length] ?? selected.config.length,
                      })
                    }
                  >
                    Regenerate draft from sources
                  </button>
                )}
              </>
            )}
          </div>
        )}
      </div>
      {settings && (
        <Modal title="Draft an email" onClose={closeConfig}>
          <form
            className="form-stack nb-tool-form"
            onSubmit={(event) => {
              event.preventDefault();
              if (settings.goal.trim()) void run(settings);
            }}
          >
            <p>
              Using{" "}
              <strong>
                {sources.length} selected{" "}
                {sources.length === 1 ? "source" : "sources"}
              </strong>
              . Review and approve the draft before sending.
            </p>
            <label>
              Result title
              <input
                value={settings.title}
                maxLength={120}
                placeholder="Progress update email"
                onChange={(event) => {
                  clearLaunch();
                  setConfig({ ...settings, title: event.target.value });
                }}
              />
            </label>
            <label>
              What to include
              <textarea
                autoFocus
                required
                rows={3}
                maxLength={1500}
                value={settings.goal}
                placeholder="What is the email about?"
                onChange={(event) => {
                  clearLaunch();
                  setConfig({ ...settings, goal: event.target.value });
                }}
              />
            </label>
            <label>
              Recipient
              <input
                type="email"
                required
                value={settings.recipient}
                placeholder="Enter the recipient's email address"
                onChange={(event) => {
                  clearLaunch();
                  setConfig({ ...settings, recipient: event.target.value });
                }}
              />
            </label>
            <div className="nb-form-row">
              <label>
                Tone
                <select
                  value={settings.tone}
                  onChange={(event) => {
                    clearLaunch();
                    setConfig({ ...settings, tone: event.target.value });
                  }}
                >
                  <option>Formal</option>
                  <option>Friendly</option>
                  <option>Concise and direct</option>
                </select>
              </label>
              <label>
                Length
                <select
                  value={settings.length}
                  onChange={(event) => {
                    clearLaunch();
                    setConfig({ ...settings, length: event.target.value });
                  }}
                >
                  <option>Short</option>
                  <option>Medium</option>
                  <option>Detailed</option>
                </select>
              </label>
            </div>
            {!sources.length && (
              <p className="nb-inline-warning">
                Select at least one ready source in Sources.
              </p>
            )}
            <div className="modal-actions">
              <DialogCancel />
              <button
                className="button primary"
                disabled={
                  !sources.length ||
                  !settings.goal.trim() ||
                  !apiFor(workspace.id)
                }
              >
                <Mail size={16} />
                Create{" "}
              </button>
            </div>
          </form>
        </Modal>
      )}
      {renaming && (
        <Modal title="Rename result" onClose={() => setRenaming(null)}>
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
              Result title
              <input
                autoFocus
                value={newTitle}
                maxLength={120}
                onChange={(event) => setNewTitle(event.target.value)}
              />
            </label>
            <div className="modal-actions">
              <DialogCancel />
              <button className="button primary" disabled={!newTitle.trim()}>
                Save name
              </button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal title="Delete this result?" onClose={() => setDeleting(null)}>
          <p>“{deleting.title}” will be removed from Studio history.</p>
          <div className="modal-actions">
            <DialogCancel />
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
              Delete result
            </button>
          </div>
        </Modal>
      )}
      {emailEditor && selected?.draft && (
        <Modal
          title="Review email draft"
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
