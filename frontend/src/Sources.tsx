import { useEffect, useId, useRef, useState } from "react";
import {
  Plus,
  Search,
  X,
  Trash2,
  FileText,
  FileSpreadsheet,
  Presentation,
  Braces,
  FolderOpen,
  ChevronDown,
  PanelRightClose,
  ArrowDownAZ,
  Info,
} from "lucide-react";
import { Status, Notice } from "./components";
import { type Workspace, type Source } from "./data";

const fileTypes = ["PDF", "Word", "PowerPoint", "TXT", "CSV", "JSON"];
function fileType(source: Source) {
  const kind = source.kind.toUpperCase();
  if (["DOC", "DOCX"].includes(kind)) return "Word";
  if (["PPT", "PPTX"].includes(kind)) return "PowerPoint";
  return kind;
}

export default function Sources({
  workspace,
  update,
  onClose,
  notify,
  isDrawer,
}: {
  workspace: Workspace;
  update: (fn: (w: Workspace) => Workspace) => void;
  onClose: () => void;
  notify: (s: string) => void;
  isDrawer: boolean;
}) {
  const [search, setSearch] = useState("");
  const [type, setType] = useState("All types");
  const [alphabetical, setAlphabetical] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const allCheckbox = useRef<HTMLInputElement>(null);
  const selected = workspace.sources.filter(
    (s) => s.selected && s.status === "Processed",
  ).length;
  const visible = workspace.sources
    .filter(
      (s) =>
        s.name.toLowerCase().includes(search.trim().toLowerCase()) &&
        (type === "All types" || fileType(s) === type),
    )
    .sort((a, b) => (alphabetical ? a.name.localeCompare(b.name) : 0));
  const selectable = visible.filter((s) => s.status === "Processed");
  const allSelected =
    selectable.length > 0 && selectable.every((s) => s.selected);
  const someSelected = selectable.some((s) => s.selected);
  const filtered = !!search.trim() || type !== "All types";
  useEffect(() => {
    if (allCheckbox.current)
      allCheckbox.current.indeterminate = someSelected && !allSelected;
  }, [someSelected, allSelected]);
  const upload = (files: FileList | null) => {
    if (!files) return;
    const added: Source[] = [];
    for (const f of Array.from(files)) {
      const ext = f.name.split(".").pop()?.toLowerCase();
      if (
        !["pdf", "ppt", "pptx", "doc", "docx", "txt", "csv", "json"].includes(
          ext || "",
        )
      ) {
        notify("Use PDF, PowerPoint, Word, TXT, CSV, or JSON files.");
        continue;
      }
      added.push({
        id: crypto.randomUUID(),
        name: f.name,
        kind: ext!.toUpperCase(),
        detail: `${Math.max(1, Math.round(f.size / 1024))} KB · Added just now`,
        status: "Preview only",
        selected: false,
        limitation:
          "Extraction is not connected. This file cannot be used as evidence yet.",
      });
    }
    update((w) => ({ ...w, sources: [...w.sources, ...added] }));
    if (added.length)
      notify(
        `${added.length} file${added.length > 1 ? "s" : ""} added to ${workspace.name}.`,
      );
    if (input.current) input.current.value = "";
  };
  return (
    <>
      <div className="sources-heading">
        <h2>
          Sources <span>{workspace.sources.length}</span>
        </h2>
        <button
          className="icon-button collapse-sources"
          aria-label={isDrawer ? "Close file repository" : "Collapse sources"}
          title={isDrawer ? "Close sources" : "Collapse sources"}
          aria-expanded="true"
          aria-controls="workspace-sources"
          onClick={onClose}
        >
          <PanelRightClose size={18} />
        </button>
      </div>
      <button
        className="button upload-button"
        onClick={() => input.current?.click()}
      >
        <Plus size={17} /> Add sources
      </button>
      <input
        type="file"
        multiple
        hidden
        ref={input}
        accept=".pdf,.ppt,.pptx,.doc,.docx,.txt,.csv,.json"
        onChange={(e) => upload(e.target.files)}
      />
      <div className="source-search-panel">
        <label className="source-search">
          <Search size={15} />
          <input
            aria-label="Find a file"
            placeholder="Find a source…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          {search && (
            <button
              type="button"
              aria-label="Clear file search"
              onClick={() => setSearch("")}
            >
              <X size={14} />
            </button>
          )}
        </label>
        <div className="source-filter-row">
          <select
            aria-label="Filter sources by type"
            value={type}
            onChange={(e) => setType(e.target.value)}
          >
            <option>All types</option>
            {fileTypes.map((kind) => (
              <option key={kind}>{kind}</option>
            ))}
          </select>
          <span>
            {filtered ? `${visible.length} found` : "In this workspace"}
          </span>
        </div>
      </div>
      <div className="source-list-label">
        <div className="source-selection-count">
          <button
            className="icon-button source-sort"
            aria-label={
              alphabetical ? "Restore source order" : "Sort sources by name"
            }
            title={alphabetical ? "Restore source order" : "Sort by name"}
            aria-pressed={alphabetical}
            onClick={() => setAlphabetical(!alphabetical)}
          >
            <ArrowDownAZ size={15} />
          </button>
          <span>{selected} selected</span>
          {selected > 0 && (
            <button
              className="clear-source-selection"
              aria-label="Clear selection"
              title="Clear selection"
              onClick={() =>
                update((w) => ({
                  ...w,
                  sources: w.sources.map((s) => ({ ...s, selected: false })),
                }))
              }
            >
              <X size={13} />
            </button>
          )}
        </div>
        <label className="select-all-sources">
          <span>{filtered ? "Select results" : "Select all"}</span>
          <input
            ref={allCheckbox}
            type="checkbox"
            aria-label={filtered ? "Select matching files" : "Select all files"}
            checked={allSelected}
            disabled={!selectable.length}
            onChange={(e) => {
              const checked = e.target.checked;
              const ids = new Set(selectable.map((s) => s.id));
              update((w) => ({
                ...w,
                sources: w.sources.map((s) =>
                  ids.has(s.id) ? { ...s, selected: checked } : s,
                ),
              }));
            }}
          />
        </label>
      </div>
      <div className="file-list" aria-label="Workspace sources">
        {visible.map((source) => (
          <SourceRow key={source.id} source={source} update={update} />
        ))}
        {!workspace.sources.length ? (
          <div className="repository-empty">
            <FolderOpen size={27} />
            <h3>No sources yet</h3>
            <p>Add your first file to start a grounded conversation.</p>
          </div>
        ) : !visible.length ? (
          <div className="source-no-results">
            <Search size={22} />
            <p>No sources match these filters.</p>
            <button
              onClick={() => {
                setSearch("");
                setType("All types");
              }}
            >
              Reset filters
            </button>
          </div>
        ) : null}
      </div>
      {workspace.sources.length >= 20 && (
        <Notice>
          Soft limit reached. Remove unused files to keep your workspace
          focused.
        </Notice>
      )}
      <details className="source-help">
        <summary>
          <Info size={14} />
          <span>{workspace.sources.length} of 20 sources</span>
          <ChevronDown size={14} />
        </summary>
        <div>
          <p>
            PDF, PowerPoint, Word, TXT, CSV and JSON. Up to 50 pages per PDF;
            20-file soft limit.
          </p>
          <p>
            Only selected, processed files are used. Sources stay in this
            workspace.
          </p>
        </div>
      </details>
    </>
  );
}

function SourceRow({
  source,
  update,
}: {
  source: Source;
  update: (fn: (w: Workspace) => Workspace) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const detailId = useId();
  const family = fileType(source);
  const Icon =
    family === "PowerPoint"
      ? Presentation
      : family === "CSV"
        ? FileSpreadsheet
        : family === "JSON"
          ? Braces
          : FileText;
  const ready = source.status === "Processed";
  return (
    <div
      className="source-row"
      data-selected={source.selected && ready}
      data-expanded={expanded}
    >
      <div className="source-row-main">
        <button
          className="source-summary"
          aria-label={`${expanded ? "Hide" : "Show"} details for ${source.name}`}
          aria-expanded={expanded}
          aria-controls={expanded ? detailId : undefined}
          title={source.name}
          onClick={() => setExpanded(!expanded)}
        >
          <Icon size={18} className="source-type-icon" data-type={family} />
          <span className="source-name">
            <strong>{source.name}</strong>
            {!ready && (
              <span className="source-row-status">{source.status}</span>
            )}
          </span>
          <ChevronDown size={13} className="source-row-chevron" />
        </button>
        <label
          className="source-check"
          title={
            ready ? `Use ${source.name}` : source.limitation || source.status
          }
        >
          <input
            type="checkbox"
            aria-label={`Use ${source.name}`}
            checked={source.selected && ready}
            disabled={!ready}
            onChange={() =>
              update((w) => ({
                ...w,
                sources: w.sources.map((s) =>
                  s.id === source.id ? { ...s, selected: !s.selected } : s,
                ),
              }))
            }
          />
        </label>
      </div>
      {expanded && (
        <div className="source-details" id={detailId}>
          <p className="source-full-name">{source.name}</p>
          <span className="source-detail">{source.detail}</span>
          <Status status={source.status} />
          {source.limitation && (
            <p className="source-warning">{source.limitation}</p>
          )}
          <button
            className="remove-source"
            aria-label={`Remove ${source.name}`}
            onClick={() =>
              update((w) => ({
                ...w,
                sources: w.sources.filter((s) => s.id !== source.id),
              }))
            }
          >
            <Trash2 size={13} /> Remove source
          </button>
        </div>
      )}
    </div>
  );
}
