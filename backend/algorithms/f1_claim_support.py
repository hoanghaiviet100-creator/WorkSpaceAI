"""Bounded support contracts/proofs. Stdlib only; no I/O or model calls.

Numerical proofs require exact controlled declarations in BOTH source and claim.
Natural-language acceptance is constrained by the service's separate support gate.
"""
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from fractions import Fraction
import hashlib
import re
from types import MappingProxyType
from typing import Optional, Tuple


class SupportStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ERROR = "ERROR"


def fingerprint(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _strings(obj, names):
    if any(not isinstance(getattr(obj, name), str) for name in names):
        raise TypeError("Contract string fields must be immutable strings")


@dataclass(frozen=True)
class Evidence:
    context_id: str
    evidence_id: str
    doc_id: str
    doc_version: str
    doc_hash: str
    page: int
    line_start: int
    line_end: int
    text: str
    content_fingerprint: str

    def __post_init__(self):
        _strings(self, ("context_id", "evidence_id", "doc_id", "doc_version", "doc_hash", "text", "content_fingerprint"))
        if any(type(n) is not int for n in (self.page, self.line_start, self.line_end)):
            raise TypeError("Physical coordinates must be integers")


@dataclass(frozen=True)
class DocumentIdentity:
    """Trusted fixture manifest entry, separate from per-record assertions."""
    doc_id: str
    doc_version: str
    doc_hash: str

    def __post_init__(self):
        _strings(self, ("doc_id", "doc_version", "doc_hash"))


@dataclass(frozen=True)
class Quantity:
    entity: str
    scope: str
    attribute: str
    value: str
    unit: str
    relation: str = "="

    def __post_init__(self):
        _strings(self, ("entity", "scope", "attribute", "value", "unit", "relation"))

    def declaration(self) -> str:
        return f"{self.entity} [{self.scope}]: {self.attribute} {self.relation} {self.value} {self.unit}."


@dataclass(frozen=True)
class SourceFact:
    fact_id: str
    evidence_id: str
    line: int
    quantity: Quantity

    def __post_init__(self):
        _strings(self, ("fact_id", "evidence_id"))
        if not isinstance(self.quantity, Quantity) or type(self.line) is not int:
            raise TypeError("Source facts require an immutable quantity and integer line")


@dataclass(frozen=True)
class CompositionCondition:
    condition_id: str
    evidence_id: str
    line: int
    left_entity: str
    right_entity: str
    combined_entity: str
    scope: str
    attribute: str = "completed"
    unit: str = "task"
    kind: str = "disjoint"

    def __post_init__(self):
        _strings(self, ("condition_id", "evidence_id", "left_entity", "right_entity", "combined_entity", "scope", "attribute", "unit", "kind"))
        if type(self.line) is not int:
            raise TypeError("Condition line must be an integer")

    def declaration(self) -> str:
        return (f"{self.combined_entity} [{self.scope}]: {self.kind}({self.left_entity}, {self.right_entity}); "
                f"attribute={self.attribute}; unit={self.unit}.")


@dataclass(frozen=True)
class EvidenceLedger:
    context_id: str
    selected_doc_ids: Tuple[str, ...]
    evidence: Tuple[Evidence, ...]
    facts: Tuple[SourceFact, ...] = ()
    conditions: Tuple[CompositionCondition, ...] = ()
    context_complete: bool = True
    # Explicit trusted fixture annotations, not workspace contradiction discovery.
    conflict_groups: Tuple[Tuple[str, ...], ...] = ()
    documents: Tuple[DocumentIdentity, ...] = ()

    def __post_init__(self):
        for name in ("selected_doc_ids", "evidence", "facts", "conditions", "documents"):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        object.__setattr__(self, "conflict_groups", tuple(tuple(g) for g in self.conflict_groups))
        _strings(self, ("context_id",))
        for values, kind in ((self.selected_doc_ids, str), (self.evidence, Evidence),
                             (self.facts, SourceFact), (self.conditions, CompositionCondition),
                             (self.documents, DocumentIdentity)):
            if any(not isinstance(v, kind) for v in values):
                raise TypeError("Ledger members must be immutable contract records")
        if any(not isinstance(v, str) for g in self.conflict_groups for v in g):
            raise TypeError("Conflict references must be strings")


@dataclass(frozen=True)
class Proof:
    operation: str
    fact_ids: Tuple[str, ...]
    goal: Quantity
    condition_id: Optional[str] = None

    def __post_init__(self):
        object.__setattr__(self, "fact_ids", tuple(self.fact_ids))
        _strings(self, ("operation",))
        if any(not isinstance(v, str) for v in self.fact_ids) or not isinstance(self.goal, Quantity):
            raise TypeError("Proof requires immutable fact references and a quantity")


@dataclass(frozen=True)
class Atom:
    claim_id: str
    text: str
    start: int
    end: int
    evidence_ids: Tuple[str, ...]
    proof: Optional[Proof] = None

    def __post_init__(self):
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        _strings(self, ("claim_id", "text"))
        if any(not isinstance(v, str) for v in self.evidence_ids) or (self.proof is not None and not isinstance(self.proof, Proof)):
            raise TypeError("Atom references/proof must be immutable contract values")


@dataclass(frozen=True)
class ParentClaim:
    claim_id: str
    context_id: str
    text: str
    atoms: Tuple[Atom, ...]
    explanation: Optional[Atom] = None

    def __post_init__(self):
        object.__setattr__(self, "atoms", tuple(self.atoms))
        _strings(self, ("claim_id", "context_id", "text"))
        if any(not isinstance(a, Atom) for a in self.atoms) or (self.explanation is not None and not isinstance(self.explanation, Atom)):
            raise TypeError("Parent components must be immutable atoms")


@dataclass(frozen=True)
class CheckedProof:
    operation: str
    fact_ids: Tuple[str, ...]
    evidence_ids: Tuple[str, ...]
    actual_value: str
    target_value: str
    unit: str
    condition_id: Optional[str] = None


@dataclass(frozen=True)
class AtomDecision:
    claim_id: str
    context_id: str
    status: SupportStatus
    evidence_ids: Tuple[str, ...]
    method: str
    reason_code: str
    checked_proof: Optional[CheckedProof] = None
    simulated: bool = False


@dataclass(frozen=True)
class SupportDecision:
    claim_id: str
    context_id: str
    original_text: str
    status: SupportStatus
    evidence_ids: Tuple[str, ...]
    method: str
    reason_code: str
    atom_decisions: Tuple[AtomDecision, ...] = ()
    supported_text: Optional[str] = None
    supported_explanation: Optional[str] = None
    explanation_status: Optional[SupportStatus] = None
    checked_proof: Optional[CheckedProof] = None
    simulated: bool = False
    # No semantic backend qualification/production authorization exists in this prototype.
    production_semantic_authorized: bool = field(default=False, init=False)


_UNITS = MappingProxyType({
    "g": ("mass", Fraction(1)), "mg": ("mass", Fraction(1, 1000)),
    "kg": ("mass", Fraction(1000)), "page": ("page", Fraction(1)),
    "tablet": ("tablet", Fraction(1)), "USD": ("USD", Fraction(1)),
    "task": ("task", Fraction(1)),
})
_ATTRIBUTES = MappingProxyType({"mass": "mass", "pages": "page", "dose": "tablet",
                                "balance": "USD", "completed": "task"})


def _identifier(value) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip() and "\n" not in value and "\r" not in value


def _number(value: str) -> Fraction:
    if not isinstance(value, str) or not re.fullmatch(r"[+−-]?(?:[0-9]+/[0-9]+|[0-9]+(?:\.[0-9]+)?)", value):
        raise ValueError("UNRECOGNIZED_NUMBER")
    try:
        return Fraction(value.replace("−", "-"))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError("UNRECOGNIZED_NUMBER") from exc


def _normalized(q: Quantity):
    if not all(_identifier(v) for v in (q.entity, q.scope, q.attribute, q.value, q.unit)):
        raise ValueError("INVALID_QUANTITY_BINDING")
    if q.unit not in _UNITS or q.attribute not in _ATTRIBUTES:
        raise ValueError("UNRECOGNIZED_UNIT_OR_ATTRIBUTE")
    dimension, factor = _UNITS[q.unit]
    if dimension != _ATTRIBUTES[q.attribute]:
        raise ValueError("UNIT_ATTRIBUTE_MISMATCH")
    return dimension, _number(q.value) * factor


def _bound_line(ledger: EvidenceLedger, evidence_id: str, line: int, text: str) -> bool:
    e = next((e for e in ledger.evidence if e.evidence_id == evidence_id), None)
    return bool(e and type(line) is int and e.line_start <= line <= e.line_end
                and e.text.splitlines()[line - e.line_start] == text)


def audit_ledger(ledger: EvidenceLedger):
    """Return (failure status, reason), or None. Scope is only supplied selected evidence."""
    if not isinstance(ledger, EvidenceLedger) or not _identifier(ledger.context_id):
        return SupportStatus.ERROR, "INVALID_CONTEXT_ID"
    ids = ledger.selected_doc_ids
    if any(not _identifier(d) for d in ids) or len(set(ids)) != len(ids):
        return SupportStatus.ERROR, "INVALID_SELECTED_DOCUMENTS"
    documents = {d.doc_id: d for d in ledger.documents}
    if (len(documents) != len(ledger.documents) or set(documents) != set(ids)
            or any(not _identifier(d.doc_version) or not re.fullmatch(r"[0-9a-f]{64}", d.doc_hash)
                   for d in ledger.documents)):
        return SupportStatus.ERROR, "INVALID_DOCUMENT_MANIFEST"
    seen, versions, lines = set(), {}, {}
    for e in ledger.evidence:
        if not isinstance(e, Evidence) or not _identifier(e.evidence_id) or e.evidence_id in seen:
            return SupportStatus.ERROR, "DUPLICATE_OR_INVALID_EVIDENCE_ID"
        seen.add(e.evidence_id)
        if e.context_id != ledger.context_id or e.doc_id not in ids:
            return SupportStatus.ERROR, "UNAUTHORIZED_OR_MISMATCHED_EVIDENCE"
        trusted = documents[e.doc_id]
        if (e.doc_version, e.doc_hash) != (trusted.doc_version, trusted.doc_hash):
            return SupportStatus.ERROR, "DOCUMENT_IDENTITY_MISMATCH"
        if (not _identifier(e.doc_version) or not isinstance(e.doc_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", e.doc_hash)
                or not isinstance(e.text, str) or not e.text or e.content_fingerprint != fingerprint(e.text)):
            return SupportStatus.ERROR, "INVALID_PROVENANCE"
        if (type(e.page) is not int or e.page < 1 or type(e.line_start) is not int or type(e.line_end) is not int
                or e.line_start < 1 or e.line_end - e.line_start + 1 != len(e.text.splitlines())):
            return SupportStatus.ERROR, "INVALID_PHYSICAL_SPAN"
        version = (e.doc_version, e.doc_hash)
        if e.doc_id in versions and versions[e.doc_id] != version:
            return SupportStatus.ERROR, "CONFLICTING_PROVENANCE"
        versions[e.doc_id] = version
        for offset, line in enumerate(e.text.splitlines()):
            key = e.doc_id, e.page, e.line_start + offset
            if key in lines and lines[key] != line:
                return SupportStatus.ERROR, "CONFLICTING_OVERLAP"
            lines[key] = line
    for f in ledger.facts:
        if (not isinstance(f, SourceFact) or not _identifier(f.fact_id) or f.fact_id in seen
                or not isinstance(f.quantity, Quantity) or f.quantity.relation != "="
                or not _bound_line(ledger, f.evidence_id, f.line, f.quantity.declaration())):
            return SupportStatus.ERROR, "UNBOUND_OR_DUPLICATE_SOURCE_FACT"
        seen.add(f.fact_id)
    for c in ledger.conditions:
        if (not isinstance(c, CompositionCondition) or not _identifier(c.condition_id) or c.condition_id in seen
                or not _bound_line(ledger, c.evidence_id, c.line, c.declaration())):
            return SupportStatus.ERROR, "UNBOUND_OR_DUPLICATE_CONDITION"
        seen.add(c.condition_id)
    evidence_ids = {e.evidence_id for e in ledger.evidence}
    for group in ledger.conflict_groups:
        if len(group) < 2 or len(set(group)) != len(group) or not set(group) <= evidence_ids:
            return SupportStatus.ERROR, "INVALID_CONFLICT_REFERENCES"
    if type(ledger.context_complete) is not bool:
        return SupportStatus.ERROR, "INVALID_COMPLETENESS_FLAG"
    if not ledger.context_complete:
        return SupportStatus.INSUFFICIENT_EVIDENCE, "INCOMPLETE_CONTEXT"
    if ledger.conflict_groups:
        return SupportStatus.INSUFFICIENT_EVIDENCE, "SOURCE_CONFLICT"
    quantities = {}
    for fact in ledger.facts:
        try:
            dimension, value = _normalized(fact.quantity)
        except ValueError:
            continue  # Unrecognized facts cannot authorize a numerical proof.
        q = fact.quantity
        key = q.entity, q.scope, q.attribute, dimension
        if key in quantities and quantities[key] != value:
            return SupportStatus.INSUFFICIENT_EVIDENCE, "SOURCE_CONFLICT"
        quantities[key] = value
    # Reconcile the existing one-step disjoint addition with direct totals before
    # choosing a proof. Use only normalized direct facts; never chain derivations.
    for c in ledger.conditions:
        if (c.kind != "disjoint" or c.attribute != "completed" or c.unit != "task"
                or c.left_entity == c.right_entity):
            continue
        keys = tuple((entity, c.scope, c.attribute, "task")
                     for entity in (c.left_entity, c.right_entity, c.combined_entity))
        if all(key in quantities for key in keys):
            left, right, direct = (quantities[key] for key in keys)
            if left + right != direct:
                return SupportStatus.INSUFFICIENT_EVIDENCE, "SOURCE_CONFLICT"
    return None


def audit_parent(parent: ParentClaim, ledger: EvidenceLedger):
    if not _identifier(parent.claim_id) or not isinstance(parent.text, str) or not parent.text.strip():
        return SupportStatus.ERROR, "INVALID_PARENT_CLAIM"
    if parent.context_id != ledger.context_id:
        return SupportStatus.ERROR, "CONTEXT_MISMATCH"
    evidence_ids, claim_ids = {e.evidence_id for e in ledger.evidence}, {parent.claim_id}
    all_atoms = parent.atoms + ((parent.explanation,) if parent.explanation else ())
    for atom in all_atoms:
        if not isinstance(atom, Atom) or not _identifier(atom.claim_id) or atom.claim_id in claim_ids:
            return SupportStatus.ERROR, "DUPLICATE_OR_INVALID_CLAIM_ID"
        claim_ids.add(atom.claim_id)
        if (not isinstance(atom.text, str) or not atom.text.strip()
                or not atom.evidence_ids or any(not _identifier(i) for i in atom.evidence_ids)
                or len(set(atom.evidence_ids)) != len(atom.evidence_ids) or not set(atom.evidence_ids) <= evidence_ids):
            return SupportStatus.ERROR, "INVALID_EVIDENCE_REFERENCES"
    if parent.explanation and (parent.explanation.start != 0 or parent.explanation.end != len(parent.explanation.text)):
        return SupportStatus.ERROR, "INVALID_EXPLANATION_COVERAGE"
    if not parent.atoms:
        return SupportStatus.INSUFFICIENT_EVIDENCE, "DECOMPOSITION_INCOMPLETE"
    cursor = 0
    for atom in parent.atoms:
        if (type(atom.start) is not int or type(atom.end) is not int or not atom.text
                or atom.start < cursor or atom.end > len(parent.text) or atom.end <= atom.start
                or parent.text[atom.start:atom.end] != atom.text):
            return SupportStatus.INSUFFICIENT_EVIDENCE, "DECOMPOSITION_INCOMPLETE"
        gap = parent.text[cursor:atom.start]
        if (cursor == 0 and gap.strip()) or (cursor != 0 and gap not in (" and ", " và ")):
            return SupportStatus.INSUFFICIENT_EVIDENCE, "UNVERIFIED_RELATIONSHIP_OR_COVERAGE"
        cursor = atom.end
    if parent.text[cursor:].strip():
        return SupportStatus.INSUFFICIENT_EVIDENCE, "DECOMPOSITION_INCOMPLETE"
    return None


def check_proof(atom: Atom, ledger: EvidenceLedger) -> AtomDecision:
    def result(status, reason, checked=None):
        return AtomDecision(atom.claim_id, ledger.context_id, status, atom.evidence_ids,
                            "deterministic_proof", reason, checked)
    failure = audit_ledger(ledger)
    if failure:
        return result(*failure)
    p = atom.proof
    if not isinstance(p, Proof) or p.operation not in ("compare", "add"):
        return result(SupportStatus.INSUFFICIENT_EVIDENCE, "UNSUPPORTED_OPERATION")
    if not isinstance(p.goal, Quantity) or atom.text != p.goal.declaration():
        return result(SupportStatus.INSUFFICIENT_EVIDENCE, "CLAIM_PROPOSITION_NOT_BOUND")
    if p.goal.relation not in ("=", "!=", "<", "<=", ">", ">="):
        return result(SupportStatus.INSUFFICIENT_EVIDENCE, "UNSUPPORTED_RELATION")
    facts = {f.fact_id: f for f in ledger.facts}
    if len(set(p.fact_ids)) != len(p.fact_ids) or any(f not in facts for f in p.fact_ids):
        return result(SupportStatus.INSUFFICIENT_EVIDENCE, "UNBOUND_OR_DUPLICATE_OPERAND")
    operands = tuple(facts[f] for f in p.fact_ids)
    if any(f.evidence_id not in atom.evidence_ids for f in operands):
        return result(SupportStatus.ERROR, "OPERAND_EVIDENCE_NOT_AUTHORIZED")
    try:
        dimension, target = _normalized(p.goal)
        values = [_normalized(f.quantity) for f in operands]
    except ValueError as exc:
        return result(SupportStatus.INSUFFICIENT_EVIDENCE, str(exc))
    if any(d != dimension for d, _ in values):
        return result(SupportStatus.INSUFFICIENT_EVIDENCE, "MISMATCHED_UNITS")
    if p.operation == "compare":
        if len(operands) != 1 or p.condition_id is not None:
            return result(SupportStatus.INSUFFICIENT_EVIDENCE, "INVALID_COMPARE_PROOF")
        q = operands[0].quantity
        if (q.entity, q.scope, q.attribute) != (p.goal.entity, p.goal.scope, p.goal.attribute):
            return result(SupportStatus.INSUFFICIENT_EVIDENCE, "OPERAND_SCOPE_MISMATCH")
        actual = values[0][1]
    else:
        c = next((c for c in ledger.conditions if c.condition_id == p.condition_id), None)
        if len(operands) != 2 or c is None or c.kind != "disjoint":
            return result(SupportStatus.INSUFFICIENT_EVIDENCE, "MISSING_COMPOSITION_CONDITION")
        q1, q2 = (f.quantity for f in operands)
        if (q1.entity == q2.entity or {q1.entity, q2.entity} != {c.left_entity, c.right_entity}
                or c.combined_entity != p.goal.entity or c.scope != p.goal.scope
                or any(q.scope != c.scope or q.attribute != c.attribute or q.unit != c.unit for q in (q1, q2))
                or c.attribute != "completed" or c.unit != "task" or p.goal.attribute != c.attribute
                or p.goal.unit != c.unit or c.evidence_id not in atom.evidence_ids):
            return result(SupportStatus.INSUFFICIENT_EVIDENCE, "INVALID_COMPOSITION_BINDING")
        actual = sum((v for _, v in values), Fraction(0))
    relation = p.goal.relation
    supported = {"=": actual == target, "!=": actual != target, "<": actual < target,
                 "<=": actual <= target, ">": actual > target, ">=": actual >= target}[relation]
    factor = _UNITS[p.goal.unit][1]
    checked = CheckedProof(p.operation, p.fact_ids, atom.evidence_ids, str(actual / factor),
                           str(_number(p.goal.value)), p.goal.unit, p.condition_id)
    return result(SupportStatus.SUPPORTED if supported else SupportStatus.CONTRADICTED,
                  "CHECKED_PROOF" if supported else "CHECKED_CONTRADICTION", checked)


# M2: deliberately bounded source parsing. Every regex consumes a whole physical
# assertion; unknown qualifications/conditions are never stripped to obtain a fact.
_NUM = r"(?:[+−-]?(?:\d+/\d+|\d+(?:[.,]\d+)?)|(?:negative |âm )?[\w]+(?: [\w]+)?)"
_ENTITY = r"[\w-]+"
_WORDS = dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split(), range(21)))
_VI_DIGITS = dict(zip('không một hai ba bốn năm sáu bảy tám chín'.split(), range(10)))


def ambiguous_number_format(text):
    """Reject grouping-shaped literals without guessing a numeric locale.

    Keep the existing simple decimal grammar, including 0.017/0,017. A
    nonzero (or padded) integer followed by three digits could be grouping;
    multiple separators are outside this bounded grammar altogether.
    """
    for literal in re.findall(r'(?<![\w.,/])[+−-]?[0-9]+(?:[.,][0-9]+)+(?![\w/])', text):
        parts = re.split(r'[.,]', literal.lstrip('+−-'))
        if len(parts) > 2 or (len(parts[1]) == 3 and parts[0] != '0'):
            return True
    return False


def bounded_number(text):
    value = text.lower().strip()
    sign = -1 if value.startswith(('negative ', 'âm ')) else 1
    value = re.sub(r'^(?:negative |âm )', '', value)
    if value in _WORDS:
        return Fraction(sign * _WORDS[value])
    if value in _VI_DIGITS:
        return Fraction(sign * _VI_DIGITS[value])
    if value == 'mười':
        return Fraction(sign * 10)
    if value.startswith('mười ') and value[5:] in _VI_DIGITS:
        return Fraction(sign * (10 + _VI_DIGITS[value[5:]]))
    if ambiguous_number_format(value):
        raise ValueError('AMBIGUOUS_NUMBER_FORMAT')
    return sign * _number(value.replace(',', '.'))


@dataclass(frozen=True)
class BoundProposition:
    kind: str
    entity: str
    scope: str
    attribute: str
    value: str
    unit: str
    relation: str = '='


def parse_bound_proposition(text):
    """Closed grammar for existing quantity/date and approval/payment examples.

    The grammar is language-wide and parameterized, never keyed by fixture IDs.
    Semantic approval/payment signatures are constraints, not a support verdict.
    """
    s = text.strip().rstrip('.').strip()
    controlled = re.fullmatch(r'(.+?) \[([^\[\]]+)\]: (\w+) (!=|<=|>=|=|<|>) (\S+) (\w+)', s)
    if controlled:
        entity, scope, attribute, relation, value, unit = controlled.groups()
        try:
            dimension, normalized = _normalized(Quantity(entity, scope, attribute, value, unit, relation))
            return BoundProposition('quantity', entity, scope, attribute, str(normalized), dimension, relation)
        except ValueError:
            return None
    patterns = (
        (rf'(?:Report )?({_ENTITY}|The report) (?:requires|must contain) (?:exactly )?({_NUM}) pages?', 'pages', 'page'),
        (rf'(?:Báo cáo )?({_ENTITY}) (?:bắt buộc có|phải có) (?:đúng )?({_NUM}) trang', 'pages', 'page'),
        (rf"(?:Account )?({_ENTITY})(?:'s balance is| has (?:a recorded balance of|a negative balance of)) ({_NUM}) USD", 'balance', 'USD'),
        (rf'(?:Tài khoản )?({_ENTITY}) có số dư (?:ghi nhận là )?({_NUM}) USD', 'balance', 'USD'),
        (rf'Số dư của ({_ENTITY}) là ({_NUM}) USD', 'balance', 'USD'),
        (rf"(?:Patient )?({_ENTITY})'s (?:prescribed )?dose is ({_NUM}) tablets?", 'dose', 'tablet'),
        (rf'Liều (?:được kê cho bệnh nhân|của) ({_ENTITY}) (?:là )?({_NUM}) viên', 'dose', 'tablet'),
        (rf'(?:Sample )?({_ENTITY}) has a mass of ({_NUM}) (mg|g|kg)', 'mass', None),
        (rf'(?:Mẫu )?({_ENTITY}) có khối lượng ({_NUM}) (mg|g|kg)', 'mass', None),
        (rf'Khối lượng ({_ENTITY}) là ({_NUM}) (mg|g|kg)', 'mass', None),
    )
    for pattern, attribute, fixed_unit in patterns:
        m = re.fullmatch(pattern, s, re.IGNORECASE)
        if not m:
            continue
        entity, number = m.group(1, 2)
        unit = fixed_unit or m.group(3).lower()
        try:
            value = bounded_number(number)
            # Negative balance wording carries the sign even without a symbol.
            if 'negative balance' in s.lower():
                if value < 0:
                    return None
                value = -value
            dimension, scale = _UNITS[unit]
            return BoundProposition('quantity', entity.casefold(), '', attribute, str(value * scale), dimension)
        except (ValueError, KeyError):
            return None
    date_patterns = (
        rf"(?:Report )?({_ENTITY})'s deadline is (.+)",
        rf'({_ENTITY}) is due on (.+)',
        rf'Hạn nộp (?:báo cáo )?({_ENTITY}) là (.+)',
        rf'({_ENTITY}) đến hạn (?:vào ngày |ngày )?(.+)',
    )
    for pattern in date_patterns:
        m = re.fullmatch(pattern, s, re.IGNORECASE)
        if m:
            entity, value = m.groups()
            months = {name: i + 1 for i, name in enumerate('January February March April May June July August September October November December'.lower().split())}
            try:
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                    normalized = date.fromisoformat(value)
                elif (dm := re.fullmatch(r'(\d{1,2}) ([A-Za-z]+) (\d{4})', value)):
                    day, month, year = dm.groups()
                    normalized = date(int(year), months[month.lower()], int(day))
                elif (dm := re.fullmatch(r'(\d{1,2}) tháng (\d{1,2}) năm (\d{4})', value)):
                    day, month, year = dm.groups()
                    normalized = date(int(year), int(month), int(day))
                else:
                    return None
                return BoundProposition('date', entity.casefold(), '', 'deadline', normalized.isoformat(), 'date')
            except (KeyError, ValueError):
                return None
    approval = (
        (rf'(?:Permit )?({_ENTITY}) (?:has not been approved|has not received approval)', 'negative'),
        (rf'(?:Permit )?({_ENTITY}) (?:is approved|has been approved)', 'positive'),
        (rf'(?:Giấy phép )?({_ENTITY}) (?:chưa được phê duyệt|chưa nhận được phê duyệt)', 'negative'),
        (rf'(?:Giấy phép )?({_ENTITY}) đã được phê duyệt', 'positive'),
    )
    for pattern, polarity in approval:
        if (m := re.fullmatch(pattern, s, re.IGNORECASE)):
            return BoundProposition('semantic', m[1].casefold(), '', 'approval', polarity, '')
    payment = (
        (rf'({_ENTITY}) (paid|did not pay) ({_ENTITY})', False),
        (rf'({_ENTITY}) (was paid by) ({_ENTITY})', True),
        (rf'({_ENTITY}) (trả tiền cho|không trả tiền cho) ({_ENTITY})', False),
        (rf'({_ENTITY}) (được) ({_ENTITY}) trả tiền', True),
    )
    for pattern, passive in payment:
        if (m := re.fullmatch(pattern, s, re.IGNORECASE)):
            left, verb, right = m.groups()
            if passive:
                left, right = right, left
            polarity = 'negative' if verb.lower() in ('did not pay', 'không trả tiền cho') else 'positive'
            return BoundProposition('semantic', left.casefold(), right.casefold(), 'payment', polarity, '')
    return None


def instruction_data(text):
    return bool(re.search(r'ignore .*?(?:rules|instructions)|output SUPPORTED|bỏ qua .*?quy tắc|xuất SUPPORTED|__import__|<\/?(?:think|system)', text, re.IGNORECASE))


def source_assertions(text):
    """Keep qualifications intact; split only physical lines/sentence boundaries."""
    return tuple(s.strip() for s in re.split(r'\n+|(?<=[.!?])\s+(?=[A-ZÀ-ỸĐ])', text) if s.strip())


def source_propositions(text):
    return tuple(p for s in source_assertions(text) if (p := parse_bound_proposition(s)) is not None)


def _conflict_assertion(statement):
    """Canonicalize explicit presentation locators for conflict comparison only.

    Keep the entire prefix, including factual numbers, scopes, negation and
    qualifications. Source text, citations and support premises stay intact.
    Bare numbers and prose references to pages are not presentation locators.
    """
    locator = r'(?:page|trang)\s+[0-9]+(?:\s*(?:/|of|trên)\s*[0-9]+)?'
    if re.fullmatch(locator, statement, re.IGNORECASE):
        return ''
    return re.sub(r'\|\s*' + locator + r'\s*$', '| PAGE_LOCATOR', statement, flags=re.IGNORECASE)


def bounded_conflict(texts):
    values = {}
    literal_values = {}
    for text in texts:
        # Temporal adverbs never resolve disagreements. Removal is used ONLY to
        # discover conflict, never to authorize a proof from a qualified source.
        conflict_text = re.sub(r'\bcurrently\s+|\bhiện\s+', '', text, flags=re.IGNORECASE)
        for statement in source_assertions(conflict_text):
            statement = _conflict_assertion(statement)
            if not statement:
                continue
            # Additional narrow lexical contradictions (no synonym inference).
            normalized = ' '.join(statement.casefold().rstrip('.').split())
            negative = bool(re.search(r'\b(?:not|never|không|chưa)\b', normalized))
            skeleton = re.sub(r'\b(?:not|never|không|chưa)\s+', '', normalized)
            numbers = tuple(re.findall(r'[+−-]?\d+(?:[.,/]\d+)*', skeleton))
            skeleton = re.sub(r'[+−-]?\d+(?:[.,/]\d+)*', '#', skeleton)
            literal = negative, numbers
            if skeleton in literal_values and literal_values[skeleton] != literal:
                return True
            literal_values[skeleton] = literal
        for p in source_propositions(conflict_text):
            if p.relation != '=':
                continue
            key = p.kind, p.entity, p.scope, p.attribute, p.unit
            if key in values and values[key] != p.value:
                return True
            values[key] = p.value
    return False


def declared_facts(evidence):
    """Bind only literal controlled declarations; caller supplies trusted evidence."""
    facts, conditions = [], []
    for e in evidence:
        for offset, line in enumerate(e.text.splitlines()):
            m = re.fullmatch(r'(.+?) \[([^\[\]]+)\]: (\w+) = (\S+) (\w+)\.', line)
            if m:
                entity, scope, attribute, value, unit = m.groups()
                facts.append(SourceFact(f'fact:{e.evidence_id}:{offset}', e.evidence_id, e.line_start + offset,
                                        Quantity(entity, scope, attribute, value, unit)))
            m = re.fullmatch(r'(.+?) \[([^\[\]]+)\]: disjoint\((.+?), (.+?)\); attribute=(\w+); unit=(\w+)\.', line)
            if m:
                combined, scope, left, right, attribute, unit = m.groups()
                conditions.append(CompositionCondition(f'condition:{e.evidence_id}:{offset}', e.evidence_id,
                    e.line_start + offset, left, right, combined, scope, attribute, unit))
    return tuple(facts), tuple(conditions)


def bind_declared_proof(text, refs, ledger):
    m = re.fullmatch(r'(.+?) \[([^\[\]]+)\]: (\w+) (!=|<=|>=|=|<|>) (\S+) (\w+)\.', text)
    if not m:
        return None
    entity, scope, attribute, relation, value, unit = m.groups()
    goal = Quantity(entity, scope, attribute, value, unit, relation)
    candidates = [f for f in ledger.facts if f.evidence_id in refs and
                  (f.quantity.entity, f.quantity.scope, f.quantity.attribute) == (entity, scope, attribute)]
    if len(candidates) == 1:
        return Proof('compare', (candidates[0].fact_id,), goal)
    for c in ledger.conditions:
        if c.evidence_id not in refs or (c.combined_entity, c.scope, c.attribute, c.unit) != (entity, scope, attribute, unit):
            continue
        operands = [f for f in ledger.facts if f.evidence_id in refs and f.quantity.entity in (c.left_entity, c.right_entity)
                    and (f.quantity.scope, f.quantity.attribute, f.quantity.unit) == (scope, attribute, unit)]
        if len(operands) == 2:
            return Proof('add', tuple(f.fact_id for f in operands), goal, c.condition_id)
    return None


def prose_statements(text):
    """Physical/sentence boundaries only; no proposition or entity invention."""
    return source_assertions(text)


def _prose_words(text):
    return re.findall(r'[^\W_]+(?:[-\u2010-\u2014][^\W_]+)*', text, re.UNICODE)


# Linguistic operators, not domain vocabulary or answer templates. These are
# rejection constraints; none can authorize entailment or resolve a reference.
_PROSE_OPERATORS = (
    r'\b(?:not|never|no|without|không|chưa|chẳng)\b',
    r'\b(?:may|might|could|possibly|có thể|có khả năng)\b',
    r'\b(?:must|required|phải|bắt buộc)\b',
    r'\b(?:only|solely|chỉ|duy nhất)\b',
    r'\b(?:if|unless|provided|when|under|except|nếu|khi|trừ|điều kiện)\b',
    r'\b(?:all|every|always|tất cả|mọi|luôn)\b',
    r'\b(?:some|sometimes|một số|đôi khi)\b',
)
_PROSE_FUNCTION_WORDS = frozenset(('the a an this that these those it they he she in on at for with '
    'during under only if when unless because after before and but of to as is are was were '
    'nếu khi chỉ trong cùng điều kiện sau trước vì do của là và nhưng một các những này đó').split())


def _prose_operators(text):
    return tuple(bool(re.search(pattern, text, re.IGNORECASE)) for pattern in _PROSE_OPERATORS)


def _prose_entities(text):
    """Conservatively retain explicit names/codes and sentence subject anchors.

    This is not a coreference resolver. Unresolved paraphrases abstain instead
    of guessing an entity; ordinary predicate synonyms are left to full NLI.
    """
    entities = set()
    for sentence in prose_statements(text):
        words = _prose_words(sentence)
        substantive = [w for w in words if w.casefold() not in _PROSE_FUNCTION_WORDS]
        if substantive:
            entities.add(substantive[0].casefold())
        entities.update(w.casefold() for w in words if w[:1].isupper()
                        and w.casefold() not in _PROSE_FUNCTION_WORDS)
    return entities


def _prose_numbers_units(text):
    return tuple(sorted(re.findall(r'(?<!\w)[+−-]?[0-9]+(?:[.,:/][0-9]+)*(?!\w)', text))), tuple(sorted(
        (m.group(1), m.group(2).casefold()) for m in re.finditer(
            r'(?<!\w)([+−-]?[0-9]+(?:[.,:/][0-9]+)*)\s+([^\W\d_]+)', text)))


def _prose_clause_count(text):
    return len(prose_statements(text)) + len(re.findall(
        r'\b(?:and|but|that|which|because|và|nhưng|vì|để)\b|;', text, re.IGNORECASE))


def prose_preconditions(claim, premise, authorized_texts):
    """Necessary structural constraints; success here is NEVER a support token.

    The caller must still check complete-claim entailment, reverse coverage and
    semantic conflicts against the entire authorized context with qualified NLI.
    """
    if not claim.strip() or not premise.strip():
        return 'INSUFFICIENT_PROSE_EVIDENCE'
    context = tuple(authorized_texts)
    if instruction_data(claim) or any(instruction_data(t) for t in context):
        return 'INSTRUCTION_DATA'
    if _prose_numbers_units(claim) != _prose_numbers_units(premise):
        return 'PROSE_VALUE_OR_UNIT_MISMATCH'
    if not prose_operator_forms_match(claim, premise):
        return 'PROSE_QUALIFICATION_MISMATCH'
    if _prose_clause_count(claim) > _prose_clause_count(premise):
        return 'PROSE_UNSUPPORTED_TAIL'
    source_entities = _prose_entities(premise)
    claim_words = {w.casefold() for w in _prose_words(claim)}
    if not source_entities or not source_entities <= claim_words:
        return 'PROSE_ENTITY_MISMATCH'
    # Explicit names/codes introduced by the candidate cannot inherit support.
    premise_words = {w.casefold() for w in _prose_words(premise)}
    if not _prose_entities(claim) <= premise_words:
        return 'PROSE_ENTITY_MISMATCH'
    if not _same_prose(claim, premise) and re.search(
            r'\b(?:it|they|he|she|nó|họ|chúng)\b', premise, re.IGNORECASE):
        return 'PROSE_AMBIGUOUS_REFERENCE'
    return None


def _same_prose(left, right):
    return ' '.join(left.split()) == ' '.join(right.split())


def prose_operator_forms_match(claim, premise):
    """Retain modal guards; admit one ambiguous comparative form to full NLI.

    Adding Vietnamese capability wording to an otherwise identical explicit
    comparison can express the same disposition. This is only NLI eligibility;
    deleting that wording from a source, or changing a clear modal, stays denied.
    """
    left, right = _prose_operators(claim), _prose_operators(premise)
    if left == right:
        return True
    stripped, count = re.subn(r'\bcó khả năng\s+', '', claim, count=1, flags=re.IGNORECASE)
    comparative = bool(re.search(r'\bhơn\b', premise, re.IGNORECASE))
    return (count == 1 and comparative and not re.search(r'\bcó khả năng\b', premise, re.IGNORECASE)
            and left[1] and not right[1] and left[:1] + left[2:] == right[:1] + right[2:]
            and tuple(w.casefold() for w in _prose_words(stripped)) == tuple(w.casefold() for w in _prose_words(premise)))


def prose_qualification_candidates(premise, authorized_texts):
    """Bind qualification to its own factual clause, never a shared token alone.

    Clause stripping is rejection-only and never changes a support premise.
    Uncertain semantic relations are assessed by the service's pinned NLI audit;
    all original authorized text also stays in the separate contradiction audit.
    """
    anchors = _prose_entities(premise)
    cited = {' '.join(s.casefold().split()) for s in (premise, *prose_statements(premise))}
    seen = set()
    for text in authorized_texts:
        statements = prose_statements(text)
        units = list(statements)
        for left, right in zip(statements, statements[1:]):
            if re.match(r'^(?:if|when|unless|provided|only|nếu|khi|chỉ)\b', left, re.IGNORECASE) and not re.search(r'[.!?]$', left):
                units.append(left.rstrip(':,') + ', ' + right)
        for statement in units:
            normalized = ' '.join(statement.casefold().split())
            if normalized in cited or normalized in seen or not any(_prose_operators(statement)):
                continue
            seen.add(normalized)
            base = statement.strip()
            leading = re.match(r'^(?:if\b|when\b|unless\b|provided\b|under\b|only\b|nếu\b|khi\b|chỉ\b|trong\b)[^,:\n]*[,:]\s*(.+)$', base, re.IGNORECASE | re.DOTALL)
            if leading:
                base = leading.group(1)
            else:
                suffix = re.search(r'\s+(?:only|unless|if|when|provided|under|except|nếu|khi|trừ|chỉ)\b', base, re.IGNORECASE)
                if suffix:
                    base = base[:suffix.start()]
            base = re.sub(r'\b(?:not|never|may|might|could|possibly|must|required|không|chưa|chẳng|có thể|có khả năng|phải|bắt buộc)\s+', '', base, flags=re.IGNORECASE)
            base_words = {w.casefold() for w in _prose_words(base)}
            if not anchors & base_words:
                # A reference occurring only inside another assertion's condition
                # does not bind that condition to the cited factual proposition.
                continue
            missing = any(a and not b for a,b in zip(_prose_operators(statement), _prose_operators(premise)))
            yield base, statement, missing


class PropositionComparability(str, Enum):
    COMPARABLE = 'COMPARABLE'
    DISTINCT = 'DISTINCT'
    AMBIGUOUS = 'AMBIGUOUS'


@dataclass(frozen=True)
class ComparabilityDecision:
    state: PropositionComparability
    reason: str
    proof: Tuple[str, ...]


@dataclass(frozen=True)
class _ComparabilitySignature:
    grammar: str
    subject: str
    predicate: str
    object_id: str
    event_role: str
    scope: str
    unit_dimension: str
    qualifications: Tuple[bool, ...]
    canonical_subject: bool


_EVENT_ROLE_FORMS = MappingProxyType({
    'starts': 'start', 'begins': 'start', 'opens': 'start',
    'ends': 'end', 'finishes': 'end', 'closes': 'end',
    'arrives': 'arrival', 'departs': 'departure', 'returns': 'return',
    'bắt đầu': 'start', 'mở cửa': 'start', 'kết thúc': 'end', 'đóng cửa': 'end',
    'đến': 'arrival', 'khởi hành': 'departure', 'trở về': 'return', 'trả': 'return',
})
_TEMPORAL_ROLES = frozenset(_EVENT_ROLE_FORMS.values())


def _comparability_signature(statement):
    """Only complete bounded declarations/temporal assertions yield signatures.

    Values and comparison operators are deliberately absent: conflicting values
    of the same property must remain comparable. No entity alias, omitted
    predicate, pronoun or unparsed qualification is inferred.
    """
    normalized = ' '.join(statement.strip().rstrip('.').split())
    if re.search(r'\b(?:it|they|he|she|this|that|nó|họ|chúng)\b', normalized, re.IGNORECASE):
        return None
    p = parse_bound_proposition(normalized)
    if p is not None:
        if p.entity.casefold() in {'the report', 'the sample', 'báo cáo', 'mẫu'}:
            return None
        object_id = p.scope if p.kind == 'semantic' and p.attribute == 'payment' else ''
        scope = '' if object_id else p.scope
        return _ComparabilitySignature('bound', p.entity.casefold(), p.attribute, object_id.casefold(), '',
            scope.casefold(), p.unit, _prose_operators(statement)[1:], True)
    # Temporal assertions form a small language-wide grammar. Role identity is
    # structural (start/end/arrival/departure/return), not a document keyword.
    if any(_prose_operators(statement)):
        return None
    clock = r'([0-9]{1,2}:[0-9]{2})'
    english = r'(.+?) (starts|begins|opens|ends|finishes|closes|arrives|departs|returns) at ' + clock
    vietnamese = r'(.+?) (bắt đầu|mở cửa|kết thúc|đóng cửa|đến|khởi hành|trở về) (?:lúc|vào lúc) ' + clock
    match = re.fullmatch(english, normalized, re.IGNORECASE) or re.fullmatch(vietnamese, normalized, re.IGNORECASE)
    if match:
        subject, role, value = match.groups()
    else:
        match = re.fullmatch(r'Giờ (bắt đầu|kết thúc|trả|khởi hành|đến) (.+?) là ' + clock, normalized, re.IGNORECASE)
        if not match:
            return None
        role, subject, value = match.groups()
    hour, minute = (int(v) for v in value.split(':'))
    if hour > 23 or minute > 59 or re.search(r'[,:;.!?]|\b(?:and|but|và|nhưng)\b', subject, re.IGNORECASE):
        return None
    subject = ' '.join(subject.casefold().split())
    named = bool(re.fullmatch(r'(?:event|sự kiện) [\w-]+', subject))
    return _ComparabilitySignature('temporal', subject, 'event_time', '', _EVENT_ROLE_FORMS[role.casefold()],
        '', 'clock', (), named)


def _compare_atomic_propositions(left, right):
    C = PropositionComparability
    if ' '.join(left.casefold().split()) == ' '.join(right.casefold().split()):
        return ComparabilityDecision(C.COMPARABLE, 'EXACT_ASSERTION_IDENTITY', ('complete assertion identity',))
    if not _conflict_assertion(left) or not _conflict_assertion(right):
        return ComparabilityDecision(C.DISTINCT, 'EXPLICIT_PRESENTATION_LOCATOR', ('accepted presentation-only locator grammar',))
    a, b = _comparability_signature(left), _comparability_signature(right)
    if a is None or b is None:
        return ComparabilityDecision(C.AMBIGUOUS, 'UNPARSED_OR_UNBOUND_PROPOSITION', ('no complete comparable signature; no alias or predicate inference',))
    if a.qualifications != b.qualifications or a.scope != b.scope:
        return ComparabilityDecision(C.AMBIGUOUS, 'UNRESOLVED_SCOPE_OR_QUALIFICATION', ('scope/qualification identity not established',))
    if a.grammar == b.grammar == 'bound':
        if a.subject == b.subject and a.predicate == b.predicate and a.object_id == b.object_id and a.unit_dimension == b.unit_dimension:
            return ComparabilityDecision(C.COMPARABLE, 'BOUND_PROPERTY_IDENTITY', ('canonical subject/property/object/scope/unit; asserted values excluded',))
        if a.predicate == b.predicate and a.unit_dimension == b.unit_dimension and a.subject != b.subject:
            return ComparabilityDecision(C.DISTINCT, 'BOUND_DISTINCT_CANONICAL_ENTITIES', ('complete existing closed-grammar identifiers and same relation roles',))
        if a.subject == b.subject and a.predicate != b.predicate:
            return ComparabilityDecision(C.DISTINCT, 'BOUND_INDEPENDENT_PROPERTIES', ('different explicit property slots in the bounded declaration contract',))
        if a.subject == b.subject and a.predicate == b.predicate == 'payment' and a.object_id != b.object_id:
            return ComparabilityDecision(C.DISTINCT, 'BOUND_DISTINCT_RELATION_OBJECTS', ('same payer; distinct canonical payee identifiers in the closed relation grammar',))
    if a.grammar == b.grammar == 'temporal':
        if a.event_role != b.event_role and a.event_role in _TEMPORAL_ROLES and b.event_role in _TEMPORAL_ROLES:
            return ComparabilityDecision(C.DISTINCT, 'INDEPENDENT_TEMPORAL_EVENT_ROLES', ('complete unqualified clock assertions; different temporal property roles; no value comparison',))
        if a.subject == b.subject and a.event_role == b.event_role and a.canonical_subject and b.canonical_subject:
            return ComparabilityDecision(C.COMPARABLE, 'BOUND_EVENT_ROLE_IDENTITY', ('canonical event identifier and same temporal role; asserted times excluded',))
        if a.subject != b.subject and a.canonical_subject and b.canonical_subject and a.event_role == b.event_role:
            return ComparabilityDecision(C.DISTINCT, 'BOUND_DISTINCT_EVENT_IDENTIFIERS', ('same event role; different explicit event identifiers',))
    return ComparabilityDecision(C.AMBIGUOUS, 'NO_DISTINCTNESS_PROOF', ('different surface text or favorable NLI labels cannot prove independence',))


def proposition_comparability(left, right):
    """Three-way bounded decision; only a proved DISTINCT may discount conflict.

    All physical/sentence assertions participate. Unknown fragments and mixed
    prose do not become presentation metadata. A relevant comparable assertion
    keeps a mixed block comparable; unresolved remaining blocks fail closed.
    """
    C = PropositionComparability
    if instruction_data(left) or instruction_data(right):
        return ComparabilityDecision(C.AMBIGUOUS, 'INSTRUCTION_OR_UNTRUSTED_OPERATOR', ('instruction text cannot establish distinctness',))
    aa, bb = prose_statements(left), prose_statements(right)
    if not aa or not bb:
        return ComparabilityDecision(C.AMBIGUOUS, 'EMPTY_PROPOSITION', ('missing complete assertion',))
    decisions = tuple(_compare_atomic_propositions(a, b) for a in aa for b in bb)
    if any(d.state == C.COMPARABLE for d in decisions):
        return ComparabilityDecision(C.COMPARABLE, 'COMPARABLE_ASSERTION_PRESENT', tuple(d.reason for d in decisions))
    if all(d.state == C.DISTINCT for d in decisions):
        return ComparabilityDecision(C.DISTINCT, 'ALL_ASSERTIONS_PROVED_DISTINCT', tuple(d.reason for d in decisions))
    return ComparabilityDecision(C.AMBIGUOUS, 'UNRESOLVED_ASSERTION_PRESENT', tuple(d.reason for d in decisions))
