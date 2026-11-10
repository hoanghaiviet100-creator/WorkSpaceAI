import { useEffect, useRef, useState } from "react";
import {
  ArrowDownAZ,
  Check,
  FileSpreadsheet,
  FileText,
  FolderOpen,
  Info,
  Link,
  LoaderCircle,
  PanelLeftClose,
  Pencil,
  Plus,
  Presentation,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { Modal, Notice } from "./components";
import type { Source, Workspace } from "./data";
import {
  apiFor,
  deleteDocument,
  importSourceLink,
  listDocuments,
  renameDocument,
  selectDocuments,
  uploadDocument,
} from "./api";
import { sha256, syncWorkspaceLibrary } from "./workflow-model";
import DocumentInspector from "./DocumentInspector";
import ActionMenu from "./ActionMenu";

const ACCEPT = ".pdf,.docx,.pptx,.txt,.md,.csv";
const TYPES = ["PDF", "DOCX", "PPTX", "TXT", "MD", "CSV"];
function FileIcon({ source }: { source: Source }) {
  const kind = source.kind.toLowerCase();
  return kind.includes("ppt") ? (
    <Presentation size={20} />
  ) : kind === "csv" ? (
    <FileSpreadsheet size={20} />
  ) : source.sourceUrl ? (
    <Link size={20} />
  ) : (
    <FileText size={20} />
  );
}
export default function Sources({
  workspace,
  update,
  onClose,
  notify,
}: {
  workspace: Workspace;
  update: (fn: (workspace: Workspace) => Workspace) => void;
  onClose: () => void;
  notify: (message: string) => void;
  isDrawer: boolean;
  notebook?: boolean;
}) {
  const connected = apiFor(workspace.id);
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [alphabetical, setAlphabetical] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [add, setAdd] = useState<"file" | "link" | "text" | null>(null);
  const [title, setTitle] = useState("");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [failure, setFailure] = useState("");
  const [inspect, setInspect] = useState<Source | null>(null);
  const [renaming, setRenaming] = useState<Source | null>(null);
  const [newName, setNewName] = useState("");
  const [deleting, setDeleting] = useState<Source | null>(null);
  const [jobs, setJobs] = useState<
    { id: string; file: File; error?: string; replacement?: Source }[]
  >([]);
  const input = useRef<HTMLInputElement>(null);
  const target = useRef<Source | null>(null);
  const selectAll = useRef<HTMLInputElement>(null);
  const lock = useRef(false);
  const dragDepth = useRef(0);
  const libraryRevision = useRef(0);
  const commit = (fn: (current: Workspace) => Workspace) => {
    libraryRevision.current++;
    update(fn);
  };
  const updateRef = useRef(update);
  updateRef.current = update;
  useEffect(() => {
    if (!connected) return;
    let alive = true;
    const revisionAtRead = libraryRevision.current;
    listDocuments(workspace.id)
      .then((sources) => {
        if (alive && revisionAtRead === libraryRevision.current)
          updateRef.current((current) =>
            syncWorkspaceLibrary(current, sources),
          );
      })
      .catch(() => {
        if (alive)
          setFailure(
            "Chưa đồng bộ được thư viện. Kiểm tra backend và thử lại.",
          );
      });
    return () => {
      alive = false;
    };
  }, [workspace.id, connected]);
  const usable = (source: Source) =>
    source.status === "Processed" && (!connected || source.origin === "server");
  const selected = workspace.sources.filter(
    (source) => source.selected && usable(source),
  );
  const visible = workspace.sources
    .filter(
      (source) =>
        source.name
          .toLocaleLowerCase()
          .includes(search.trim().toLocaleLowerCase()) &&
        (!kind || source.kind.toUpperCase() === kind),
    )
    .sort((a, b) => (alphabetical ? a.name.localeCompare(b.name) : 0));
  const selectable = visible.filter(usable);
  const allSelected =
    !!selectable.length && selectable.every((source) => source.selected);
  useEffect(() => {
    if (selectAll.current)
      selectAll.current.indeterminate =
        !allSelected && selectable.some((source) => source.selected);
  }, [allSelected, selectable]);
  const toggle = async (ids: string[], checked: boolean) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setFailure("");
    try {
      if (
        workspace.sources.some(
          (source) => ids.includes(source.id) && source.origin === "server",
        )
      ) {
        if (!connected)
          throw new Error("Kết nối backend để thay đổi nguồn đang sử dụng.");
        await selectDocuments(
          workspace.sources
            .filter(
              (source) =>
                source.origin === "server" &&
                (ids.includes(source.id) ? checked : source.selected),
            )
            .map((source) => source.id),
          workspace.id,
        );
      }
      commit((current) => ({
        ...current,
        sources: current.sources.map((source) =>
          ids.includes(source.id) ? { ...source, selected: checked } : source,
        ),
      }));
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : "Chưa lưu được lựa chọn nguồn.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const sync = async () => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setFailure("");
    try {
      const sources = await listDocuments(workspace.id);
      commit((current) => syncWorkspaceLibrary(current, sources));
      notify("Đã đồng bộ thư viện nguồn.");
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "Chưa đồng bộ được thư viện.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const ingest = async (file: File, replacement?: Source) => {
    const extension = file.name.split(".").pop()?.toLowerCase() || "";
    if (!TYPES.includes(extension.toUpperCase()))
      throw new Error(
        "Chọn PDF, Word (.docx), slide (.pptx), TXT, MD hoặc CSV.",
      );
    if (!file.size || file.size > 25 * 1024 * 1024)
      throw new Error("File cần có nội dung và không vượt quá 25 MB.");
    if (
      replacement &&
      file.name.toLowerCase() !== replacement.name.toLowerCase()
    )
      throw new Error(
        `Chọn file gốc ${replacement.name}. Dùng Thêm nguồn để tải tài liệu khác.`,
      );
    if (connected) {
      const source = await uploadDocument(file, workspace.id);
      commit((current) =>
        syncWorkspaceLibrary(
          current,
          [
            ...current.sources.filter(
              (old) => old.origin === "server" && old.id !== source.id,
            ),
            source,
          ],
          replacement ? { [replacement.id]: source.id } : {},
        ),
      );
    } else {
      const bytes = await file.arrayBuffer();
      const hash = await sha256(bytes);
      const plain = ["txt", "md", "csv"].includes(extension)
        ? new TextDecoder().decode(bytes)
        : undefined;
      const id = crypto.randomUUID(),
        at = new Date().toISOString();
      const pageHash =
        plain === undefined
          ? undefined
          : await sha256(new TextEncoder().encode(plain));
      const source: Source = {
        id,
        name: file.name,
        kind: extension.toUpperCase(),
        detail: `${Math.ceil(file.size / 1024)} KB`,
        selected: false,
        status: "Preview only",
        origin: "local",
        fileHash: hash,
        fileSizeBytes: file.size,
        uploadedAt: at,
        versionId: "v1",
        totalPages: plain === undefined ? undefined : 1,
        totalLines: plain?.split(/\r?\n/).length,
        limitation:
          "Bản xem trước trên thiết bị. Tải lại lên backend để sử dụng làm nguồn trả lời.",
        pages:
          plain === undefined
            ? undefined
            : [
                {
                  page_id: 1,
                  doc_id: id,
                  page_number: 1,
                  line_count: plain.split(/\r?\n/).length,
                  raw_text: plain,
                  page_hash: pageHash!,
                  created_at: at,
                },
              ],
      };
      commit((current) =>
        current.sources.some((old) => old.fileHash === hash)
          ? current
          : { ...current, sources: [...current.sources, source] },
      );
    }
  };
  const upload = async (files: File[], replacement?: Source) => {
    if (!files.length || lock.current) return;
    lock.current = true;
    setBusy(true);
    setFailure("");
    setAdd(null);
    for (const file of files) {
      const id = crypto.randomUUID();
      setJobs((current) => [...current, { id, file, replacement }]);
      try {
        await ingest(file, replacement);
        setJobs((current) => current.filter((job) => job.id !== id));
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Tải lên chưa thành công.";
        setJobs((current) =>
          current.map((job) =>
            job.id === id ? { ...job, error: message } : job,
          ),
        );
      }
    }
    lock.current = false;
    setBusy(false);
    target.current = null;
    if (input.current) input.current.value = "";
  };
  const importLink = async () => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setFailure("");
    try {
      const source = await importSourceLink(
        url.trim(),
        title.trim(),
        workspace.id,
      );
      commit((current) =>
        syncWorkspaceLibrary(current, [
          ...current.sources.filter(
            (old) => old.origin === "server" && old.id !== source.id,
          ),
          source,
        ]),
      );
      setAdd(null);
      setUrl("");
      setTitle("");
      notify("Đã thêm nội dung từ liên kết.");
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : "Không tải được nội dung từ liên kết.",
      );
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  const rename = async () => {
    if (!renaming || busy || !newName.trim()) return;
    setBusy(true);
    setFailure("");
    try {
      if (renaming.origin === "server")
        await renameDocument(renaming.id, newName.trim(), workspace.id);
      commit((current) => ({
        ...current,
        sources: current.sources.map((source) =>
          source.id === renaming.id
            ? { ...source, name: newName.trim() }
            : source,
        ),
        evidence: Object.fromEntries(
          Object.entries(current.evidence).map(([id, evidence]) => [
            id,
            evidence.file === renaming.name &&
            (!evidence.docHash || evidence.docHash === renaming.fileHash)
              ? { ...evidence, file: newName.trim() }
              : evidence,
          ]),
        ),
      }));
      setRenaming(null);
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "Chưa đổi được tên tài liệu.",
      );
    } finally {
      setBusy(false);
    }
  };
  const remove = async () => {
    if (!deleting || busy) return;
    setBusy(true);
    setFailure("");
    try {
      if (deleting.origin === "server")
        await deleteDocument(deleting.id, workspace.id);
      commit((current) => ({
        ...current,
        sources: current.sources.filter((source) => source.id !== deleting.id),
        requirements: current.requirements?.map((requirement) =>
          requirement.doc_id === deleting.id
            ? { ...requirement, doc_id: null }
            : requirement,
        ),
      }));
      setDeleting(null);
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "Chưa xóa được tài liệu.",
      );
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <header className="nb-panel-header">
        <h2>
          Nguồn <span className="nb-count">{workspace.sources.length}</span>
        </h2>
        <button
          className="icon-button"
          aria-label="Thu gọn Nguồn"
          title="Thu gọn Nguồn"
          onClick={onClose}
        >
          <PanelLeftClose size={18} />
        </button>
      </header>
      <div
        className={`nb-sources-body ${dragging ? "is-dragging" : ""}`}
        onDragEnter={(event) => {
          if (!event.dataTransfer.types.includes("Files")) return;
          event.preventDefault();
          dragDepth.current++;
          setDragging(true);
        }}
        onDragOver={(event) => {
          if (event.dataTransfer.types.includes("Files"))
            event.preventDefault();
        }}
        onDragLeave={() => {
          dragDepth.current--;
          if (dragDepth.current <= 0) {
            dragDepth.current = 0;
            setDragging(false);
          }
        }}
        onDrop={(event) => {
          if (!event.dataTransfer.files.length) return;
          event.preventDefault();
          dragDepth.current = 0;
          setDragging(false);
          void upload(Array.from(event.dataTransfer.files));
        }}
      >
        <button
          className="button nb-add-source"
          disabled={busy}
          onClick={() => {
            target.current = null;
            setFailure("");
            setAdd("file");
          }}
        >
          <Plus size={18} />
          Thêm nguồn
        </button>
        <label className="nb-source-search">
          <Search size={16} />
          <input
            aria-label="Tìm nguồn"
            placeholder="Tìm trong nguồn của bạn"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          {search && (
            <button aria-label="Xóa tìm kiếm" onClick={() => setSearch("")}>
              <X size={14} />
            </button>
          )}
        </label>
        <div className="nb-source-filter">
          <select
            aria-label="Lọc loại nguồn"
            value={kind}
            onChange={(event) => setKind(event.target.value)}
          >
            <option value="">Tất cả loại file</option>
            {TYPES.map((type) => (
              <option key={type}>{type}</option>
            ))}
          </select>
          <button
            className="icon-button"
            aria-label="Sắp xếp nguồn theo tên"
            aria-pressed={alphabetical}
            onClick={() => setAlphabetical(!alphabetical)}
          >
            <ArrowDownAZ size={16} />
          </button>
          {connected && (
            <button
              className="icon-button"
              aria-label="Đồng bộ nguồn"
              disabled={busy}
              onClick={() => void sync()}
            >
              <RefreshCw size={16} />
            </button>
          )}
        </div>
        <div className="nb-source-selection">
          <span>{selected.length} đang dùng</span>
          <label>
            Chọn tất cả
            <input
              ref={selectAll}
              type="checkbox"
              aria-label="Chọn tất cả nguồn"
              checked={allSelected}
              disabled={busy || !selectable.length}
              onChange={(event) =>
                void toggle(
                  selectable.map((source) => source.id),
                  event.target.checked,
                )
              }
            />
          </label>
        </div>
        {failure && (
          <div className="nb-source-error" role="alert">
            {failure}
          </div>
        )}
        <div className="nb-source-list">
          {jobs.map((job) => (
            <div className="nb-upload-job" key={job.id}>
              <Upload size={18} />
              <span>
                <strong>{job.file.name}</strong>
                <small>{job.error || "Đang tải và xử lý…"}</small>
              </span>
              {job.error ? (
                <button
                  className="icon-button"
                  aria-label={`Thử tải lại ${job.file.name}`}
                  disabled={busy}
                  onClick={() => {
                    setJobs((current) =>
                      current.filter((item) => item.id !== job.id),
                    );
                    void upload([job.file], job.replacement);
                  }}
                >
                  <RefreshCw size={16} />
                </button>
              ) : (
                <LoaderCircle size={16} className="nb-spin" />
              )}
            </div>
          ))}
          {visible.map((source) => (
            <div
              className={`nb-source-row ${source.selected && usable(source) ? "is-selected" : ""}`}
              key={source.id}
            >
              <button
                className="nb-source-open"
                title={source.name}
                onClick={() => setInspect(source)}
              >
                <span
                  className={`nb-file-icon kind-${source.kind.toLowerCase()}`}
                >
                  <FileIcon source={source} />
                </span>
                <span>
                  <strong>{source.name}</strong>
                  <small>
                    {source.status === "Processed"
                      ? connected && source.origin !== "server"
                        ? "Cần tải file gốc"
                        : "Sẵn sàng"
                      : source.status === "Processing"
                        ? "Đang xử lý"
                        : source.status === "Unreadable"
                          ? "Không đọc được file"
                          : "Chỉ xem trước"}
                    {source.totalPages
                      ? ` · ${source.totalPages} ${source.kind.toLowerCase() === "pptx" ? "slide" : "trang"}`
                      : ""}
                  </small>
                </span>
              </button>
              <label
                className="nb-source-check"
                title={
                  !usable(source)
                    ? source.limitation ||
                      "Tải file gốc lên backend để dùng nguồn này."
                    : "Bật/tắt nguồn cho câu trả lời"
                }
              >
                <input
                  type="checkbox"
                  aria-label={`Dùng ${source.name}`}
                  checked={source.selected && usable(source)}
                  disabled={busy || !usable(source)}
                  onChange={(event) =>
                    void toggle([source.id], event.target.checked)
                  }
                />
              </label>
              <ActionMenu
                label={`Tùy chọn ${source.name}`}
                actions={[
                  {
                    label: "Xem nguồn",
                    icon: <Info size={15} />,
                    run: () => setInspect(source),
                  },
                  {
                    label: "Đổi tên",
                    icon: <Pencil size={15} />,
                    disabled: busy,
                    run: () => {
                      setFailure("");
                      setNewName(source.name);
                      setRenaming(source);
                    },
                  },
                  {
                    label: "Tải lại file gốc",
                    icon: <RefreshCw size={15} />,
                    disabled: busy,
                    run: () => {
                      target.current = source;
                      setFailure("");
                      setAdd("file");
                    },
                  },
                  {
                    label: "Xóa nguồn",
                    icon: <Trash2 size={15} />,
                    danger: true,
                    disabled: busy,
                    run: () => {
                      setFailure("");
                      setDeleting(source);
                    },
                  },
                ]}
              />
            </div>
          ))}
          {!visible.length && !jobs.length && (
            <div className="nb-sources-empty">
              <div className="nb-empty-illustration">
                <FileText size={32} />
                <span />
                <span />
              </div>
              <h3>
                {workspace.sources.length
                  ? "Không tìm thấy nguồn"
                  : "Tải tài liệu đầu tiên của bạn"}
              </h3>
              <p>
                {workspace.sources.length
                  ? "Thử một tên khác hoặc thay đổi bộ lọc."
                  : "Thả file vào đây, dán liên kết hoặc thêm văn bản để bắt đầu."}
              </p>
            </div>
          )}
        </div>
        <div className="nb-source-footer">
          <span>
            <Check size={13} />
            Chỉ nguồn được chọn mới dùng để trả lời
          </span>
          <span>PDF · Word · Slide · tối đa 25 MB/file</span>
        </div>
        {dragging && (
          <div className="nb-drop-overlay">
            <Upload size={28} />
            <strong>Thả tài liệu để thêm nguồn</strong>
          </div>
        )}
      </div>
      {add && (
        <Modal
          title={
            target.current ? "Tải lại file gốc" : "Thêm nguồn vào workspace"
          }
          onClose={() => {
            if (!busy) {
              target.current = null;
              setAdd(null);
            }
          }}
        >
          <div
            className="nb-import-tabs"
            role="group"
            aria-label="Cách thêm nguồn"
          >
            {(
              [
                { id: "file", label: "Tải file", icon: Upload },
                { id: "link", label: "Liên kết", icon: Link },
                { id: "text", label: "Văn bản", icon: FileText },
              ] as const
            ).map((tab) => (
              <button
                key={tab.id}
                aria-pressed={add === tab.id}
                onClick={() => {
                  setAdd(tab.id);
                  setFailure("");
                }}
                disabled={busy || (!!target.current && tab.id !== "file")}
              >
                <tab.icon size={16} />
                {tab.label}
              </button>
            ))}
          </div>
          {add === "file" ? (
            <div className="nb-import-file">
              <Upload size={32} />
              <h3>Tài liệu của bạn, trong một nơi</h3>
              <p>
                PDF có văn bản, Word (.docx), PowerPoint (.pptx), TXT, MD, CSV.
                Tối đa 25 MB/file.
              </p>
              {target.current && (
                <p>
                  Chọn tệp gốc <strong>{target.current.name}</strong> để khôi
                  phục nguồn này.
                </p>
              )}
              {/* A real file control receives the trusted user gesture inside the dialog.
                  No synthetic click on a hidden input outside the active modal. */}
              <label
                className="button primary nb-native-file-picker"
                data-disabled={busy}
              >
                <span aria-hidden="true">Chọn file từ thiết bị</span>
                <input
                  ref={input}
                  type="file"
                  accept={ACCEPT}
                  multiple={!target.current}
                  disabled={busy}
                  aria-label="Chọn file từ thiết bị"
                  onChange={(event) =>
                    void upload(
                      Array.from(event.target.files || []),
                      target.current || undefined,
                    )
                  }
                />
              </label>
              <p className="small muted">
                Bạn cũng có thể kéo file vào cột Nguồn.
              </p>
            </div>
          ) : (
            <form
              className="form-stack"
              onSubmit={(event) => {
                event.preventDefault();
                if (add === "link") void importLink();
                else if (text.trim()) {
                  const filename = (title.trim() || "Văn bản đã dán").replace(
                    /[<>:"/\\|?*]/g,
                    "-",
                  );
                  void upload([
                    new File([text], `${filename}.txt`, { type: "text/plain" }),
                  ]);
                  setText("");
                  setTitle("");
                }
              }}
            >
              <label>
                Tên nguồn (không bắt buộc)
                <input
                  maxLength={120}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              {add === "link" ? (
                <>
                  <label>
                    Liên kết công khai
                    <input
                      autoFocus
                      type="url"
                      required
                      placeholder="https://…"
                      value={url}
                      onChange={(event) => setUrl(event.target.value)}
                    />
                  </label>
                  <p className="small muted">
                    Tải nội dung trang web hoặc file công khai. Không truy cập
                    trang cần đăng nhập hay liên kết nội bộ. Thao tác này cần
                    Internet.
                  </p>
                </>
              ) : (
                <label>
                  Nội dung
                  <textarea
                    autoFocus
                    required
                    rows={8}
                    maxLength={1000000}
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    placeholder="Dán nội dung tài liệu tại đây…"
                  />
                </label>
              )}
              {failure && <Notice>{failure}</Notice>}
              <div className="modal-actions">
                <button
                  type="button"
                  className="button"
                  onClick={() => setAdd(null)}
                  disabled={busy}
                >
                  Hủy
                </button>
                <button
                  className="button primary"
                  disabled={busy || (add === "link" && !connected)}
                >
                  {busy ? "Đang thêm…" : "Thêm nguồn"}
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}
      {inspect && (
        <Modal title="Chi tiết nguồn" onClose={() => setInspect(null)} wide>
          <DocumentInspector source={inspect} workspaceId={workspace.id} />
        </Modal>
      )}
      {renaming && (
        <Modal title="Đổi tên nguồn" onClose={() => !busy && setRenaming(null)}>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              void rename();
            }}
          >
            <label>
              Tên file
              <input
                autoFocus
                required
                maxLength={180}
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
            </label>
            <p className="small muted">
              Giữ nguyên phần mở rộng của file. Nội dung và lựa chọn nguồn được
              giữ nguyên.
            </p>
            {failure && <Notice>{failure}</Notice>}
            <div className="modal-actions">
              <button
                type="button"
                className="button"
                disabled={busy}
                onClick={() => setRenaming(null)}
              >
                Hủy
              </button>
              <button
                className="button primary"
                disabled={busy || !newName.trim()}
              >
                Lưu tên
              </button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal
          title="Xóa nguồn khỏi workspace?"
          onClose={() => !busy && setDeleting(null)}
        >
          <p>
            “{deleting.name}” sẽ không còn được dùng cho câu trả lời mới. Các
            đoạn trích đã có trong hội thoại vẫn được giữ.
          </p>
          {failure && <Notice>{failure}</Notice>}
          <div className="modal-actions">
            <button
              className="button"
              disabled={busy}
              onClick={() => setDeleting(null)}
            >
              Hủy
            </button>
            <button
              className="button nb-danger"
              disabled={busy}
              onClick={() => void remove()}
            >
              Xóa nguồn
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
