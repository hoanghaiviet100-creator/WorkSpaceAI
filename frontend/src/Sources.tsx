import {
  memo,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
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
import { DialogCancel, Modal, Notice } from "./components";
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
type SourceAction = "inspect" | "rename" | "replace" | "delete";

const SourceRow = memo(function SourceRow({
  source,
  usable,
  connected,
  busy,
  pending,
  onToggle,
  onAction,
}: {
  source: Source;
  usable: boolean;
  connected: boolean;
  busy: boolean;
  pending: boolean;
  onToggle: (ids: string[], checked: boolean) => void;
  onAction: (action: SourceAction, source: Source) => void;
}) {
  return (
    <div
      className={`nb-source-row ${source.selected && usable ? "is-selected" : ""}`}
    >
      <button
        className="nb-source-open"
        title={source.name}
        onClick={() => onAction("inspect", source)}
      >
        <span className={`nb-file-icon kind-${source.kind.toLowerCase()}`}>
          <FileIcon source={source} />
        </span>
        <span>
          <strong>{source.name}</strong>
          <small>
            {source.status === "Processed"
              ? connected && source.origin !== "server"
                ? "Original file needed"
                : "Ready"
              : source.status === "Processing"
                ? "Processing"
                : source.status === "Unreadable"
                  ? "Unreadable file"
                  : "Preview only"}
            {source.totalPages
              ? ` · ${source.totalPages} ${source.kind.toLowerCase() === "pptx" ? "slide" : "trang"}`
              : ""}
          </small>
        </span>
      </button>
      <label
        className="nb-source-check"
        title={
          !usable
            ? source.limitation ||
              "Upload the original file to the server to use this source."
            : "Use this source for answers"
        }
      >
        <input
          type="checkbox"
          aria-label={`Use ${source.name}`}
          checked={source.selected && usable}
          disabled={busy || pending || !usable}
          onChange={(event) => onToggle([source.id], event.target.checked)}
        />
      </label>
      <ActionMenu
        label={`Options for ${source.name}`}
        actions={[
          {
            label: "View source",
            icon: <Info size={15} />,
            run: () => onAction("inspect", source),
          },
          {
            label: "Rename",
            icon: <Pencil size={15} />,
            disabled: busy,
            run: () => onAction("rename", source),
          },
          {
            label: "Re-upload original file",
            icon: <RefreshCw size={15} />,
            disabled: busy,
            run: () => onAction("replace", source),
          },
          {
            label: "Remove source",
            icon: <Trash2 size={15} />,
            danger: true,
            disabled: busy,
            run: () => onAction("delete", source),
          },
        ]}
      />
    </div>
  );
});

export default function Sources({
  workspace,
  update,
  onClose,
  notify,
  motionRef,
  intakeFiles,
  onIntakeComplete,
}: {
  workspace: Workspace;
  update: (fn: (workspace: Workspace) => Workspace) => void;
  onClose: () => void;
  notify: (message: string) => void;
  isDrawer: boolean;
  notebook?: boolean;
  motionRef?: RefObject<HTMLDivElement | null>;
  intakeFiles?: File[];
  onIntakeComplete: (ready: boolean) => void;
}) {
  const connected = apiFor(workspace.id);
  const [search, setSearch] = useState("");
  const [kind, setKind] = useState("");
  const [alphabetical, setAlphabetical] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pendingSelection, setPendingSelection] =
    useState<ReadonlySet<string> | null>(null);
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
  const updateRef = useRef(update);
  updateRef.current = update;
  const sourcesRef = useRef(workspace.sources);
  sourcesRef.current = workspace.sources;
  const commit = useCallback((fn: (current: Workspace) => Workspace) => {
    libraryRevision.current++;
    updateRef.current(fn);
  }, []);
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
            "Could not sync the library. Check the server connection and try again.",
          );
      });
    return () => {
      alive = false;
    };
  }, [workspace.id, connected]);
  const usable = useCallback(
    (source: Source) =>
      source.status === "Processed" &&
      (!connected || source.origin === "server"),
    [connected],
  );
  const selected = workspace.sources.filter(
    (source) => source.selected && usable(source),
  );
  const visible = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    const rows = workspace.sources.filter(
      (source) =>
        source.name.toLocaleLowerCase().includes(query) &&
        (!kind || source.kind.toUpperCase() === kind),
    );
    return alphabetical
      ? rows.sort((a, b) => a.name.localeCompare(b.name))
      : rows;
  }, [workspace.sources, search, kind, alphabetical]);
  const selectable = visible.filter(usable);
  const allSelected =
    !!selectable.length && selectable.every((source) => source.selected);
  useEffect(() => {
    if (selectAll.current)
      selectAll.current.indeterminate =
        !allSelected && selectable.some((source) => source.selected);
  }, [allSelected, selectable]);
  const toggle = useCallback(
    async (ids: string[], checked: boolean) => {
      if (lock.current) return;
      const sources = sourcesRef.current;
      const requested = new Set(ids);
      const changed = new Set(
        sources
          .filter(
            (source) =>
              requested.has(source.id) &&
              source.selected !== checked &&
              usable(source),
          )
          .map((source) => source.id),
      );
      if (!changed.size) return;

      lock.current = true;
      try {
        if (
          sources.some(
            (source) => changed.has(source.id) && source.origin === "server",
          )
        ) {
          setPendingSelection(changed);
          await selectDocuments(
            sources
              .filter(
                (source) =>
                  source.origin === "server" &&
                  (changed.has(source.id) ? checked : source.selected),
              )
              .map((source) => source.id),
            workspace.id,
          );
        }
        commit((current) => ({
          ...current,
          sources: current.sources.map((source) =>
            changed.has(source.id) ? { ...source, selected: checked } : source,
          ),
        }));
      } catch (error) {
        notify(
          error instanceof Error
            ? error.message
            : "Could not save source selection.",
        );
      } finally {
        lock.current = false;
        setPendingSelection(null);
      }
    },
    [workspace.id, usable, commit, notify],
  );
  const sync = async () => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setFailure("");
    try {
      const sources = await listDocuments(workspace.id);
      commit((current) => syncWorkspaceLibrary(current, sources));
      notify("Source library synced.");
    } catch (error) {
      setFailure(
        error instanceof Error ? error.message : "Could not sync the library.",
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
        "Choose a PDF, Word (.docx), PowerPoint (.pptx), TXT, MD, or CSV file.",
      );
    if (!file.size || file.size > 25 * 1024 * 1024)
      throw new Error(
        "The file must contain data and be no larger than 25 MB.",
      );
    if (
      replacement &&
      file.name.toLowerCase() !== replacement.name.toLowerCase()
    )
      throw new Error(
        `Choose the original file ${replacement.name}. Use Add source for a different document.`,
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
      return source;
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
          "Local preview. Re-upload to the server to use it for answers.",
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
  const upload = async (
    files: File[],
    replacement?: Source,
    selectForChat = false,
  ) => {
    if (!files.length || lock.current) return false;
    lock.current = true;
    setBusy(true);
    setFailure("");
    setAdd(null);
    let completed = true;
    const uploaded: Source[] = [];
    for (const file of files) {
      const id = crypto.randomUUID();
      setJobs((current) => [...current, { id, file, replacement }]);
      try {
        const source = await ingest(file, replacement);
        if (source) uploaded.push(source);
        setJobs((current) => current.filter((job) => job.id !== id));
      } catch (error) {
        completed = false;
        const message =
          error instanceof Error ? error.message : "Upload failed.";
        setJobs((current) =>
          current.map((job) =>
            job.id === id ? { ...job, error: message } : job,
          ),
        );
      }
    }
    if (selectForChat && uploaded.some((source) => !source.selected)) {
      const ids = new Set([
        ...sourcesRef.current
          .filter((source) => source.origin === "server" && source.selected)
          .map((source) => source.id),
        ...uploaded.map((source) => source.id),
      ]);
      try {
        await selectDocuments([...ids], workspace.id);
        commit((current) => ({
          ...current,
          sources: current.sources.map((source) =>
            ids.has(source.id) && !source.selected
              ? { ...source, selected: true }
              : source,
          ),
        }));
      } catch {
        completed = false;
      }
    }
    lock.current = false;
    setBusy(false);
    target.current = null;
    if (input.current) input.current.value = "";
    return completed;
  };
  const receivedFiles = useRef<File[] | undefined>(undefined);
  const uploadRef = useRef(upload);
  const intakeComplete = useRef(onIntakeComplete);
  uploadRef.current = upload;
  intakeComplete.current = onIntakeComplete;
  useEffect(() => {
    if (!intakeFiles?.length || receivedFiles.current === intakeFiles) return;
    receivedFiles.current = intakeFiles;
    void uploadRef.current(intakeFiles, undefined, true).then((completed) => {
      if (!completed)
        notify(
          "Some files could not be prepared. Check Sources before sending.",
        );
      else if (!connected)
        notify(
          "Files added as local previews. The question is saved in the composer.",
        );
      intakeComplete.current(completed && connected);
    });
  }, [intakeFiles, connected, notify]);
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
      notify("Source added from link.");
    } catch (error) {
      setFailure(
        error instanceof Error
          ? error.message
          : "Could not load content from the link.",
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
        error instanceof Error
          ? error.message
          : "Could not rename the document.",
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
        error instanceof Error
          ? error.message
          : "Could not remove the document.",
      );
    } finally {
      setBusy(false);
    }
  };
  const onSourceAction = useCallback((action: SourceAction, source: Source) => {
    if (action === "inspect") {
      setInspect(source);
      return;
    }
    if (lock.current) return;
    setFailure("");
    if (action === "rename") {
      setNewName(source.name);
      setRenaming(source);
    } else if (action === "replace") {
      target.current = source;
      setAdd("file");
    } else {
      setDeleting(source);
    }
  }, []);

  return (
    <>
      <div className="nb-panel-content nb-rail-surface" ref={motionRef}>
        <header className="nb-panel-header">
          <h2>
            Sources <span className="nb-count">{workspace.sources.length}</span>
          </h2>
          <button
            className="icon-button"
            aria-label="Collapse Sources"
            title="Collapse Sources"
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
            Add source
          </button>
          <label className="nb-source-search">
            <Search size={16} />
            <input
              aria-label="Search sources"
              placeholder="Search your sources"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            {search && (
              <button aria-label="Clear search" onClick={() => setSearch("")}>
                <X size={14} />
              </button>
            )}
          </label>
          <div className="nb-source-filter">
            <select
              aria-label="Filter by source type"
              value={kind}
              onChange={(event) => setKind(event.target.value)}
            >
              <option value="">All file types</option>
              {TYPES.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
            <button
              className="icon-button"
              aria-label="Sort sources by name"
              aria-pressed={alphabetical}
              onClick={() => setAlphabetical(!alphabetical)}
            >
              <ArrowDownAZ size={16} />
            </button>
            {connected && (
              <button
                className="icon-button"
                aria-label="Sync sources"
                disabled={busy}
                onClick={() => void sync()}
              >
                <RefreshCw size={16} />
              </button>
            )}
          </div>
          <div className="nb-source-selection">
            <span
              className="nb-source-count"
              title={`${selected.length} in use`}
            >
              {selected.length} in use
            </span>
            <label>
              Select all
              <input
                ref={selectAll}
                type="checkbox"
                aria-label="Select all sources"
                checked={allSelected}
                disabled={busy || !!pendingSelection || !selectable.length}
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
          <div className="nb-source-list" aria-busy={!!pendingSelection}>
            {jobs.map((job) => (
              <div className="nb-upload-job" key={job.id}>
                <Upload size={18} />
                <span>
                  <strong>{job.file.name}</strong>
                  <small>{job.error || "Uploading and processing…"}</small>
                </span>
                {job.error ? (
                  <button
                    className="icon-button"
                    aria-label={`Retry upload for ${job.file.name}`}
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
                  <LoaderCircle size={16} />
                )}
              </div>
            ))}
            {visible.map((source) => (
              <SourceRow
                key={source.id}
                source={source}
                usable={usable(source)}
                connected={connected}
                busy={busy}
                pending={pendingSelection?.has(source.id) ?? false}
                onToggle={toggle}
                onAction={onSourceAction}
              />
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
                    ? "No sources found"
                    : "Upload your first document"}
                </h3>
                <p>
                  {workspace.sources.length
                    ? "Try a different name or change the filter."
                    : "Drop a file, paste a link, or add text to get started."}
                </p>
              </div>
            )}
          </div>
          <div className="nb-source-footer">
            <span>
              <Check size={13} />
              Answers use selected sources only
            </span>
            <span>PDF · Word · PowerPoint · up to 25 MB per file</span>
          </div>
          {dragging && (
            <div className="nb-drop-overlay">
              <Upload size={28} />
              <strong>Drop documents to add them</strong>
            </div>
          )}
        </div>
      </div>
      {add && (
        <Modal
          title={
            target.current
              ? "Re-upload original file"
              : "Add a source to this note"
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
            aria-label="Add source method"
          >
            {(
              [
                { id: "file", label: "Upload file", icon: Upload },
                { id: "link", label: "Link", icon: Link },
                { id: "text", label: "Text", icon: FileText },
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
              <h3>Upload documents</h3>
              <p>
                Text-based PDF, Word (.docx), PowerPoint (.pptx), TXT, MD, and
                CSV. Up to 25 MB per file.
              </p>
              {target.current && (
                <p>
                  Choose the original file{" "}
                  <strong>{target.current.name}</strong> to restore this source.
                </p>
              )}
              {/* A real file control receives the trusted user gesture inside the dialog.
                  No synthetic click on a hidden input outside the active modal. */}
              <label
                className="button primary nb-native-file-picker"
                data-disabled={busy}
              >
                <span aria-hidden="true">Choose files from your device</span>
                <input
                  ref={input}
                  type="file"
                  accept={ACCEPT}
                  multiple={!target.current}
                  disabled={busy}
                  aria-label="Choose files from your device"
                  onChange={(event) =>
                    void upload(
                      Array.from(event.target.files || []),
                      target.current || undefined,
                    )
                  }
                />
              </label>
              <p className="small muted">
                You can also drag files into the Sources panel.
              </p>
            </div>
          ) : (
            <form
              className="form-stack"
              onSubmit={(event) => {
                event.preventDefault();
                if (add === "link") void importLink();
                else if (text.trim()) {
                  const filename = (title.trim() || "Pasted text").replace(
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
                Source name (optional)
                <input
                  maxLength={120}
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </label>
              {add === "link" ? (
                <>
                  <label>
                    Public link
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
                    Import a public web page or file. An internet connection is
                    required. Private links and pages that require sign-in are
                    unsupported.
                  </p>
                </>
              ) : (
                <label>
                  Content
                  <textarea
                    autoFocus
                    required
                    rows={8}
                    maxLength={1000000}
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                    placeholder="Paste document text here…"
                  />
                </label>
              )}
              {failure && <Notice>{failure}</Notice>}
              <div className="modal-actions">
                <DialogCancel disabled={busy} />
                <button
                  className="button primary"
                  disabled={busy || (add === "link" && !connected)}
                >
                  {busy ? "Adding…" : "Add source"}
                </button>
              </div>
            </form>
          )}
        </Modal>
      )}
      {inspect && (
        <Modal
          title="Source details"
          onClose={() => setInspect(null)}
          wide
          deferContent
        >
          <DocumentInspector source={inspect} workspaceId={workspace.id} />
        </Modal>
      )}
      {renaming && (
        <Modal title="Rename source" onClose={() => !busy && setRenaming(null)}>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              void rename();
            }}
          >
            <label>
              File name
              <input
                autoFocus
                required
                maxLength={180}
                value={newName}
                onChange={(event) => setNewName(event.target.value)}
              />
            </label>
            <p className="small muted">
              Keep the existing file extension. The contents and source
              selection stay the same.
            </p>
            {failure && <Notice>{failure}</Notice>}
            <div className="modal-actions">
              <DialogCancel disabled={busy} />
              <button
                className="button primary"
                disabled={busy || !newName.trim()}
              >
                Save name
              </button>
            </div>
          </form>
        </Modal>
      )}
      {deleting && (
        <Modal
          title="Remove source from this note?"
          onClose={() => !busy && setDeleting(null)}
        >
          <p>
            “{deleting.name}” will be removed from future answers. Excerpts
            already in the conversation are retained.
          </p>
          {failure && <Notice>{failure}</Notice>}
          <div className="modal-actions">
            <DialogCancel disabled={busy} />
            <button
              className="button nb-danger"
              disabled={busy}
              onClick={() => void remove()}
            >
              Remove source
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
