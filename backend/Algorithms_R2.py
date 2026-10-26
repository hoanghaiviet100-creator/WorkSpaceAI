import hashlib
import re
from datetime import date
from typing import Dict, List, Tuple
from backend.schemas import (
    CitationVerificationResult,
    DateConflict,
    EmailDraftPayload,
    EmailState,
    GeneratedClaim,
    ReconciledItemReport,
    ReconciliationSummary,
    RequirementItem,
    TaskRecord,
)
from backend.Understanding_Guardrails import validate_email_address


# =====================================================================
# ALGORITHM 1: Cross-Document Requirement & Deadline Reconciliation
# =====================================================================
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


# =====================================================================
# ALGORITHM 2: Deterministic Citation & Evidence Span Verifier
# =====================================================================
def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def _token_overlap_ratio(quote: str, source: str) -> float:
    q_tokens = re.findall(r"\w+", quote)
    s_tokens = set(re.findall(r"\w+", source))
    if not q_tokens:
        return 0.0
    matched = sum(1 for tok in q_tokens if tok in s_tokens)
    return matched / len(q_tokens)


def verify_citations(
    claims: List[GeneratedClaim],
    chunk_lookup: Dict[Tuple[str, int], str],
    theta_match: float = 0.75,
) -> CitationVerificationResult:
    """
    R2 Deterministic Capability #2:
    Verifies whether each generated claim's cited (doc_id, page) exists and
    whether the quoted evidence span appears verbatim or above token overlap threshold.
    """
    validated: List[GeneratedClaim] = []
    flagged: List[GeneratedClaim] = []
    verified_count = 0

    for c in claims:
        key = (c.cited_doc_id, c.cited_page)
        if key not in chunk_lookup:
            c.verification_status = "INVALID_SOURCE_PAGE"
            flagged.append(c)
            continue

        norm_source = _normalize_text(chunk_lookup[key])
        norm_quote = _normalize_text(c.evidence_quote)

        if norm_quote and norm_quote in norm_source:
            c.verification_status = "VERIFIED_EXACT"
            verified_count += 1
            validated.append(c)
        else:
            overlap = _token_overlap_ratio(norm_quote, norm_source)
            if overlap >= theta_match:
                c.verification_status = "VERIFIED_FUZZY"
                verified_count += 1
                validated.append(c)
            else:
                c.verification_status = "UNGROUNDED_QUOTE"
                flagged.append(c)

    score = round(verified_count / max(1, len(claims)), 4)
    return CitationVerificationResult(
        validated_claims=validated,
        hallucination_flags=flagged,
        grounding_score=score,
    )


# =====================================================================
# ALGORITHM 3: Deterministic Email Approval FSM & Hash Gate
# =====================================================================
def compute_draft_hash(recipient: str, subject: str, body: str, attachments: List[str]) -> str:
    raw = f"{recipient.strip()}|{subject.strip()}|{body.strip()}|{','.join(sorted(attachments))}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def prepare_draft_for_approval(draft: EmailDraftPayload) -> EmailDraftPayload:
    if not validate_email_address(draft.recipient_email):
        raise ValueError(f"Invalid RFC-5322 recipient email: {draft.recipient_email}")
    draft.state = EmailState.PENDING_APPROVAL
    draft.payload_hash = compute_draft_hash(
        draft.recipient_email, draft.subject, draft.body, draft.attachment_ids
    )
    return draft


def approve_and_verify_email_send(
    stored_draft: EmailDraftPayload,
    approved_recipient: str,
    approved_subject: str,
    approved_body: str,
    approved_attachments: List[str],
    user_confirmed: bool,
) -> EmailDraftPayload:
    """
    R2 Deterministic Capability #3:
    Enforces strict state transition PENDING_APPROVAL -> APPROVED and checks SHA-256 integrity.
    """
    if not user_confirmed:
        raise PermissionError("Email send blocked: explicit human approval flag is False.")
    if stored_draft.state != EmailState.PENDING_APPROVAL:
        raise RuntimeError(f"Invalid FSM transition from state {stored_draft.state} to APPROVED.")
    if not validate_email_address(approved_recipient):
        raise ValueError(f"Invalid recipient email address: {approved_recipient}")

    incoming_hash = compute_draft_hash(
        approved_recipient, approved_subject, approved_body, approved_attachments
    )
    if incoming_hash != stored_draft.payload_hash:
        raise SecurityError("Payload hash mismatch! Draft was modified without re-staging approval.")

    stored_draft.state = EmailState.APPROVED
    return stored_draft


class SecurityError(Exception):
    pass
