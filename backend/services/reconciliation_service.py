from datetime import date
from typing import Any, Dict, List, Optional
from backend.algorithms.reconciliation import reconcile_requirements_and_tasks
from backend.core.schemas import RequirementItem, RouteType, TaskRecord


def get_default_requirements() -> List[RequirementItem]:
    """Default CSC10014 project requirements for demonstration and evaluation."""
    return [
        RequirementItem(
            req_id="R1",
            title="Problem boundary & 10 use cases",
            keywords=["boundary", "use", "cases"],
            official_deadline=date(2026, 10, 20),
            mandatory_flag=True,
            source_ref="Project_Brief.pdf#p3",
        ),
        RequirementItem(
            req_id="R2",
            title="Deterministic capability & algorithms",
            keywords=["deterministic", "algorithm"],
            official_deadline=date(2026, 10, 24),
            mandatory_flag=True,
            source_ref="Project_Brief.pdf#p3",
        ),
        RequirementItem(
            req_id="R8",
            title="Evaluation benchmark & improvement cycle",
            keywords=["evaluation", "benchmark"],
            official_deadline=date(2026, 11, 15),
            mandatory_flag=True,
            source_ref="Project_Brief.pdf#p3",
        ),
    ]


def get_default_tasks() -> List[TaskRecord]:
    """Default team task records for demonstration and evaluation."""
    return [
        TaskRecord(
            task_id="T-01",
            mapped_req_id="R1",
            title="Define problem boundary and 10 use cases",
            owner="Minh",
            status="COMPLETED",
            logged_deadline=date(2026, 10, 20),
            completion_pct=100.0,
            source_ref="team_tasks.csv#row1",
        ),
        TaskRecord(
            task_id="T-02",
            mapped_req_id="R2",
            title="Implement deterministic reconciliation engine",
            owner="Lan",
            status="IN_PROGRESS",
            logged_deadline=date(2026, 10, 28),  # Intentional conflict with Oct 24
            completion_pct=60.0,
            source_ref="team_tasks.csv#row2",
        ),
    ]


class ReconciliationService:
    """Nghiệp vụ đối chiếu yêu cầu đề bài và task nhóm."""

    def reconcile(
        self,
        reference_date: date,
        requirements: Optional[List[RequirementItem]] = None,
        tasks: Optional[List[TaskRecord]] = None,
    ) -> Dict[str, Any]:
        reqs = requirements if requirements is not None else get_default_requirements()
        t_list = tasks if tasks is not None else get_default_tasks()

        report = reconcile_requirements_and_tasks(reqs, t_list, reference_date)
        return {
            "route": RouteType.RECONCILE_FLOW,
            "status": "RECONCILIATION_COMPLETE",
            "reconciliation_report": report,
        }


# Singleton instance
reconciliation_service = ReconciliationService()


def handle_reconciliation_request(reference_date: date) -> Dict[str, Any]:
    return reconciliation_service.reconcile(reference_date=reference_date)
