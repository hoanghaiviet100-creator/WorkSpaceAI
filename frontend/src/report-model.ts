import type { Workspace } from "./data";
import type { ReconciliationState } from "./schema";
import type { ServerReport } from "./api";
export const reconciliationStates: Record<ReconciliationState, string> = {
  FULLY_COVERED: "Fully covered",
  PARTIALLY_COVERED: "Partially covered",
  NOT_COVERED: "Not covered",
  OVERDUE: "Overdue",
  DEADLINE_CONFLICT: "Deadline conflict",
};
/** Translate existing R2 response names to the SQL enum; calculations stay in Python. */
export function reportState(
  state: string,
  conflict: boolean,
): ReconciliationState {
  if (Object.hasOwn(reconciliationStates, state))
    return state as ReconciliationState;
  if (state === "COMPLETED") return "FULLY_COVERED";
  if (state === "OVERDUE") return "OVERDUE";
  if (state === "UNTRACKED_MISSING") return "NOT_COVERED";
  if (state === "IN_PROGRESS" || state === "UNASSIGNED")
    return conflict ? "DEADLINE_CONFLICT" : "PARTIALLY_COVERED";
  throw new Error(`Unsupported reconciliation state: ${state}`);
}
export function appendReport(
  w: Workspace,
  report: ServerReport,
  referenceDate: string,
): Workspace {
  if (
    !Array.isArray(report.item_reports) ||
    !Number.isFinite(report.coverage_ratio) ||
    report.coverage_ratio < 0 ||
    report.coverage_ratio > 1 ||
    !Number.isInteger(report.overdue_count) ||
    report.overdue_count < 0 ||
    !Number.isInteger(report.conflict_count) ||
    report.conflict_count < 0
  )
    throw new Error("Invalid reconciliation report.");
  const runId = crypto.randomUUID();
  const ids = new Set<string>();
  for (const item of report.item_reports) {
    if (
      !item.req_id ||
      ids.has(item.req_id) ||
      !["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(item.risk_level) ||
      !Number.isFinite(item.avg_completion) ||
      item.avg_completion < 0 ||
      item.avg_completion > 100 ||
      !(
        item.days_remaining === null || Number.isInteger(item.days_remaining)
      ) ||
      !Array.isArray(item.owners) ||
      !Array.isArray(item.citations) ||
      !Array.isArray(item.date_conflicts)
    )
      throw new Error("Invalid requirement result in server report.");
    ids.add(item.req_id);
  }
  const items = report.item_reports.map((r, index) => ({
    ...r,
    id: Math.max(0, ...(w.reconciledItems ?? []).map((i) => i.id)) + index + 1,
    run_id: runId,
    state: reportState(r.state, (r.date_conflicts ?? []).length > 0),
    serverState: r.state,
    date_conflicts: r.date_conflicts ?? [],
    citations: r.citations ?? [],
    owners: r.owners ?? [],
  }));
  return {
    ...w,
    reconciliationRuns: [
      ...(w.reconciliationRuns ?? []),
      {
        run_id: runId,
        reference_date: referenceDate,
        coverage_ratio: report.coverage_ratio,
        total_requirements: items.length,
        covered_requirements: items.filter((i) => i.state === "FULLY_COVERED")
          .length,
        overdue_count: report.overdue_count,
        conflict_count: report.conflict_count,
        executed_at: new Date().toISOString(),
        origin: "server",
      },
    ],
    reconciledItems: [...(w.reconciledItems ?? []), ...items],
  };
}
