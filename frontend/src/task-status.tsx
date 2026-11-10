import {
  CircleDot,
  CirclePlus,
  ClipboardList,
  CircleCheck,
} from "lucide-react";
import type { TaskState } from "./schema";

export const TASK_STATUSES = [
  {
    value: "TODO",
    label: "To-do",
    tone: "todo",
    icon: CirclePlus,
    help: "Planned and ready to pick up.",
  },
  {
    value: "IN_PROGRESS",
    label: "In progress",
    tone: "in-progress",
    icon: CircleDot,
    help: "Work is actively underway.",
  },
  {
    value: "REVIEW",
    label: "In Review",
    tone: "review",
    icon: ClipboardList,
    help: "The work is ready for review.",
  },
  {
    value: "DONE",
    label: "Done",
    tone: "done",
    icon: CircleCheck,
    help: "The task is complete.",
  },
] as const;
/** Additional labels are UI metadata, separate from tasks.status in SQL. */
export const LOCAL_TASK_LABELS = [
  "Not Started",
  "Design Review",
  "Rework",
  "Blocked",
  "On Hold",
] as const;
export type TaskStatus = TaskState;
export type BoardLane =
  "To do" | "In progress" | "In Review" | "Done" | "Archived";
export function statusDefinition(status: TaskStatus) {
  return (
    TASK_STATUSES.find((item) => item.value === status) ?? TASK_STATUSES[0]
  );
}
export function taskLane(status: TaskStatus, archived = false): BoardLane {
  if (archived) return "Archived";
  if (status === "TODO") return "To do";
  if (status === "REVIEW") return "In Review";
  if (status === "DONE") return "Done";
  return "In progress";
}
export function isOpenTask(task: { status: TaskStatus; archived?: boolean }) {
  return task.status !== "DONE" && !task.archived;
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
