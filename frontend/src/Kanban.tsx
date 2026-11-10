import {
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type PointerEvent,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  CheckSquare,
  Columns3,
  Copy,
  GripVertical,
  LoaderCircle,
  Minimize2,
  Plus,
  Search,
  Sparkles,
  Trash2,
  Undo2,
  X,
} from "lucide-react";
import { Modal } from "./components";
import ActionMenu from "./ActionMenu";
import type { Workspace } from "./data";
import {
  boardSummary,
  confirmProposal,
  dueState,
  id,
  moveCard,
  newCard,
  now,
  reorderColumn,
  saveBoard,
  selectedProposal,
  workspaceBoard,
  type KanbanBoard,
  type KanbanCard,
  type KanbanColumn,
  type KanbanProposal,
  type LabelTone,
  type Priority,
} from "./kanban-model";
import { suggestKanban } from "./kanban-service";

const priorities: Record<Priority, string> = {
  none: "Không đặt",
  low: "Thấp",
  medium: "Vừa",
  high: "Cao",
};
const tones: { id: LabelTone; name: string }[] = [
  { id: "neutral", name: "Xám" },
  { id: "orange", name: "Cam" },
  { id: "teal", name: "Xanh ngọc" },
  { id: "rose", name: "Hồng" },
];
const dateText = (value: string) =>
  value
    ? new Intl.DateTimeFormat("vi-VN", {
        day: "numeric",
        month: "short",
      }).format(new Date(value + "T12:00:00"))
    : "Chưa đặt hạn";
type Props = {
  workspace: Workspace;
  update: (fn: (workspace: Workspace) => Workspace) => void;
  notify: (text: string) => void;
};

export function KanbanSummary({
  workspace,
  onOpen,
}: {
  workspace: Workspace;
  onOpen: () => void;
}) {
  const board = workspaceBoard(workspace),
    summary = board && boardSummary(board);
  return (
    <section className="kb-summary" aria-label="Kanban của workspace">
      <div className="kb-summary-title">
        <Columns3 size={18} />
        <h3>Kanban</h3>
        {summary && <span>{summary.total} thẻ</span>}
      </div>
      {board && summary ? (
        <>
          <div className="kb-summary-counts">
            {board.columns.map((col) => (
              <span key={col.id}>
                <i data-done={col.status === "DONE"} />
                {col.title}
                <b>
                  {
                    board.cards.filter((card) => card.columnId === col.id)
                      .length
                  }
                </b>
              </span>
            ))}
          </div>
          <progress
            max={100}
            value={summary.percent}
            aria-label={`${summary.percent}% hoàn thành`}
          />
          <div className="kb-summary-meta">
            <span>
              {summary.done}/{summary.total} hoàn thành
            </span>
            <span>
              {summary.upcoming
                ? `Hạn gần nhất: ${dateText(summary.upcoming)}`
                : "Chưa có hạn chót"}
            </span>
          </div>
          <button className="button kb-open" onClick={onOpen}>
            Mở bảng <ArrowRight size={16} />
          </button>
        </>
      ) : (
        <>
          <p>Gom công việc từ tài liệu thành một bảng để cùng theo dõi.</p>
          <button className="button kb-open" onClick={onOpen}>
            Tạo bảng Kanban từ gợi ý của AI <ArrowRight size={16} />
          </button>
          <small>Offline · Xem trước rồi xác nhận</small>
        </>
      )}
    </section>
  );
}

function CardEditor({
  card,
  columns,
  workspace,
  onSave,
  onClose,
  onDelete,
  onDuplicate,
}: {
  card: KanbanCard;
  columns: KanbanColumn[];
  workspace: Workspace;
  onSave: (card: KanbanCard) => void;
  onClose: () => void;
  onDelete?: () => void;
  onDuplicate?: () => void;
}) {
  const [draft, setDraft] = useState(() => structuredClone(card));
  const [item, setItem] = useState(""),
    [label, setLabel] = useState(""),
    [tone, setTone] = useState<LabelTone>("teal");
  const [error, setError] = useState("");
  const patch = (next: Partial<KanbanCard>) =>
    setDraft((current) => ({ ...current, ...next }));
  return (
    <Modal
      title="Chi tiết thẻ"
      onClose={onClose}
      className="kb-card-editor"
      wide
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (
            draft.startDate &&
            draft.dueDate &&
            draft.startDate > draft.dueDate
          ) {
            setError("Hạn chót phải bằng hoặc sau ngày bắt đầu.");
            return;
          }
          onSave({ ...draft, title: draft.title.trim(), updatedAt: now() });
        }}
      >
        <label>
          Tiêu đề
          <input
            autoFocus
            required
            maxLength={160}
            value={draft.title}
            onChange={(e) => patch({ title: e.target.value })}
          />
        </label>
        <div className="kb-form-grid">
          <label>
            Loại
            <select
              value={draft.kind}
              onChange={(e) =>
                patch({ kind: e.target.value as KanbanCard["kind"] })
              }
            >
              <option value="task">Công việc</option>
              <option value="event">Sự kiện</option>
            </select>
          </label>
          <label>
            Cột
            <select
              value={draft.columnId}
              onChange={(e) => patch({ columnId: e.target.value })}
            >
              {columns.map((col) => (
                <option key={col.id} value={col.id}>
                  {col.title}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label>
          Mô tả
          <textarea
            rows={3}
            maxLength={6000}
            value={draft.description}
            onChange={(e) => patch({ description: e.target.value })}
          />
        </label>
        <div className="kb-form-grid">
          <label>
            Ngày bắt đầu
            <input
              type="date"
              value={draft.startDate}
              onChange={(e) => patch({ startDate: e.target.value })}
            />
          </label>
          <label>
            Hạn chót
            <input
              type="date"
              min={draft.startDate || undefined}
              value={draft.dueDate}
              onChange={(e) => patch({ dueDate: e.target.value })}
            />
          </label>
        </div>
        <label>
          Mức ưu tiên
          <select
            value={draft.priority}
            onChange={(e) => patch({ priority: e.target.value as Priority })}
          >
            {Object.entries(priorities).map(([value, text]) => (
              <option key={value} value={value}>
                {text}
              </option>
            ))}
          </select>
        </label>
        <fieldset>
          <legend>Nhãn màu</legend>
          <div className="kb-label-list">
            {draft.labels.map((entry, index) => (
              <button
                type="button"
                className="kb-label"
                data-tone={entry.tone}
                key={index}
                onClick={() =>
                  patch({ labels: draft.labels.filter((_, i) => i !== index) })
                }
                aria-label={`Xóa nhãn ${entry.name}`}
              >
                {entry.name}
                <X size={13} />
              </button>
            ))}
          </div>
          <div className="kb-inline">
            <input
              aria-label="Tên nhãn"
              maxLength={32}
              placeholder="Tên nhãn"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
            <select
              aria-label="Màu nhãn"
              value={tone}
              onChange={(e) => setTone(e.target.value as LabelTone)}
            >
              {tones.map((t) => (
                <option value={t.id} key={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="icon-button"
              disabled={!label.trim() || draft.labels.length >= 5}
              aria-label="Thêm nhãn"
              onClick={() => {
                patch({
                  labels: [...draft.labels, { name: label.trim(), tone }],
                });
                setLabel("");
              }}
            >
              <Plus size={18} />
            </button>
          </div>
        </fieldset>
        <fieldset>
          <legend>
            Checklist · {draft.checklist.filter((entry) => entry.done).length}/
            {draft.checklist.length}
          </legend>
          {draft.checklist.map((entry) => (
            <div className="kb-check-row" key={entry.id}>
              <label className="kb-check-target">
                <input
                  type="checkbox"
                  aria-label={`Hoàn thành ${entry.text}`}
                  checked={entry.done}
                  onChange={(e) =>
                    patch({
                      checklist: draft.checklist.map((next) =>
                        next.id === entry.id
                          ? { ...next, done: e.target.checked }
                          : next,
                      ),
                    })
                  }
                />
              </label>
              <input
                aria-label="Nội dung checklist"
                maxLength={180}
                value={entry.text}
                onChange={(e) =>
                  patch({
                    checklist: draft.checklist.map((next) =>
                      next.id === entry.id
                        ? { ...next, text: e.target.value }
                        : next,
                    ),
                  })
                }
              />
              <button
                type="button"
                className="icon-button"
                aria-label={`Xóa ${entry.text}`}
                onClick={() =>
                  patch({
                    checklist: draft.checklist.filter(
                      (next) => next.id !== entry.id,
                    ),
                  })
                }
              >
                <X size={16} />
              </button>
            </div>
          ))}
          <div className="kb-inline">
            <input
              aria-label="Thêm việc vào checklist"
              placeholder="Thêm việc vào checklist…"
              value={item}
              maxLength={180}
              onChange={(e) => setItem(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  if (item.trim()) {
                    patch({
                      checklist: [
                        ...draft.checklist,
                        { id: id(), text: item.trim(), done: false },
                      ],
                    });
                    setItem("");
                  }
                }
              }}
            />
            <button
              type="button"
              className="icon-button"
              disabled={!item.trim()}
              aria-label="Thêm checklist"
              onClick={() => {
                patch({
                  checklist: [
                    ...draft.checklist,
                    { id: id(), text: item.trim(), done: false },
                  ],
                });
                setItem("");
              }}
            >
              <Plus size={18} />
            </button>
          </div>
        </fieldset>
        <fieldset>
          <legend>Nguồn tài liệu liên quan</legend>
          {workspace.sources.length ? (
            <div className="kb-source-options">
              {workspace.sources.map((source) => (
                <label key={source.id}>
                  <input
                    type="checkbox"
                    checked={draft.sourceIds.includes(source.id)}
                    onChange={(e) =>
                      patch({
                        sourceIds: e.target.checked
                          ? [...draft.sourceIds, source.id]
                          : draft.sourceIds.filter(
                              (next) => next !== source.id,
                            ),
                      })
                    }
                  />
                  <span>{source.name}</span>
                </label>
              ))}
            </div>
          ) : (
            <p className="muted">
              Chưa có nguồn. Bạn có thể liên kết sau khi tải tài liệu.
            </p>
          )}
          {draft.sourceIds.some(
            (sourceId) =>
              !workspace.sources.some((source) => source.id === sourceId),
          ) && (
            <p className="muted">
              Có nguồn cũ đã bị xóa; thông tin thẻ vẫn được giữ.
            </p>
          )}
        </fieldset>
        <label>
          Ghi chú
          <textarea
            rows={3}
            maxLength={6000}
            value={draft.notes}
            onChange={(e) => patch({ notes: e.target.value })}
          />
        </label>
        <p className="kb-origin">
          {draft.origin === "ai"
            ? "Gợi ý tự động · Nội dung do bạn kiểm tra và xác nhận"
            : "Thẻ do người dùng thêm"}
        </p>
        {error && (
          <p className="kb-error" role="alert">
            {error}
          </p>
        )}
        <div className="kb-editor-actions">
          {onDelete && (
            <button type="button" className="button" onClick={onDelete}>
              <Trash2 size={16} />
              Xóa thẻ
            </button>
          )}
          {onDuplicate && (
            <button type="button" className="button" onClick={onDuplicate}>
              <Copy size={16} />
              Nhân bản
            </button>
          )}
          <button type="button" className="button" onClick={onClose}>
            Hủy
          </button>
          <button className="button primary" disabled={!draft.title.trim()}>
            Lưu thay đổi
          </button>
        </div>
      </form>
    </Modal>
  );
}

type Drag = { kind: "card" | "column"; id: string };
export default function Kanban({
  workspace,
  update,
  notify,
  open,
  onClose,
}: Props & { open: boolean; onClose: () => void }) {
  const board = workspaceBoard(workspace);
  const [phase, setPhase] = useState<"idle" | "loading" | "preview" | "error">(
    "idle",
  );
  const [proposal, setProposal] = useState<KanbanProposal | null>(null),
    [progress, setProgress] = useState(""),
    [error, setError] = useState("");
  const [query, setQuery] = useState(""),
    [priority, setPriority] = useState(""),
    [label, setLabel] = useState(""),
    [due, setDue] = useState("");
  const [editing, setEditing] = useState<KanbanCard | null>(null),
    [columnEdit, setColumnEdit] = useState<KanbanColumn | null>(null),
    [columnName, setColumnName] = useState(""),
    [columnDone, setColumnDone] = useState(false),
    [addingColumn, setAddingColumn] = useState(false);
  const [removingColumn, setRemovingColumn] = useState<KanbanColumn | null>(
      null,
    ),
    [destination, setDestination] = useState("");
  const [undo, setUndo] = useState<{ card: KanbanCard; index: number } | null>(
      null,
    ),
    [saved, setSaved] = useState(""),
    [announcement, setAnnouncement] = useState("");
  const [mobileColumn, setMobileColumn] = useState(0),
    [dragOver, setDragOver] = useState("");
  const [rename, setRename] = useState(false),
    [boardName, setBoardName] = useState("");
  const drag = useRef<Drag | null>(null),
    lanes = useRef<HTMLDivElement>(null),
    running = useRef(false),
    alive = useRef(true),
    latest = useRef(workspace);
  latest.current = workspace;
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  useEffect(() => {
    if (!board) return;
    setSaved("Đang lưu…");
    const frame = requestAnimationFrame(() => {
      try {
        const record = (
          JSON.parse(
            localStorage.getItem("workspaceai-v2") || "[]",
          ) as Workspace[]
        ).find((w) => w.id === workspace.id);
        setSaved(
          record?.kanban?.updatedAt === board.updatedAt
            ? "Đã lưu"
            : "Chưa lưu trên thiết bị",
        );
      } catch {
        setSaved("Chưa lưu trên thiết bị");
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [board?.updatedAt, workspace.id]);
  const change = (
    fn: (board: KanbanBoard) => KanbanBoard,
    message = "Đã cập nhật bảng",
  ) => {
    const current = workspaceBoard(latest.current);
    if (!current) return;
    try {
      saveBoard(latest.current, fn(current));
      update((w) => {
        const latestBoard = workspaceBoard(w);
        return latestBoard ? saveBoard(w, fn(latestBoard)) : w;
      });
      setAnnouncement(message);
    } catch (reason) {
      notify(
        reason instanceof Error ? reason.message : "Chưa lưu được thay đổi.",
      );
    }
  };
  const generate = async (demo = false) => {
    if (running.current) return;
    running.current = true;
    setPhase("loading");
    setError("");
    setProgress("Đang chuẩn bị gợi ý…");
    try {
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
      const next = await suggestKanban(
        latest.current,
        demo,
        (text) => alive.current && setProgress(text),
      );
      if (alive.current) {
        setProposal(next);
        setPhase("preview");
      }
    } catch (reason) {
      if (alive.current) {
        setError(
          reason instanceof Error
            ? reason.message
            : "Chưa tạo được gợi ý. Hãy thử lại.",
        );
        setPhase("error");
      }
    } finally {
      running.current = false;
    }
  };
  const confirm = () => {
    if (!proposal) return;
    try {
      confirmProposal(latest.current, proposal);
      update((w) => {
        try {
          return confirmProposal(w, proposal);
        } catch {
          return w;
        }
      });
      setPhase("idle");
      setProposal(null);
      setError("");
      notify(
        proposal.mode === "initial"
          ? "Đã tạo bảng Kanban duy nhất của workspace."
          : "Đã thêm các thẻ đã chọn; giữ nguyên thẻ hiện có.",
      );
    } catch (reason) {
      setError(
        reason instanceof Error ? reason.message : "Chưa xác nhận được.",
      );
    }
  };
  const removeCard = (card: KanbanCard) => {
    setUndo({
      card,
      index: board?.cards.findIndex((c) => c.id === card.id) || 0,
    });
    change(
      (b) => ({ ...b, cards: b.cards.filter((c) => c.id !== card.id) }),
      `Đã xóa ${card.title}. Có thể hoàn tác.`,
    );
    setEditing(null);
  };
  const duplicate = (card: KanbanCard) => {
    const fresh = newCard(
      card.columnId,
      `${card.title.slice(0, 148)} (bản sao)`,
    );
    change((b) => ({
      ...b,
      cards: [
        ...b.cards,
        {
          ...structuredClone(card),
          ...fresh,
          description: card.description,
          startDate: card.startDate,
          dueDate: card.dueDate,
          priority: card.priority,
          labels: structuredClone(card.labels),
          checklist: card.checklist.map((entry) => ({ ...entry, id: id() })),
          sourceIds: [...card.sourceIds],
          notes: card.notes,
        },
      ],
    }));
    setEditing(null);
  };
  const applyDrag = (
    target: Element | null,
    point: { x: number; y: number },
  ) => {
    const active = drag.current;
    if (!active) return;
    const column = target?.closest<HTMLElement>("[data-column-id]");
    if (!column) return;
    const overCard = target?.closest<HTMLElement>("[data-card-id]");
    let before = overCard?.dataset.cardId;
    if (overCard) {
      const rect = overCard.getBoundingClientRect();
      if (point.y > rect.top + rect.height / 2)
        before =
          overCard.nextElementSibling?.getAttribute("data-card-id") ||
          undefined;
    }
    const rect = column.getBoundingClientRect();
    const beforeColumn =
      point.x > rect.left + rect.width / 2
        ? column.nextElementSibling?.getAttribute("data-column-id") || undefined
        : column.dataset.columnId;
    change(
      (b) =>
        active.kind === "card"
          ? moveCard(b, active.id, column.dataset.columnId!, before)
          : reorderColumn(b, active.id, beforeColumn),
      "Đã di chuyển. Đã cập nhật thứ tự bảng.",
    );
  };
  const dragProps = (item: Drag) => ({
    draggable: true,
    onDragStart: (event: DragEvent) => {
      drag.current = item;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", item.id);
    },
    onDragEnd: () => {
      drag.current = null;
      setDragOver("");
    },
    onPointerDown: (event: PointerEvent<HTMLButtonElement>) => {
      if (event.pointerType === "mouse") return;
      drag.current = item;
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    onPointerMove: (event: PointerEvent<HTMLButtonElement>) => {
      if (event.pointerType === "mouse" || !drag.current) return;
      const target = document.elementFromPoint(event.clientX, event.clientY);
      setDragOver(
        target?.closest<HTMLElement>("[data-column-id]")?.dataset.columnId ||
          "",
      );
      const frame = lanes.current?.getBoundingClientRect();
      if (frame && lanes.current) {
        if (event.clientX > frame.right - 40) lanes.current.scrollLeft += 18;
        else if (event.clientX < frame.left + 40)
          lanes.current.scrollLeft -= 18;
      }
    },
    onPointerUp: (event: PointerEvent<HTMLButtonElement>) => {
      if (event.pointerType === "mouse") return;
      applyDrag(document.elementFromPoint(event.clientX, event.clientY), {
        x: event.clientX,
        y: event.clientY,
      });
      drag.current = null;
      setDragOver("");
    },
    onPointerCancel: (event: PointerEvent<HTMLButtonElement>) => {
      // Native HTML drag cancels the mouse pointer stream after dragstart.
      // Keep its drag data until drop/dragend; only cancel our touch gesture here.
      if (event.pointerType === "mouse") return;
      drag.current = null;
      setDragOver("");
    },
  });
  const keyboardMove = (card: KanbanCard, key: string) => {
    if (!board) return;
    const col = board.columns.findIndex((col) => col.id === card.columnId),
      rows = board.cards.filter((c) => c.columnId === card.columnId),
      index = rows.findIndex((c) => c.id === card.id);
    if (key === "ArrowLeft" && col > 0)
      change((b) => moveCard(b, card.id, b.columns[col - 1].id));
    if (key === "ArrowRight" && col < board.columns.length - 1)
      change((b) => moveCard(b, card.id, b.columns[col + 1].id));
    if (key === "ArrowUp" && index > 0)
      change((b) => moveCard(b, card.id, card.columnId, rows[index - 1].id));
    if (key === "ArrowDown" && index < rows.length - 1)
      change((b) => moveCard(b, card.id, card.columnId, rows[index + 2]?.id));
  };
  const shownBoard = phase === "preview" ? null : board;
  const labels = [
    ...new Set(
      board?.cards.flatMap((card) => card.labels.map((entry) => entry.name)) ||
        [],
    ),
  ];
  const matching = (card: KanbanCard, col: KanbanColumn) =>
    [
      card.title,
      card.description,
      card.notes,
      ...card.labels.map((entry) => entry.name),
    ]
      .join(" ")
      .toLocaleLowerCase()
      .includes(query.toLocaleLowerCase().trim()) &&
    (!priority || card.priority === priority) &&
    (!label || card.labels.some((entry) => entry.name === label)) &&
    (!due ||
      (due === "unset"
        ? !card.dueDate
        : dueState(card, col.status === "DONE") === due));
  const counts = proposal && selectedProposal(proposal);
  const close = () => {
    setEditing(null);
    onClose();
  };
  if (!open) return null;
  return (
    <>
      <Modal
        title={`Kanban · ${workspace.name}`}
        onClose={close}
        className="kb-board-modal"
        wide
      >
        <div className="kb-toolbar">
          <div className="kb-board-identity">
            <Columns3 size={21} />
            {shownBoard ? (
              <button
                className="kb-name"
                onClick={() => {
                  setBoardName(shownBoard.name);
                  setRename(true);
                }}
                title="Đổi tên bảng"
              >
                {shownBoard.name}
              </button>
            ) : (
              <h3>
                {phase === "preview" ? "Xem trước gợi ý" : "Kế hoạch workspace"}
              </h3>
            )}
            <span className="kb-save" role="status">
              {shownBoard ? saved : "Chưa xác nhận"}
            </span>
          </div>
          <div className="kb-toolbar-actions">
            {shownBoard && phase !== "loading" && (
              <button
                className="button"
                title="Nhờ AI gợi ý thêm · Offline"
                aria-label="Nhờ AI gợi ý thêm"
                onClick={() => void generate()}
              >
                <Sparkles size={16} />
                Nhờ AI gợi ý thêm
              </button>
            )}
            <button
              className="icon-button"
              onClick={close}
              aria-label="Thu nhỏ về Studio"
              title="Thu nhỏ về Studio"
            >
              <Minimize2 size={19} />
            </button>
          </div>
        </div>
        <div className="sr-only" aria-live="polite">
          {announcement}
        </div>
        <p id="kb-move-help" className="sr-only">
          Dùng nút Di chuyển: giữ Alt và phím mũi tên trái phải để đổi cột, lên
          xuống để đổi thứ tự. Trên cảm ứng giữ và kéo nút này.
        </p>
        {phase === "loading" ? (
          <div className="kb-generation" role="status" aria-busy="true">
            <LoaderCircle size={24} className="spin" />
            <h3>Đang chuẩn bị bản xem trước</h3>
            <p>{progress}</p>
            <div className="kb-skeletons">
              {[1, 2, 3].map((n) => (
                <div key={n}>
                  <span />
                  <span />
                  <span />
                </div>
              ))}
            </div>
            <p>Bảng hiện có được giữ nguyên trong lúc tạo gợi ý.</p>
          </div>
        ) : phase === "error" ? (
          <div className="kb-empty">
            <Columns3 size={32} />
            <h3>Chưa tạo được gợi ý</h3>
            <p className="kb-error" role="alert">
              {error}
            </p>
            <button className="button primary" onClick={() => void generate()}>
              Thử lại
            </button>
            {board ? (
              <button className="button" onClick={() => setPhase("idle")}>
                Về bảng hiện có
              </button>
            ) : (
              <button className="button" onClick={() => void generate(true)}>
                Xem bản mẫu 8 thẻ
              </button>
            )}
          </div>
        ) : phase === "preview" && proposal ? (
          <>
            <div className="kb-preview-note">
              <Sparkles size={18} />
              <div>
                <strong>
                  {proposal.engine === "demo"
                    ? "Bản mẫu mô phỏng"
                    : "Gợi ý Offline"}{" "}
                  ·{" "}
                  {proposal.mode === "initial"
                    ? "Chưa tạo bảng"
                    : "Chưa thêm vào bảng"}
                </strong>
                <p>{proposal.contextNote}</p>
              </div>
            </div>
            <div className="kb-preview-options">
              <label>
                Tên bảng
                <input
                  value={proposal.name}
                  disabled={proposal.mode === "append"}
                  maxLength={120}
                  onChange={(e) =>
                    setProposal({ ...proposal, name: e.target.value })
                  }
                />
              </label>
              <span>
                {counts?.cards.length} thẻ được chọn · Có thể sửa trước khi lưu
              </span>
            </div>
            <div className="kb-lanes kb-preview-lanes">
              {proposal.columns.map((col) => (
                <section className="kb-column" key={col.id}>
                  <div className="kb-preview-column">
                    <label className="kb-check-target">
                      <input
                        type="checkbox"
                        aria-label={`Chọn cột ${col.title}`}
                        checked={col.selected}
                        onChange={(e) =>
                          setProposal({
                            ...proposal,
                            columns: proposal.columns.map((c) =>
                              c.id === col.id
                                ? { ...c, selected: e.target.checked }
                                : c,
                            ),
                          })
                        }
                      />
                    </label>
                    <input
                      aria-label="Tên cột gợi ý"
                      required
                      maxLength={50}
                      value={col.title}
                      readOnly={proposal.mode === "append"}
                      onChange={(e) =>
                        setProposal({
                          ...proposal,
                          columns: proposal.columns.map((c) =>
                            c.id === col.id
                              ? { ...c, title: e.target.value }
                              : c,
                          ),
                        })
                      }
                    />
                    {proposal.mode === "initial" && (
                      <button
                        className="icon-button"
                        aria-label={`Xóa cột gợi ý ${col.title}`}
                        onClick={() =>
                          setProposal({
                            ...proposal,
                            columns: proposal.columns.filter(
                              (c) => c.id !== col.id,
                            ),
                            cards: proposal.cards.filter(
                              (c) => c.columnId !== col.id,
                            ),
                          })
                        }
                      >
                        <X size={16} />
                      </button>
                    )}
                  </div>
                  <div className="kb-column-cards">
                    {proposal.cards
                      .filter((card) => card.columnId === col.id)
                      .map((card) => (
                        <article
                          className={`kb-preview-card ${!col.selected ? "is-excluded" : ""}`}
                          key={card.id}
                        >
                          <div className="kb-preview-select">
                            <label className="kb-check-target">
                              <input
                                type="checkbox"
                                aria-label={`Chọn thẻ ${card.title}`}
                                checked={card.selected}
                                disabled={!col.selected}
                                onChange={(e) =>
                                  setProposal({
                                    ...proposal,
                                    cards: proposal.cards.map((c) =>
                                      c.id === card.id
                                        ? { ...c, selected: e.target.checked }
                                        : c,
                                    ),
                                  })
                                }
                              />
                            </label>
                            <input
                              aria-label="Tiêu đề thẻ gợi ý"
                              maxLength={160}
                              value={card.title}
                              onChange={(e) =>
                                setProposal({
                                  ...proposal,
                                  cards: proposal.cards.map((c) =>
                                    c.id === card.id
                                      ? { ...c, title: e.target.value }
                                      : c,
                                  ),
                                })
                              }
                            />
                          </div>
                          <div className="kb-preview-card-footer">
                            <span>
                              {card.dueDate
                                ? dateText(card.dueDate)
                                : "Chưa đặt hạn"}
                            </span>
                            <button
                              className="kb-text"
                              onClick={() => setEditing(card)}
                            >
                              Chỉnh sửa
                            </button>
                            <button
                              className="icon-button"
                              aria-label={`Bỏ thẻ ${card.title}`}
                              onClick={() =>
                                setProposal({
                                  ...proposal,
                                  cards: proposal.cards.filter(
                                    (c) => c.id !== card.id,
                                  ),
                                })
                              }
                            >
                              <X size={15} />
                            </button>
                          </div>
                        </article>
                      ))}
                    {!proposal.cards.some((c) => c.columnId === col.id) && (
                      <p className="kb-column-empty">Không có thẻ gợi ý</p>
                    )}
                  </div>
                </section>
              ))}
            </div>
            <footer className="kb-preview-footer">
              <span>
                {error && (
                  <span role="alert" className="kb-error">
                    {error}
                  </span>
                )}
                {proposal.mode === "append"
                  ? "Chỉ thêm thẻ đã chọn. Không ghi đè thẻ hiện có."
                  : "Sau xác nhận, workspace sẽ có một bảng Kanban duy nhất."}
              </span>
              <button
                className="button"
                onClick={() => {
                  setPhase("idle");
                  setProposal(null);
                  setError("");
                }}
              >
                Hủy gợi ý
              </button>
              <button
                className="button primary"
                disabled={!counts?.cards.length || !counts.columns.length}
                onClick={confirm}
              >
                Xác nhận {counts?.cards.length} thẻ
              </button>
            </footer>
          </>
        ) : shownBoard ? (
          <>
            <div className="kb-filters">
              <label className="kb-search">
                <Search size={17} />
                <input
                  aria-label="Tìm kiếm thẻ"
                  placeholder="Tìm trong bảng…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </label>
              <select
                aria-label="Lọc nhãn"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
              >
                <option value="">Tất cả nhãn</option>
                {labels.map((name) => (
                  <option key={name}>{name}</option>
                ))}
              </select>
              <select
                aria-label="Lọc ưu tiên"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                <option value="">Mọi ưu tiên</option>
                {Object.entries(priorities).map(([value, text]) => (
                  <option value={value} key={value}>
                    {text}
                  </option>
                ))}
              </select>
              <select
                aria-label="Lọc hạn chót"
                value={due}
                onChange={(e) => setDue(e.target.value)}
              >
                <option value="">Mọi hạn chót</option>
                <option value="overdue">Quá hạn</option>
                <option value="soon">Trong 3 ngày</option>
                <option value="unset">Chưa đặt hạn</option>
              </select>
              {(query || label || priority || due) && (
                <button
                  className="kb-text"
                  onClick={() => {
                    setQuery("");
                    setLabel("");
                    setPriority("");
                    setDue("");
                  }}
                >
                  Xóa bộ lọc
                </button>
              )}
              <button
                className="button kb-add-column"
                onClick={() => {
                  setColumnName("");
                  setColumnDone(false);
                  setAddingColumn(true);
                }}
              >
                <Plus size={16} />
                Thêm cột
              </button>
            </div>
            <div
              className="kb-lanes"
              ref={lanes}
              onScroll={() => {
                const el = lanes.current;
                if (el) {
                  const width =
                    el.firstElementChild?.getBoundingClientRect().width || 1;
                  setMobileColumn(
                    Math.max(
                      0,
                      Math.min(
                        shownBoard.columns.length - 1,
                        Math.round(el.scrollLeft / (width + 16)),
                      ),
                    ),
                  );
                }
              }}
            >
              {shownBoard.columns.map((col, columnIndex) => {
                const all = shownBoard.cards.filter(
                    (card) => card.columnId === col.id,
                  ),
                  cards = all.filter((card) => matching(card, col));
                return (
                  <section
                    className={`kb-column ${dragOver === col.id ? "kb-drop-active" : ""}`}
                    data-column-id={col.id}
                    key={col.id}
                    aria-label={`Cột ${col.title}`}
                    onDragOver={(event) => {
                      if (drag.current) {
                        event.preventDefault();
                        event.dataTransfer.dropEffect = "move";
                        setDragOver(col.id);
                      }
                    }}
                    onDrop={(event) => {
                      event.preventDefault();
                      applyDrag(event.target as Element, {
                        x: event.clientX,
                        y: event.clientY,
                      });
                      drag.current = null;
                      setDragOver("");
                    }}
                  >
                    <header className="kb-column-header">
                      <button
                        className="kb-grip"
                        aria-label={`Di chuyển cột ${col.title}`}
                        {...dragProps({ kind: "column", id: col.id })}
                        onKeyDown={(event) => {
                          if (
                            event.altKey &&
                            ["ArrowLeft", "ArrowRight"].includes(event.key)
                          ) {
                            event.preventDefault();
                            const target =
                              event.key === "ArrowLeft"
                                ? columnIndex - 1
                                : columnIndex + 2;
                            if (
                              target < 0 ||
                              (columnIndex === shownBoard.columns.length - 1 &&
                                event.key === "ArrowRight")
                            )
                              return;
                            change((b) =>
                              reorderColumn(b, col.id, b.columns[target]?.id),
                            );
                          }
                        }}
                      >
                        <GripVertical size={16} />
                      </button>
                      <h3>{col.title}</h3>
                      <span className="kb-count">
                        {cards.length}
                        {cards.length !== all.length ? `/${all.length}` : ""}
                      </span>
                      <ActionMenu
                        label={`Tùy chọn cột ${col.title}`}
                        actions={[
                          {
                            label: "Đổi tên cột",
                            run: () => {
                              setColumnEdit(col);
                              setColumnName(col.title);
                              setColumnDone(col.status === "DONE");
                            },
                          },
                          {
                            label: "Chuyển cột sang trái",
                            disabled: columnIndex === 0,
                            run: () =>
                              change((b) =>
                                reorderColumn(
                                  b,
                                  col.id,
                                  b.columns[columnIndex - 1]?.id,
                                ),
                              ),
                          },
                          {
                            label: "Chuyển cột sang phải",
                            disabled:
                              columnIndex === shownBoard.columns.length - 1,
                            run: () =>
                              change((b) =>
                                reorderColumn(
                                  b,
                                  col.id,
                                  b.columns[columnIndex + 2]?.id,
                                ),
                              ),
                          },
                          {
                            label: "Xóa cột",
                            danger: true,
                            disabled: shownBoard.columns.length === 1,
                            run: () => {
                              setRemovingColumn(col);
                              setDestination(
                                shownBoard.columns.find((c) => c.id !== col.id)!
                                  .id,
                              );
                            },
                          },
                        ]}
                      />
                    </header>
                    <div className="kb-column-cards">
                      {cards.map((card) => {
                        const dueFlag = dueState(card, col.status === "DONE"),
                          completed = card.checklist.filter(
                            (entry) => entry.done,
                          ).length;
                        return (
                          <article
                            className="kb-card"
                            data-card-id={card.id}
                            key={card.id}
                          >
                            <div className="kb-card-top">
                              <button
                                className="kb-grip"
                                aria-label={`Di chuyển thẻ ${card.title}`}
                                aria-describedby="kb-move-help"
                                {...dragProps({ kind: "card", id: card.id })}
                                onKeyDown={(event) => {
                                  if (
                                    event.altKey &&
                                    [
                                      "ArrowLeft",
                                      "ArrowRight",
                                      "ArrowUp",
                                      "ArrowDown",
                                    ].includes(event.key)
                                  ) {
                                    event.preventDefault();
                                    keyboardMove(card, event.key);
                                  }
                                }}
                              >
                                <GripVertical size={15} />
                              </button>
                              <div className="kb-card-labels">
                                {card.labels.map((entry, index) => (
                                  <span
                                    className="kb-label"
                                    data-tone={entry.tone}
                                    key={index}
                                  >
                                    {entry.name}
                                  </span>
                                ))}
                              </div>
                              {card.origin === "ai" && (
                                <span
                                  className="kb-ai"
                                  title="Thẻ từ gợi ý tự động đã được xác nhận"
                                  aria-label="Thẻ AI gợi ý"
                                >
                                  <Sparkles size={14} />
                                </span>
                              )}
                              <ActionMenu
                                label={`Tùy chọn thẻ ${card.title}`}
                                actions={[
                                  {
                                    label: "Chỉnh sửa",
                                    run: () => setEditing(card),
                                  },
                                  {
                                    label: "Nhân bản",
                                    run: () => duplicate(card),
                                  },
                                  {
                                    label: "Xóa thẻ",
                                    danger: true,
                                    run: () => removeCard(card),
                                  },
                                ]}
                              />
                            </div>
                            <button
                              className="kb-card-title"
                              onClick={() => setEditing(card)}
                            >
                              {card.kind === "event" && (
                                <CalendarDays size={15} />
                              )}
                              <span>{card.title}</span>
                            </button>
                            {card.description && (
                              <p className="kb-card-description">
                                {card.description}
                              </p>
                            )}
                            <div className="kb-card-meta">
                              {card.dueDate && (
                                <span className="kb-due" data-state={dueFlag}>
                                  <CalendarDays size={13} />
                                  {dueFlag === "overdue"
                                    ? "Quá hạn · "
                                    : dueFlag === "soon"
                                      ? "Sắp đến · "
                                      : ""}
                                  {dateText(card.dueDate)}
                                </span>
                              )}
                              {card.priority !== "none" && (
                                <span
                                  className="kb-priority"
                                  data-priority={card.priority}
                                >
                                  Ưu tiên{" "}
                                  {priorities[
                                    card.priority
                                  ].toLocaleLowerCase()}
                                </span>
                              )}
                              {card.checklist.length > 0 && (
                                <span>
                                  <CheckSquare size={13} />
                                  {completed}/{card.checklist.length}
                                </span>
                              )}
                              {card.sourceIds.length > 0 && (
                                <span>{card.sourceIds.length} nguồn</span>
                              )}
                            </div>
                          </article>
                        );
                      })}
                      {!cards.length && (
                        <p className="kb-column-empty">
                          {all.length
                            ? "Không có thẻ khớp bộ lọc"
                            : "Chưa có thẻ trong cột này"}
                        </p>
                      )}
                    </div>
                    <QuickAdd
                      column={col}
                      onAdd={(title) => {
                        const card = newCard(col.id, title);
                        change(
                          (b) => ({ ...b, cards: [...b.cards, card] }),
                          `Đã thêm ${title}`,
                        );
                      }}
                    />
                  </section>
                );
              })}
            </div>
            <div className="kb-mobile-dots" aria-label="Chuyển cột">
              {shownBoard.columns.map((col, index) => (
                <button
                  aria-label={`Xem cột ${col.title}`}
                  aria-pressed={mobileColumn === index}
                  key={col.id}
                  onClick={() => {
                    const target = lanes.current?.children[
                      index
                    ] as HTMLElement;
                    lanes.current?.scrollTo({
                      left:
                        target?.offsetLeft -
                        (lanes.current.firstElementChild as HTMLElement)
                          ?.offsetLeft,
                      behavior: matchMedia("(prefers-reduced-motion: reduce)")
                        .matches
                        ? "instant"
                        : "smooth",
                    });
                  }}
                >
                  <i />
                  {mobileColumn === index && <span>{col.title}</span>}
                </button>
              ))}
            </div>
            <footer className="kb-board-footer">
              <span>
                {shownBoard.cards.length} thẻ ·{" "}
                {boardSummary(shownBoard).percent}% hoàn thành
              </span>
              <span>Alt + phím mũi tên trên nút kéo để di chuyển</span>
            </footer>
          </>
        ) : (
          <div className="kb-empty">
            <Columns3 size={36} />
            <h3>Một bảng cho cả workspace</h3>
            <p>
              Biến tài liệu và trao đổi thành các thẻ công việc. Bạn chọn, sửa
              và xác nhận trước khi tạo bảng.
            </p>
            <button className="button primary" onClick={() => void generate()}>
              <Sparkles size={17} />
              Tạo bảng Kanban từ gợi ý của AI
            </button>
            <span className="kb-offline">
              Offline · Gợi ý theo quy tắc, không gọi mô hình AI
            </span>
            <button className="kb-text" onClick={() => void generate(true)}>
              Thử giao diện với 8 thẻ mẫu
            </button>
          </div>
        )}
        {undo && (
          <div className="kb-undo" role="status">
            <span>Đã xóa “{undo.card.title}”</span>
            <button
              onClick={() => {
                const restore = undo;
                change((b) => {
                  if (b.cards.some((c) => c.id === restore.card.id)) return b;
                  const cards = [...b.cards];
                  cards.splice(Math.max(0, restore.index), 0, {
                    ...restore.card,
                    columnId: b.columns.some(
                      (col) => col.id === restore.card.columnId,
                    )
                      ? restore.card.columnId
                      : b.columns[0].id,
                  });
                  return { ...b, cards };
                }, "Đã hoàn tác xóa thẻ");
                setUndo(null);
              }}
            >
              <Undo2 size={16} />
              Hoàn tác
            </button>
            <button aria-label="Đóng thông báo" onClick={() => setUndo(null)}>
              <X size={16} />
            </button>
          </div>
        )}
      </Modal>
      {editing && (
        <CardEditor
          key={editing.id}
          card={editing}
          columns={
            phase === "preview" ? proposal?.columns || [] : board?.columns || []
          }
          workspace={workspace}
          onClose={() => setEditing(null)}
          onSave={(card) => {
            if (phase === "preview" && proposal)
              setProposal({
                ...proposal,
                cards: proposal.cards.map((c) =>
                  c.id === card.id ? { ...card, selected: c.selected } : c,
                ),
              });
            else
              change((b) => ({
                ...b,
                cards: b.cards.map((c) => (c.id === card.id ? card : c)),
              }));
            setEditing(null);
          }}
          onDelete={phase === "preview" ? undefined : () => removeCard(editing)}
          onDuplicate={
            phase === "preview" ? undefined : () => duplicate(editing)
          }
        />
      )}
      {(columnEdit || addingColumn) && (
        <Modal
          title={addingColumn ? "Thêm cột" : "Chỉnh sửa cột"}
          onClose={() => {
            setColumnEdit(null);
            setAddingColumn(false);
          }}
        >
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (!columnName.trim()) return;
              const col: KanbanColumn = columnEdit
                ? {
                    ...columnEdit,
                    title: columnName.trim(),
                    status: columnDone
                      ? "DONE"
                      : columnEdit.status === "DONE"
                        ? "TODO"
                        : columnEdit.status,
                  }
                : {
                    id: id(),
                    title: columnName.trim(),
                    status: columnDone ? "DONE" : "TODO",
                  };
              change((b) => ({
                ...b,
                columns: addingColumn
                  ? [...b.columns, col]
                  : b.columns.map((c) => (c.id === col.id ? col : c)),
              }));
              setColumnEdit(null);
              setAddingColumn(false);
            }}
          >
            <label>
              Tên cột
              <input
                autoFocus
                required
                maxLength={50}
                value={columnName}
                onChange={(e) => setColumnName(e.target.value)}
              />
            </label>
            <label className="kb-checkbox">
              <input
                type="checkbox"
                checked={columnDone}
                onChange={(e) => setColumnDone(e.target.checked)}
              />
              Thẻ trong cột này được tính là hoàn thành
            </label>
            <button className="button primary" disabled={!columnName.trim()}>
              Lưu cột
            </button>
          </form>
        </Modal>
      )}
      {removingColumn && board && (
        <Modal
          title="Xóa cột, giữ lại công việc"
          onClose={() => setRemovingColumn(null)}
        >
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              change((b) => ({
                ...b,
                columns: b.columns.filter((c) => c.id !== removingColumn.id),
                cards: b.cards.map((c) =>
                  c.columnId === removingColumn.id
                    ? { ...c, columnId: destination }
                    : c,
                ),
              }));
              setRemovingColumn(null);
            }}
          >
            <p>
              Các thẻ trong “{removingColumn.title}” sẽ được chuyển sang cột bạn
              chọn.
            </p>
            <label>
              Chuyển thẻ sang
              <select
                value={destination}
                onChange={(e) => setDestination(e.target.value)}
              >
                {board.columns
                  .filter((col) => col.id !== removingColumn.id)
                  .map((col) => (
                    <option key={col.id} value={col.id}>
                      {col.title}
                    </option>
                  ))}
              </select>
            </label>
            <button className="button primary">Xóa cột và chuyển thẻ</button>
          </form>
        </Modal>
      )}
      {rename && board && (
        <Modal title="Đổi tên bảng Kanban" onClose={() => setRename(false)}>
          <form
            className="form-stack"
            onSubmit={(event) => {
              event.preventDefault();
              if (boardName.trim()) {
                change((b) => ({ ...b, name: boardName.trim() }));
                setRename(false);
              }
            }}
          >
            <label>
              Tên bảng
              <input
                autoFocus
                required
                maxLength={120}
                value={boardName}
                onChange={(e) => setBoardName(e.target.value)}
              />
            </label>
            <button className="button primary">Lưu tên</button>
          </form>
        </Modal>
      )}
    </>
  );
}
function QuickAdd({
  column,
  onAdd,
}: {
  column: KanbanColumn;
  onAdd: (title: string) => void;
}) {
  const [active, setActive] = useState(false),
    [title, setTitle] = useState("");
  return active ? (
    <form
      className="kb-quick-add"
      onSubmit={(event) => {
        event.preventDefault();
        if (title.trim()) {
          onAdd(title.trim());
          setTitle("");
        }
      }}
    >
      <input
        autoFocus
        aria-label={`Thẻ mới trong ${column.title}`}
        placeholder="Tên công việc hoặc sự kiện…"
        maxLength={160}
        value={title}
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            event.stopPropagation();
            setActive(false);
            setTitle("");
          }
        }}
      />
      <button
        type="submit"
        className="icon-button"
        disabled={!title.trim()}
        aria-label="Lưu thẻ mới"
      >
        <Check size={17} />
      </button>
      <button
        type="button"
        className="icon-button"
        aria-label="Hủy thêm thẻ"
        onClick={() => {
          setActive(false);
          setTitle("");
        }}
      >
        <X size={17} />
      </button>
    </form>
  ) : (
    <button className="kb-add-card" onClick={() => setActive(true)}>
      <Plus size={17} />
      Thêm thẻ
    </button>
  );
}
