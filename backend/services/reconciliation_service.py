from datetime import date
import re
from typing import Any, Dict, List, Optional
from backend.algorithms.reconciliation import reconcile_requirements_and_tasks
from backend.core.schemas import RequirementItem, RouteType, TaskRecord


# Export alias
RequirementRecord = RequirementItem


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


def extract_requirements_from_workspace(
    doc_ids: Optional[List[str]] = None,
    repository: Optional[Any] = None,
) -> List[RequirementItem]:
    """
    R2/Feature 2 Dynamic Requirement Extraction:
    Scans ingested document chunks in workspace to automatically detect requirement codes
    (R1, R2, REQ-01), deliverables, and official deadlines with source provenance.
    Falls back gracefully to default requirements if no structured items found.
    """
    from backend.repositories.workspace_repository import workspace_repository
    repo = repository or workspace_repository

    if not repo.chunks:
        return get_default_requirements()

    # Filter target chunks by doc_ids or active selections
    if doc_ids:
        target_ids = {d.strip().lower() for d in doc_ids}
        eligible_chunks = [
            c for c in repo.chunks
            if c.doc_id.lower() in target_ids or c.doc_name.lower() in target_ids
        ]
    else:
        selected_ids = set(repo.get_selected_doc_ids())
        if selected_ids:
            eligible_chunks = [
                c for c in repo.chunks
                if c.doc_id in selected_ids or c.doc_name in selected_ids
            ]
        else:
            eligible_chunks = repo.chunks

    if not eligible_chunks:
        eligible_chunks = repo.chunks

    extracted: List[RequirementItem] = []
    seen_req_ids = set()

    date_pattern = re.compile(
        r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b|\b(\d{4})[-/](\d{1,2})[-/](\d{1,2})\b"
    )

    for chunk in eligible_chunks:
        lines = chunk.text.splitlines()
        for idx, line in enumerate(lines):
            clean_l = line.strip()
            if not clean_l:
                continue

            # 1. Match explicit requirement codes (e.g., R1, R2, R3, R4, R5, R8)
            found_codes = re.findall(
                r"\b(R[1-9]\d?|REQ-[0-9]+)\b\s*[:\-–]?\s*([^,\n;\.]+)", clean_l, re.IGNORECASE
            )
            for code, desc in found_codes:
                rid = code.upper()
                if rid not in seen_req_ids:
                    seen_req_ids.add(rid)
                    # Check for explicit deadline date
                    m_date = date_pattern.search(clean_l) or date_pattern.search(chunk.text)
                    parsed_d = None
                    if m_date:
                        try:
                            if m_date.group(1):
                                d, m, y = int(m_date.group(1)), int(m_date.group(2)), int(m_date.group(3))
                                if y < 100:
                                    y += 2000
                                parsed_d = date(y, m, d)
                            elif m_date.group(4):
                                y, m, d = int(m_date.group(4)), int(m_date.group(5)), int(m_date.group(6))
                                parsed_d = date(y, m, d)
                        except Exception:
                            parsed_d = None

                    words = [w.lower() for w in re.findall(r"\w+", desc) if len(w) > 2][:4]
                    extracted.append(
                        RequirementItem(
                            req_id=rid,
                            title=desc.strip(),
                            keywords=words,
                            official_deadline=parsed_d,
                            mandatory_flag="tùy chọn" not in desc.lower() and "optional" not in desc.lower(),
                            source_ref=f"{chunk.doc_name}#p{chunk.page_number}_L{chunk.start_line + idx}",
                        )
                    )

            # 2. Match numbered deliverables (e.g. 01 Engineering Report, 02 Source Repository)
            deliv_items = re.findall(
                r"\b(0[1-9])\s+([A-Za-z0-9À-ỹ\s]{4,35})(?:\([^\)]+\)|[,;\.]|$)", clean_l
            )
            for d_num, d_title in deliv_items:
                rid = f"DELIV-{d_num}"
                if rid not in seen_req_ids:
                    seen_req_ids.add(rid)
                    words = [w.lower() for w in re.findall(r"\w+", d_title) if len(w) > 2][:4]
                    extracted.append(
                        RequirementItem(
                            req_id=rid,
                            title=d_title.strip(),
                            keywords=words,
                            official_deadline=None,
                            mandatory_flag=True,
                            source_ref=f"{chunk.doc_name}#p{chunk.page_number}_L{chunk.start_line + idx}",
                        )
                    )

    if not extracted:
        return get_default_requirements()

    return extracted


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

    def extract_requirements(
        self, doc_ids: Optional[List[str]] = None
    ) -> List[RequirementItem]:
        """Convenience instance method for extracting requirements from workspace."""
        return extract_requirements_from_workspace(doc_ids=doc_ids)


# Singleton instance
reconciliation_service = ReconciliationService()


def handle_reconciliation_request(reference_date: date) -> Dict[str, Any]:
    return reconciliation_service.reconcile(reference_date=reference_date)
