"""
backend/algorithms/reconciliation.py
R2 Deterministic Capability #1: Cross-Document Requirements Reconciliation.
100% Python Standard Library Only (Zero third-party imports).
"""
from dataclasses import dataclass, field
from datetime import date
import re
from typing import Any, Dict, List, Optional


@dataclass
class DateConflict:
    doc_a: str
    date_a: date
    doc_b: str
    date_b: date


@dataclass
class ReconciledItemReport:
    req_id: str
    title: str
    state: str
    risk_level: str
    avg_completion: float
    days_remaining: Optional[int]
    owners: List[str] = field(default_factory=list)
    date_conflicts: List[DateConflict] = field(default_factory=list)
    citations: List[str] = field(default_factory=list)


@dataclass
class ReconciliationSummary:
    coverage_ratio: float
    overdue_count: int
    conflict_count: int
    item_reports: List[ReconciledItemReport] = field(default_factory=list)

    @property
    def total_requirements(self) -> int:
        return len(self.item_reports)


def reconcile_requirements_and_tasks(
    requirements: List[Any],
    tasks: List[Any],
    t_now: date,
) -> ReconciliationSummary:
    """
    R2 Deterministic Capability #1:
    Matches official project requirements R against team task records T,
    calculates deadline deltas, detects date conflicts, and assigns risk levels.
    """
    task_map: Dict[str, List[Any]] = {}
    unmapped_tasks: List[Any] = []

    for t in tasks:
        mapped_req = getattr(t, "mapped_req_id", None)
        if mapped_req:
            task_map.setdefault(mapped_req, []).append(t)
        else:
            unmapped_tasks.append(t)

    # Fallback deterministic keyword Jaccard matching (>= 0.45) for unmapped tasks
    for r in requirements:
        req_id = getattr(r, "req_id", "")
        keywords = getattr(r, "keywords", [])
        if req_id not in task_map and keywords:
            r_tokens = {w.lower() for w in keywords}
            for t in unmapped_tasks:
                t_title = getattr(t, "title", "")
                t_tokens = set(re.findall(r"\w+", t_title.lower()))
                union_len = len(r_tokens | t_tokens)
                if union_len > 0 and (len(r_tokens & t_tokens) / union_len) >= 0.45:
                    task_map.setdefault(req_id, []).append(t)

    item_reports: List[ReconciledItemReport] = []
    covered_count = 0
    overdue_count = 0
    conflict_count = 0

    for r in requirements:
        req_id = getattr(r, "req_id", "")
        title = getattr(r, "title", "")
        official_deadline = getattr(r, "official_deadline", None)
        mandatory_flag = getattr(r, "mandatory_flag", True)
        source_ref = getattr(r, "source_ref", "")

        matched = task_map.get(req_id, [])
        days_remaining = (official_deadline - t_now).days if official_deadline else None

        if not matched:
            is_urgent = mandatory_flag and (days_remaining is not None and days_remaining <= 7)
            item_reports.append(
                ReconciledItemReport(
                    req_id=req_id,
                    title=title,
                    state="UNTRACKED_MISSING",
                    risk_level="CRITICAL" if is_urgent else "HIGH",
                    avg_completion=0.0,
                    days_remaining=days_remaining,
                    owners=[],
                    date_conflicts=[],
                    citations=[source_ref],
                )
            )
            continue

        avg_comp = sum(getattr(t, "completion_pct", 0.0) for t in matched) / len(matched)
        owners = sorted({getattr(t, "owner", "") for t in matched if getattr(t, "owner", None)})
        citations = [source_ref] + [getattr(t, "source_ref", "") for t in matched]
        conflicts: List[DateConflict] = []

        for t in matched:
            t_logged_deadline = getattr(t, "logged_deadline", None)
            t_source_ref = getattr(t, "source_ref", "")
            if official_deadline and t_logged_deadline and official_deadline != t_logged_deadline:
                conflicts.append(
                    DateConflict(
                        doc_a=source_ref,
                        date_a=official_deadline,
                        doc_b=t_source_ref,
                        date_b=t_logged_deadline,
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
                req_id=req_id,
                title=title,
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
