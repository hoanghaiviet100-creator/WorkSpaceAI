import re
from datetime import date
from typing import Dict, List
from backend.core.schemas import (
    DateConflict,
    ReconciledItemReport,
    ReconciliationSummary,
    RequirementItem,
    TaskRecord,
)


def reconcile_requirements_and_tasks(
    requirements: List[RequirementItem],
    tasks: List[TaskRecord],
    t_now: date,
) -> ReconciliationSummary:
    """
    R2 Deterministic Capability #1:
    Matches official project requirements R against team task records T,
    calculates deadline deltas, detects date conflicts, and assigns risk levels.
    """
    task_map: Dict[str, List[TaskRecord]] = {}
    unmapped_tasks: List[TaskRecord] = []

    for t in tasks:
        if t.mapped_req_id:
            task_map.setdefault(t.mapped_req_id, []).append(t)
        else:
            unmapped_tasks.append(t)

    # Fallback deterministic keyword Jaccard matching (>= 0.45) for unmapped tasks
    for r in requirements:
        if r.req_id not in task_map and r.keywords:
            r_tokens = {w.lower() for w in r.keywords}
            for t in unmapped_tasks:
                t_tokens = set(re.findall(r"\w+", t.title.lower()))
                union_len = len(r_tokens | t_tokens)
                if union_len > 0 and (len(r_tokens & t_tokens) / union_len) >= 0.45:
                    task_map.setdefault(r.req_id, []).append(t)

    item_reports: List[ReconciledItemReport] = []
    covered_count = 0
    overdue_count = 0
    conflict_count = 0

    for r in requirements:
        matched = task_map.get(r.req_id, [])
        days_remaining = (r.official_deadline - t_now).days if r.official_deadline else None

        if not matched:
            is_urgent = r.mandatory_flag and (days_remaining is not None and days_remaining <= 7)
            item_reports.append(
                ReconciledItemReport(
                    req_id=r.req_id,
                    title=r.title,
                    state="UNTRACKED_MISSING",
                    risk_level="CRITICAL" if is_urgent else "HIGH",
                    avg_completion=0.0,
                    days_remaining=days_remaining,
                    owners=[],
                    date_conflicts=[],
                    citations=[r.source_ref],
                )
            )
            continue

        avg_comp = sum(t.completion_pct for t in matched) / len(matched)
        owners = sorted({t.owner for t in matched if t.owner})
        citations = [r.source_ref] + [t.source_ref for t in matched]
        conflicts: List[DateConflict] = []

        for t in matched:
            if r.official_deadline and t.logged_deadline and r.official_deadline != t.logged_deadline:
                conflicts.append(
                    DateConflict(
                        doc_a=r.source_ref,
                        date_a=r.official_deadline,
                        doc_b=t.source_ref,
                        date_b=t.logged_deadline,
                    )
                )

        if avg_comp >= 100.0:
            state = "COMPLETED"
            covered_count += 1
            risk_level = "LOW"
        elif days_remaining is not None and days_remaining < 0:
            state = "OVERDUE"
            overdue_count += 1
            risk_level = "CRITICAL"
        elif not owners:
            state = "UNASSIGNED"
            risk_level = "HIGH"
        else:
            state = "IN_PROGRESS"
            risk_level = "MEDIUM" if (days_remaining is not None and days_remaining <= 5) else "LOW"

        if conflicts:
            conflict_count += 1

        item_reports.append(
            ReconciledItemReport(
                req_id=r.req_id,
                title=r.title,
                state=state,
                risk_level=risk_level,
                avg_completion=round(avg_comp, 1),
                days_remaining=days_remaining,
                owners=owners,
                date_conflicts=conflicts,
                citations=citations,
            )
        )

    risk_priority = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    item_reports.sort(
        key=lambda x: (
            risk_priority.get(x.risk_level, 99),
            x.days_remaining if x.days_remaining is not None else 9999,
        )
    )

    coverage_ratio = round(covered_count / len(requirements), 4) if requirements else 1.0
    return ReconciliationSummary(
        coverage_ratio=coverage_ratio,
        overdue_count=overdue_count,
        conflict_count=conflict_count,
        item_reports=item_reports,
    )
