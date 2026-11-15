import type { Workspace } from "./data";

export const WORKSPACE_COLORS = [
  "blue",
  "teal",
  "amber",
  "olive",
  "slate",
  "orange",
] as const;
export type WorkspaceColor = (typeof WORKSPACE_COLORS)[number];

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
