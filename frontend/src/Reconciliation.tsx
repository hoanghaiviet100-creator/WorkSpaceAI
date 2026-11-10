import { useState } from "react";
import { RefreshCw, AlertTriangle } from "lucide-react";
import type { Workspace } from "./data";
import type { ReconciliationState } from "./schema";
import { apiFor, reconcile, type ServerReport } from "./api";
import { Badge, Notice } from "./components";

import { reconciliationStates as states, appendReport } from "./report-model";
export default function Reconciliation({
  workspace,
  update,
}: {
  workspace: Workspace;
  update: (fn: (w: Workspace) => Workspace) => void;
}) {
  const [referenceDate, setReferenceDate] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
  });
  const [selectedId, setSelectedId] = useState("");
  const [filter, setFilter] = useState("All results");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const runs = workspace.reconciliationRuns ?? [];
  const run = runs.find((r) => r.run_id === selectedId) ?? runs.at(-1);
  const items = (workspace.reconciledItems ?? []).filter(
    (r) => r.run_id === run?.run_id,
  );
  const connected = apiFor(workspace.id);
  return (
    <div className="reconciliation-screen">
      <div className="review-intro">
        <div>
          <h2>Requirements reconciliation</h2>
          <p>
            Compare coverage, progress and deadlines against official
            requirements.
          </p>
        </div>
        <Badge>
          {connected ? "Server calculation" : "Server not connected"}
        </Badge>
      </div>
      <Notice tone="neutral">
        This report uses the server’s requirements and tasks. Local board edits
        are not included. Report snapshots are saved on this device.
      </Notice>
      <form
        className="schema-toolbar"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!connected || pending || !referenceDate) return;
          setPending(true);
          setError("");
          try {
            const report = await reconcile(referenceDate, workspace.id);
            // Validate before the React state updater so a malformed response cannot crash rendering.
            const next = appendReport(workspace, report, referenceDate);
            const addedRun = next.reconciliationRuns!.at(-1)!;
            const addedItems = next.reconciledItems!.filter(
              (i) => i.run_id === addedRun.run_id,
            );
            update((w) => ({
              ...w,
              reconciliationRuns: [...(w.reconciliationRuns ?? []), addedRun],
              reconciledItems: [...(w.reconciledItems ?? []), ...addedItems],
            }));
            setSelectedId(addedRun.run_id);
          } catch (err) {
            setError(
              err instanceof Error
                ? err.message
                : "The report could not be generated.",
            );
          } finally {
            setPending(false);
          }
        }}
      >
        <label>
          Reference date
          <input
            type="date"
            required
            value={referenceDate}
            onChange={(e) => setReferenceDate(e.target.value)}
          />
        </label>
        <button className="button primary" disabled={!connected || pending}>
          <RefreshCw size={14} />
          {pending ? "Reconciling…" : "Run reconciliation"}
        </button>
      </form>
      {error && (
        <Notice tone="danger">{error} The previous report is kept.</Notice>
      )}
      {!run ? (
        <div className="empty-slot">
          <h3>No reconciliation runs yet</h3>
          <p>
            {connected
              ? "Choose a reference date and run reconciliation."
              : "Connect the backend to calculate an authoritative report."}
          </p>
        </div>
      ) : (
        <>
          <div className="schema-toolbar">
            <label>
              Run history
              <select
                aria-label="Reconciliation history"
                value={run.run_id}
                onChange={(e) => setSelectedId(e.target.value)}
              >
                {[...runs].reverse().map((r) => (
                  <option value={r.run_id} key={r.run_id}>
                    {r.reference_date} ·{" "}
                    {new Date(r.executed_at).toLocaleString()}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Result
              <select
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
              >
                <option>All results</option>
                {Object.entries(states).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="reconciliation-metrics">
            <div>
              <span>Requirement coverage</span>
              <strong>
                {run.total_requirements
                  ? `${Math.round(run.coverage_ratio * 100)}%`
                  : "—"}
              </strong>
              <small>
                {run.covered_requirements} of {run.total_requirements} fully
                covered
              </small>
            </div>
            <div>
              <span>Overdue</span>
              <strong>{run.overdue_count}</strong>
              <small>At {run.reference_date}</small>
            </div>
            <div>
              <span>Deadline conflicts</span>
              <strong>{run.conflict_count}</strong>
              <small>Requirements with conflicting dates</small>
            </div>
          </div>
          <p className="small muted">
            Requirement coverage is calculated by the server and differs from
            the board’s completed-task count.
          </p>
          <div className="reconciliation-list">
            {items
              .filter((i) => filter === "All results" || i.state === filter)
              .map((i) => (
                <article className="requirement-row" key={i.id}>
                  <div className="requirement-main">
                    <div className="schema-meta">
                      <span>{i.req_id}</span>
                      <Badge
                        tone={
                          i.risk_level === "CRITICAL" || i.risk_level === "HIGH"
                            ? "danger"
                            : "neutral"
                        }
                      >
                        {i.risk_level} risk
                      </Badge>
                      <Badge
                        tone={
                          i.state === "FULLY_COVERED" ? "document" : "warning"
                        }
                      >
                        {states[i.state]}
                      </Badge>
                    </div>
                    <h3>{i.title || i.req_id}</h3>
                    <p>
                      {i.avg_completion}% average completion ·{" "}
                      {i.days_remaining === null
                        ? "No official deadline"
                        : i.days_remaining < 0
                          ? `${Math.abs(i.days_remaining)} days overdue`
                          : `${i.days_remaining} days remaining`}
                    </p>
                    <p className="small">
                      Owners:{" "}
                      {i.owners.length ? i.owners.join(", ") : "Unassigned"}
                    </p>
                    {i.date_conflicts.map((c, n) => (
                      <div className="notice warning" key={n}>
                        <AlertTriangle size={14} />
                        <div>
                          {c.doc_a}: {c.date_a}
                          <br />
                          {c.doc_b}: {c.date_b}
                        </div>
                      </div>
                    ))}
                    {i.citations.length > 0 && (
                      <p className="small muted">
                        Sources: {i.citations.filter(Boolean).join(" · ")}
                      </p>
                    )}
                  </div>
                </article>
              ))}
          </div>
          {items.every(
            (i) => filter !== "All results" && i.state !== filter,
          ) && <div className="empty-slot">No results for this filter.</div>}
        </>
      )}
    </div>
  );
}
