import {
  CircleDot,
  CirclePlus,
  ClipboardList,
  Scan,
  RotateCcw,
  CircleCheck,
  CircleMinus,
  CircleX,
  CirclePause,
  Archive,
} from "lucide-react";

/** Stored values keep the original "To do" value for existing workspaces. */
export const TASK_STATUSES = [
  {
    value: "In progress",
    label: "In progress",
    tone: "in-progress",
    icon: CircleDot,
    help: "Work is actively underway.",
  },
  {
    value: "To do",
    label: "To-do",
    tone: "todo",
    icon: CirclePlus,
    help: "Planned and ready to pick up.",
  },
  {
    value: "In Review",
    label: "In Review",
    tone: "review",
    icon: ClipboardList,
    help: "The work is ready for a review.",
  },
  {
    value: "Design Review",
    label: "Design Review",
    tone: "design-review",
    icon: Scan,
    help: "A design decision needs feedback.",
  },
  {
    value: "Rework",
    label: "Rework",
    tone: "rework",
    icon: RotateCcw,
    help: "Changes are needed after feedback.",
  },
  {
    value: "Done",
    label: "Done",
    tone: "done",
    icon: CircleCheck,
    help: "The task is complete.",
  },
  {
    value: "Not Started",
    label: "Not Started",
    tone: "not-started",
    icon: CircleMinus,
    help: "The work has not started yet.",
  },
  {
    value: "Blocked",
    label: "Blocked",
    tone: "blocked",
    icon: CircleX,
    help: "A dependency prevents progress.",
  },
  {
    value: "On Hold",
    label: "On Hold",
    tone: "on-hold",
    icon: CirclePause,
    help: "Work is intentionally paused.",
  },
  {
    value: "Archived",
    label: "Archived",
    tone: "archived",
    icon: Archive,
    help: "Retained for reference; excluded from open work.",
  },
] as const;

export type TaskStatus = (typeof TASK_STATUSES)[number]["value"];
export type BoardLane = "To do" | "In progress" | "Done" | "Archived";
export function statusDefinition(status: TaskStatus) {
  return (
    TASK_STATUSES.find((item) => item.value === status) ?? TASK_STATUSES[1]
  );
}
export function taskLane(status: TaskStatus): BoardLane {
  if (status === "To do" || status === "Not Started") return "To do";
  if (status === "Done" || status === "Archived") return status;
  return "In progress";
}
export function isOpenTask(task: { status: TaskStatus }) {
  return task.status !== "Done" && task.status !== "Archived";
}
export function TaskStatusPill({ status }: { status: TaskStatus }) {
  const item = statusDefinition(status);
  const Icon = item.icon;
  return (
    <span className="task-status-pill" data-task-tag={item.tone}>
      <Icon size={13} />
      {item.label}
    </span>
  );
}
