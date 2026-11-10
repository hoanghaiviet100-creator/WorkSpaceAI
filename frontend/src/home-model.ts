import type { Mode, Thread, Workspace } from "./data";

export const WORKSPACE_COLORS = [
  "blue",
  "teal",
  "amber",
  "olive",
  "slate",
  "orange",
] as const;
export type WorkspaceColor = (typeof WORKSPACE_COLORS)[number];
export type ConversationRow = { workspace: Workspace; thread: Thread };

export function isWorkspaceColor(value: unknown): value is WorkspaceColor {
  return WORKSPACE_COLORS.includes(value as WorkspaceColor);
}

function colorOffset(id: string) {
  let value = 2166136261;
  for (const character of id)
    value = Math.imul(value ^ character.charCodeAt(0), 16777619);
  return (value >>> 0) % WORKSPACE_COLORS.length;
}

/** Persist one identity per workspace; never reshuffle existing identities on render. */
export function assignWorkspaceColors(workspaces: Workspace[]): Workspace[] {
  const usage = new Map<WorkspaceColor, number>(
    WORKSPACE_COLORS.map((color) => [color, 0]),
  );
  for (const workspace of workspaces)
    if (isWorkspaceColor(workspace.color))
      usage.set(workspace.color, usage.get(workspace.color)! + 1);
  return workspaces.map((workspace) => {
    if (isWorkspaceColor(workspace.color)) return workspace;
    const minimum = Math.min(...usage.values());
    const offset = colorOffset(workspace.id);
    const color = WORKSPACE_COLORS.map(
      (_, index) =>
        WORKSPACE_COLORS[(offset + index) % WORKSPACE_COLORS.length],
    ).find((candidate) => usage.get(candidate) === minimum)!;
    usage.set(color, usage.get(color)! + 1);
    return { ...workspace, color };
  });
}

export function workspaceColor(workspace: Workspace): WorkspaceColor {
  return isWorkspaceColor(workspace.color)
    ? workspace.color
    : WORKSPACE_COLORS[colorOffset(workspace.id)];
}

/** Recent workspaces follow their actual latest workspace/conversation timestamp. */
export function workspaceHistory(workspaces: Workspace[]) {
  return workspaces
    .map((workspace) => {
      const threads = [...workspace.threads].sort(
        (a, b) => (Date.parse(b.updated) || 0) - (Date.parse(a.updated) || 0),
      );
      const timestamp = Math.max(
        Date.parse(workspace.updated) || 0,
        Date.parse(threads[0]?.updated ?? "") || 0,
      );
      return {
        workspace,
        thread: threads[0],
        timestamp,
        updated: timestamp ? new Date(timestamp).toISOString() : "",
      };
    })
    .sort(
      (a, b) =>
        b.timestamp - a.timestamp ||
        a.workspace.id.localeCompare(b.workspace.id),
    );
}

export function conversationRows(
  workspaces: Workspace[],
  scope: string | null = null,
  mode: Mode | null = null,
  query = "",
): ConversationRow[] {
  const normalize = (text: string) =>
    text
      .normalize("NFD")
      .replace(/\p{M}/gu, "")
      .replace(/[đĐ]/g, "d")
      .toLowerCase();
  const needle = normalize(query.trim());
  return workspaces
    .filter((workspace) => !scope || workspace.id === scope)
    .flatMap((workspace) =>
      workspace.threads.map((thread) => ({ workspace, thread })),
    )
    .filter(
      ({ workspace, thread }) =>
        (!mode || thread.mode === mode) &&
        (!needle ||
          normalize(
            `${workspace.name} ${thread.title} ${thread.messages.map((message) => message.request).join(" ")}`,
          ).includes(needle)),
    )
    .sort(
      (a, b) =>
        (Date.parse(b.thread.updated) || 0) -
          (Date.parse(a.thread.updated) || 0) ||
        a.workspace.id.localeCompare(b.workspace.id) ||
        a.thread.id.localeCompare(b.thread.id),
    );
}

/** A historical source trail must describe the exchange, not today's checkbox selection. */
export function conversationSources(workspace: Workspace, thread: Thread) {
  const latest = thread.messages.at(-1);
  const ids = [
    ...new Set(latest?.sourceIds ?? thread.handoff?.sourceIds ?? []),
  ];
  const sources = ids
    .map((id) => workspace.sources.find((source) => source.id === id))
    .filter((source) => source !== undefined);
  return { sources, missing: ids.length - sources.length };
}

export function activityLabel(value: string, now = new Date()) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  const day = (input: Date) =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Bangkok",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(input);
  if (day(date) === day(now)) return "Today";
  if (day(date) === day(new Date(now.getTime() - 86400000))) return "Yesterday";
  return date.toLocaleDateString("en-US", {
    timeZone: "Asia/Bangkok",
    month: "short",
    day: "numeric",
    ...(date.getFullYear() !== now.getFullYear() ? { year: "numeric" } : {}),
  });
}

/** Home metrics, deadlines and progress share the same scoped, non-archived task rows. */
export function dashboardData(
  workspaces: Workspace[],
  scope: string | null = null,
  now = new Date(),
) {
  const projects = workspaces.filter(
    (workspace) => !scope || workspace.id === scope,
  );
  const tasks = projects.flatMap((workspace) =>
    workspace.tasks
      .filter((task) => !task.archived)
      .map((task) => ({ workspace, task })),
  );
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Bangkok",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const dated = tasks
    .filter(({ task }) => {
      if (task.status === "DONE" || !/^\d{4}-\d{2}-\d{2}$/.test(task.due))
        return false;
      const date = new Date(`${task.due}T12:00:00Z`);
      return (
        Number.isFinite(date.getTime()) &&
        date.toISOString().slice(0, 10) === task.due
      );
    })
    .sort(
      (a, b) =>
        a.task.due.localeCompare(b.task.due) ||
        a.task.id.localeCompare(b.task.id),
    );
  return {
    open: tasks.filter(({ task }) => task.status !== "DONE").length,
    inProgress: tasks.filter(({ task }) => task.status === "IN_PROGRESS")
      .length,
    done: tasks.filter(({ task }) => task.status === "DONE").length,
    documents: projects.reduce(
      (sum, workspace) => sum + workspace.sources.length,
      0,
    ),
    overdue: dated.filter(({ task }) => task.due < today).length,
    today,
    deadlines: dated.map((row) => ({ ...row, overdue: row.task.due < today })),
    progress: projects.map((workspace) => {
      const active = workspace.tasks.filter((task) => !task.archived);
      const complete = active.filter((task) => task.status === "DONE").length;
      return {
        workspace,
        complete,
        total: active.length,
        percent: active.length
          ? Math.round((complete / active.length) * 100)
          : null,
      };
    }),
    recent: conversationRows(projects),
    resume: conversationRows(projects, null, "Ask").find(
      ({ thread }) => thread.messages.length > 0,
    ),
  };
}
