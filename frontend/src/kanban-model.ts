import type { Task, Workspace } from "./data";
import type { TaskStatus } from "./task-status";

export type Priority = "none" | "low" | "medium" | "high";
export type LabelTone = "neutral" | "orange" | "teal" | "rose";
export type KanbanColumn = { id: string; title: string; status: TaskStatus };
export type KanbanCard = {
  id: string;
  taskId: string;
  columnId: string;
  title: string;
  description: string;
  kind: "task" | "event";
  startDate: string;
  dueDate: string;
  priority: Priority;
  labels: { name: string; tone: LabelTone }[];
  checklist: { id: string; text: string; done: boolean }[];
  sourceIds: string[];
  notes: string;
  origin: "ai" | "manual";
  createdAt: string;
  updatedAt: string;
};
export type KanbanBoard = {
  id: string;
  name: string;
  columns: KanbanColumn[];
  cards: KanbanCard[];
  createdAt: string;
  updatedAt: string;
  initialSuggestionConfirmedAt: string;
};
export type KanbanProposal = {
  id: string;
  boardId?: string;
  name: string;
  mode: "initial" | "append";
  columns: (KanbanColumn & { selected: boolean })[];
  cards: (KanbanCard & { selected: boolean })[];
  engine: "offline" | "demo";
  contextNote: string;
  sourceIds: string[];
};
export const id = () => crypto.randomUUID();
export const now = () => new Date().toISOString();
export function localDay(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
export function validDate(value: string) {
  return (
    /^\d{4}-\d{2}-\d{2}$/.test(value) &&
    !Number.isNaN(Date.parse(value)) &&
    new Date(value).toISOString().slice(0, 10) === value
  );
}
export function explicitDate(text: string) {
  const dates: { index: number; value: string }[] = [];
  for (const match of text.matchAll(/\b\d{4}-\d{2}-\d{2}\b/g))
    dates.push({ index: match.index!, value: match[0] });
  for (const match of text.matchAll(/\b(\d{1,2})[\/.](\d{1,2})[\/.](\d{4})\b/g))
    dates.push({
      index: match.index!,
      value: `${match[3]}-${match[2].padStart(2, "0")}-${match[1].padStart(2, "0")}`,
    });
  const months = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
  ];
  for (const match of text.matchAll(
    /\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b/gi,
  ))
    dates.push({
      index: match.index!,
      value: `${match[3]}-${String(months.indexOf(match[1].toLowerCase()) + 1).padStart(2, "0")}-${match[2].padStart(2, "0")}`,
    });
  return (
    dates
      .sort((a, b) => a.index - b.index)
      .find((date) => validDate(date.value))?.value || ""
  );
}
export function newCard(
  columnId: string,
  title: string,
  origin: "ai" | "manual" = "manual",
): KanbanCard {
  const key = id(),
    stamp = now();
  return {
    id: key,
    taskId: `kanban-${key}`,
    columnId,
    title: title.trim(),
    description: "",
    kind: "task",
    startDate: "",
    dueDate: "",
    priority: "none",
    labels: [],
    checklist: [],
    sourceIds: [],
    notes: "",
    origin,
    createdAt: stamp,
    updatedAt: stamp,
  };
}
export const initialColumns = (): KanbanColumn[] => [
  { id: id(), title: "Cần làm", status: "TODO" },
  { id: id(), title: "Đang làm", status: "IN_PROGRESS" },
  { id: id(), title: "Hoàn thành", status: "DONE" },
];
const key = (text: string) =>
  text.normalize("NFKC").trim().toLocaleLowerCase().replace(/\s+/g, " ");

/** Existing task edits remain visible; card-only metadata and manual column order stay intact. */
export function workspaceBoard(workspace: Workspace): KanbanBoard | undefined {
  const board = workspace.kanban;
  if (!board) return undefined;
  const tasks = new Map(workspace.tasks.map((task) => [task.id, task]));
  return {
    ...board,
    cards: board.cards
      .filter((card) => !tasks.get(card.taskId)?.archived)
      .map((card) => {
        const task = tasks.get(card.taskId);
        if (!task) return card;
        const column = board.columns.find((col) => col.id === card.columnId);
        return {
          ...card,
          title: task.title,
          description: task.description,
          dueDate: validDate(task.due) ? task.due : "",
          columnId:
            column?.status === task.status
              ? card.columnId
              : board.columns.find((col) => col.status === task.status)?.id ||
                card.columnId,
        };
      }),
  };
}

/** Update only tasks represented by this board, preserving schema fields and unrelated tasks. */
export function saveBoard(workspace: Workspace, board: KanbanBoard): Workspace {
  if (workspace.kanban && workspace.kanban.id !== board.id)
    throw Error("Workspace đã có một bảng Kanban.");
  if (!board.columns.length || board.columns.some((col) => !col.title.trim()))
    throw Error("Bảng cần ít nhất một cột có tên.");
  if (
    new Set(board.columns.map((col) => col.id)).size !== board.columns.length ||
    new Set(board.cards.map((card) => card.id)).size !== board.cards.length
  )
    throw Error("Dữ liệu Kanban có ID trùng.");
  if (
    board.cards.some(
      (card) =>
        !card.title.trim() ||
        !board.columns.some((col) => col.id === card.columnId) ||
        (card.dueDate && !validDate(card.dueDate)) ||
        (card.startDate && !validDate(card.startDate)) ||
        (card.startDate && card.dueDate && card.startDate > card.dueDate),
    )
  )
    throw Error("Kiểm tra tiêu đề, cột và khoảng ngày của thẻ.");
  const stamp = now();
  const cards = board.cards.map((card) => ({
    ...card,
    title: card.title.trim(),
  }));
  const tasks = new Map(workspace.tasks.map((task) => [task.id, task]));
  const removed = new Set(
    (workspace.kanban?.cards || [])
      .filter((card) => !cards.some((next) => next.taskId === card.taskId))
      .map((card) => card.taskId),
  );
  for (const taskId of removed) {
    const task = tasks.get(taskId);
    if (task) tasks.set(taskId, { ...task, archived: true, updatedAt: stamp });
  }
  for (const card of cards) {
    const previous = tasks.get(card.taskId);
    const status = board.columns.find(
      (col) => col.id === card.columnId,
    )!.status;
    const task: Task = {
      ...previous,
      id: card.taskId,
      title: card.title,
      description: card.description,
      due: card.dueDate,
      status,
      owner: previous?.owner || "",
      initials: previous?.initials || "?",
      completionPct:
        status === "DONE"
          ? 100
          : previous?.status === "DONE"
            ? 0
            : previous?.completionPct || 0,
      archived: false,
      createdAt: previous?.createdAt || card.createdAt,
      updatedAt: stamp,
    };
    tasks.set(task.id, task);
  }
  return {
    ...workspace,
    updated: stamp,
    kanban: { ...board, cards, updatedAt: stamp },
    tasks: [...tasks.values()],
  };
}
export function selectedProposal(proposal: KanbanProposal) {
  const columns = proposal.columns.filter(
    (col) => col.selected && col.title.trim(),
  );
  const cards = proposal.cards.filter(
    (card) =>
      card.selected &&
      card.title.trim() &&
      columns.some((col) => col.id === card.columnId),
  );
  return {
    columns: columns.map(({ selected: _, ...col }) => col),
    cards: cards.map(({ selected: _, ...card }) => card),
  };
}
/** Confirmation is the sole path that creates a board or appends generated cards. */
export function confirmProposal(
  workspace: Workspace,
  proposal: KanbanProposal,
): Workspace {
  const selection = selectedProposal(proposal),
    current = workspaceBoard(workspace);
  if (!selection.columns.length || !selection.cards.length)
    throw Error("Chọn ít nhất một cột và một thẻ hợp lệ để xác nhận.");
  if (proposal.mode === "initial" && current)
    throw Error("Workspace đã có bảng. Hãy dùng Nhờ AI gợi ý thêm.");
  if (
    proposal.mode === "append" &&
    (!current || current.id !== proposal.boardId)
  )
    throw Error("Bảng đã thay đổi. Hãy tạo lại bản gợi ý.");
  const added = selection.cards.filter(
    (card) =>
      !current?.cards.some(
        (old) =>
          old.taskId === card.taskId || key(old.title) === key(card.title),
      ),
  );
  if (!added.length)
    throw Error("Các thẻ đã tồn tại trong bảng. Không có thẻ mới để thêm.");
  if (
    current &&
    added.some(
      (card) => !current.columns.some((col) => col.id === card.columnId),
    )
  )
    throw Error("Cột đã bị xóa. Hãy tạo lại bản gợi ý.");
  const stamp = now();
  const board: KanbanBoard = current
    ? { ...current, cards: [...current.cards, ...added] }
    : {
        id: id(),
        name: proposal.name.trim() || "Kế hoạch workspace",
        columns: selection.columns,
        cards: added,
        createdAt: stamp,
        updatedAt: stamp,
        initialSuggestionConfirmedAt: stamp,
      };
  const saved = saveBoard(workspace, board);
  const thread = saved.threads[0];
  return {
    ...saved,
    threads: thread
      ? [
          {
            ...thread,
            updated: stamp,
            messages: [
              ...thread.messages,
              {
                id: id(),
                request: "",
                mode: "Ask",
                state: "answer",
                at: stamp,
                sourceIds: proposal.sourceIds,
                evidenceIds: [],
                kanbanEvent: {
                  boardId: board.id,
                  count: added.length,
                  initial: !current,
                },
              },
            ],
          },
          ...saved.threads.slice(1),
        ]
      : saved.threads,
  };
}
export function moveCard(
  board: KanbanBoard,
  cardId: string,
  columnId: string,
  beforeId?: string,
): KanbanBoard {
  if (!board.columns.some((col) => col.id === columnId) || cardId === beforeId)
    return board;
  const card = board.cards.find((card) => card.id === cardId);
  if (!card) return board;
  const cards = board.cards.filter((card) => card.id !== cardId);
  const next = { ...card, columnId, updatedAt: now() };
  const before = beforeId
    ? cards.findIndex(
        (card) => card.id === beforeId && card.columnId === columnId,
      )
    : -1;
  if (before >= 0) cards.splice(before, 0, next);
  else cards.push(next);
  return { ...board, cards };
}
export function reorderColumn(
  board: KanbanBoard,
  columnId: string,
  beforeId?: string,
) {
  if (columnId === beforeId) return board;
  const column = board.columns.find((col) => col.id === columnId);
  if (!column) return board;
  const columns = board.columns.filter((col) => col.id !== columnId);
  const before = columns.findIndex((col) => col.id === beforeId);
  columns.splice(before < 0 ? columns.length : before, 0, column);
  return { ...board, columns };
}
export function dueState(card: KanbanCard, done: boolean, today = localDay()) {
  if (done || !validDate(card.dueDate)) return "none";
  if (card.dueDate < today) return "overdue";
  const distance = (Date.parse(card.dueDate) - Date.parse(today)) / 86400000;
  return distance <= 3 ? "soon" : "normal";
}
export function boardSummary(board: KanbanBoard) {
  const done = board.cards.filter((card) =>
    board.columns.some(
      (col) => col.id === card.columnId && col.status === "DONE",
    ),
  ).length;
  const upcoming = board.cards
    .filter(
      (card) =>
        card.dueDate &&
        board.columns.find((col) => col.id === card.columnId)?.status !==
          "DONE",
    )
    .map((card) => card.dueDate)
    .sort()[0];
  return {
    done,
    total: board.cards.length,
    percent: board.cards.length
      ? Math.round((done / board.cards.length) * 100)
      : 0,
    upcoming,
  };
}
