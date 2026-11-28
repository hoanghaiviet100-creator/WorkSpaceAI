"""F1 QA/summary support gate plus the retained explicit simulation controller."""
from typing import Optional
from dataclasses import dataclass
import re
import uuid

from backend.algorithms.f1_claim_support import (
    Atom, AtomDecision, EvidenceLedger, ParentClaim, SupportDecision, SupportStatus,
    audit_ledger, audit_parent, check_proof,
    Evidence, DocumentIdentity, fingerprint, declared_facts, bind_declared_proof,
    parse_bound_proposition, source_propositions, source_assertions, bounded_conflict, instruction_data,
    ambiguous_number_format, prose_preconditions, prose_statements, prose_qualification_candidates,
    proposition_comparability, PropositionComparability,
)
from backend.providers.f1_claim_support_provider import (
    SemanticItem, SemanticProtocolError, SemanticRequest, SemanticVerifier, validate_simulated_response,
    QualifiedLocalNLI, get_f1_semantic_verifier, validate_local_response,
)


class ClaimSupportController:
    """Default mode can authorize only bounded deterministic declarations.

    No semantic backend is qualified in this prototype, regardless of any
    self-reported backend attributes. Simulated semantic acceptance requires
    the conspicuous for_simulation factory and stays labelled in every result.
    """
    def __init__(self, adapter: Optional[SemanticVerifier] = None):
        self._adapter = adapter
        self._simulation = False

    @classmethod
    def for_simulation(cls, adapter: SemanticVerifier):
        instance = cls(adapter)
        instance._simulation = True
        return instance

    def _semantic(self, atoms, ledger):
        if not self._simulation or self._adapter is None:
            return tuple(AtomDecision(a.claim_id, ledger.context_id, SupportStatus.INSUFFICIENT_EVIDENCE,
                a.evidence_ids, "authorization", "UNQUALIFIED_BACKEND") for a in atoms)
        request = SemanticRequest(ledger.context_id,
            tuple(SemanticItem(a.claim_id, a.text, a.evidence_ids) for a in atoms), ledger.evidence)
        try:
            response = self._adapter.verify(request)  # One call, no favorable-verdict retries.
            return validate_simulated_response(request, response)
        except TimeoutError:
            reason = "VERIFIER_TIMEOUT"
        except SemanticProtocolError:
            reason = "INVALID_SEMANTIC_PROTOCOL"
        except Exception:
            reason = "VERIFIER_ERROR"
        return tuple(AtomDecision(a.claim_id, ledger.context_id, SupportStatus.ERROR, (),
                                 "simulated_semantic", reason, simulated=True) for a in atoms)

    def verify(self, parent: ParentClaim, ledger: EvidenceLedger) -> SupportDecision:
        def finish(status, reason, decisions=(), explanation=None):
            all_decisions = tuple(decisions) + ((explanation,) if explanation else ())
            simulated = any(d.simulated for d in all_decisions)
            method = ("simulated_semantic" if simulated else
                      "deterministic_proof" if decisions and all(d.method == "deterministic_proof" for d in decisions)
                      else "validation")
            known = {e.evidence_id for e in ledger.evidence}
            refs = tuple(sorted({i for d in all_decisions for i in d.evidence_ids if i in known}))
            return SupportDecision(parent.claim_id, ledger.context_id, parent.text, status, refs, method, reason,
                tuple(decisions), parent.text if status == SupportStatus.SUPPORTED else None,
                parent.explanation.text if explanation and explanation.status == SupportStatus.SUPPORTED else None,
                explanation.status if explanation else None,
                decisions[0].checked_proof if len(decisions) == 1 else None, simulated)

        failure = audit_ledger(ledger) or audit_parent(parent, ledger)
        if failure:
            return finish(*failure)
        checked = {a.claim_id: check_proof(a, ledger) for a in parent.atoms if a.proof is not None}
        deterministic = tuple(checked.values())
        # A positive simulated verdict cannot override a checked contradiction.
        if any(d.status == SupportStatus.CONTRADICTED for d in deterministic):
            return finish(SupportStatus.CONTRADICTED, "CHECKED_CONTRADICTION", deterministic)
        if any(d.status != SupportStatus.SUPPORTED for d in deterministic):
            failed = next(d for d in deterministic if d.status != SupportStatus.SUPPORTED)
            return finish(failed.status, failed.reason_code, deterministic)
        pending = tuple(a for a in parent.atoms if a.proof is None)
        if pending:
            checked.update((d.claim_id, d) for d in self._semantic(pending, ledger))
        decisions = tuple(checked[a.claim_id] for a in parent.atoms)
        if any(d.status == SupportStatus.ERROR for d in decisions):
            return finish(SupportStatus.ERROR, next(d.reason_code for d in decisions if d.status == SupportStatus.ERROR), decisions)
        if any(d.status == SupportStatus.CONTRADICTED for d in decisions):
            return finish(SupportStatus.CONTRADICTED, "PARENT_CONTRADICTED", decisions)
        if any(d.status != SupportStatus.SUPPORTED for d in decisions):
            return finish(SupportStatus.INSUFFICIENT_EVIDENCE, "PARENT_NOT_FULLY_SUPPORTED", decisions)
        explanation = None
        if parent.explanation:
            a = parent.explanation
            explanation = check_proof(a, ledger) if a.proof is not None else self._semantic((a,), ledger)[0]
        return finish(SupportStatus.SUPPORTED, "ALL_PARENT_ASSERTIONS_SUPPORTED", decisions, explanation)


@dataclass(frozen=True)
class OutputSupport:
    status: SupportStatus
    reason: str
    method: str
    simulated: bool = False


def _same_text(left, right):
    return ' '.join(left.split()) == ' '.join(right.split())


class F1SupportGate:
    """Request-scoped support gate for QA and extractive summaries.

    Production can use only the pinned local adapter. Test injection is explicit.
    Citation-bound prose requires structural safety, whole-claim NLI, reverse
    coverage and an audit of every authorized source. No favorable fallback.
    """
    def __init__(self):
        self._adapter = None
        self._simulation = False

    @classmethod
    def for_simulation(cls, adapter):
        instance = cls()
        instance._adapter, instance._simulation = adapter, True
        return instance

    def _nli(self, text, ledger, refs, matching):
        adapter = self._adapter if self._simulation else get_f1_semantic_verifier()
        if not self._simulation and type(adapter) is not QualifiedLocalNLI:
            return OutputSupport(SupportStatus.ERROR, 'UNQUALIFIED_BACKEND', 'validation')
        request = SemanticRequest(ledger.context_id, (SemanticItem('assertion', text, refs),),
                                  tuple(e for e in ledger.evidence if e.evidence_id in refs))
        try:
            response = adapter.verify(request)
            validator = validate_simulated_response if self._simulation else validate_local_response
            decision = validator(request, response)[0]
            # Entailment never overrides a mismatch of entity, role, negation or
            # the entire bounded proposition. No score is an acceptance token.
            status = decision.status
            if status == SupportStatus.SUPPORTED and not matching:
                status = SupportStatus.INSUFFICIENT_EVIDENCE
            return OutputSupport(status, decision.reason_code, decision.method, self._simulation)
        except TimeoutError:
            reason = 'VERIFIER_TIMEOUT'
        except SemanticProtocolError:
            reason = 'INVALID_SEMANTIC_PROTOCOL'
        except ValueError as exc:
            reason = 'VERIFIER_CONTEXT_OVERFLOW' if str(exc) == 'VERIFIER_CONTEXT_OVERFLOW' else 'VERIFIER_ERROR'
        except Exception:
            reason = 'VERIFIER_ERROR'
        return OutputSupport(SupportStatus.ERROR, reason, 'semantic_adapter', self._simulation)

    def _prose(self, text, ledger, refs):
        """Citation-bound prose: structural binding AND complete semantic checks.

        Reverse coverage is rejection-only, never evidence for a served fact.
        Every selected source remains in the conflict audit, including uncited
        chunks. One protocol/model failure fails the entire candidate closed.
        """
        known = {e.evidence_id: e for e in ledger.evidence}
        premise = '\n'.join(known[i].text for i in refs)
        reason = prose_preconditions(text, premise, (e.text for e in ledger.evidence))
        if reason:
            return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, reason, 'prose_validation')
        adapter = self._adapter if self._simulation else get_f1_semantic_verifier()
        if not self._simulation and type(adapter) is not QualifiedLocalNLI:
            return OutputSupport(SupportStatus.ERROR, 'UNQUALIFIED_BACKEND', 'validation')
        cited = tuple(known[i] for i in refs)
        items = [SemanticItem('support:whole', text, refs)]
        # Whole-claim checking is retained even when individual sentences pass.
        for i, statement in enumerate(prose_statements(text)):
            items.append(SemanticItem(f'support:{i}', statement, refs))
        # Candidate text is used only as the premise of a rejection-only reverse
        # coverage check; it never enters the trusted ledger or served citations.
        first = cited[0]
        candidate = Evidence(ledger.context_id, 'candidate-audit', first.doc_id,
            first.doc_version, first.doc_hash, first.page, 1, len(text.splitlines()), text, fingerprint(text))
        items.append(SemanticItem('reverse:coverage', premise, (candidate.evidence_id,)))
        audit = list(cited) + [candidate]
        seen = set()
        context_entries = {}
        for evidence in ledger.evidence:
            if evidence.evidence_id.startswith('citation:'):
                continue
            for statement in (evidence.text, *prose_statements(evidence.text)):
                normalized = ' '.join(statement.split())
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                eid = f'context-audit:{len(seen)}'
                entry = Evidence(ledger.context_id, eid, evidence.doc_id, evidence.doc_version,
                    evidence.doc_hash, evidence.page, 1, len(statement.splitlines()), statement, fingerprint(statement))
                audit.append(entry)
                items.append(SemanticItem(f'context:{len(seen)-1}', text, (eid,)))
                context_entries[f'context:{len(seen)-1}'] = entry
        scope_checks = []
        for index, (base, statement, missing) in enumerate(prose_qualification_candidates(
                premise, (e.text for e in ledger.evidence if not e.evidence_id.startswith('citation:')))):
            eid = f'qualification-audit:{index}'
            audit.append(Evidence(ledger.context_id, eid, first.doc_id, first.doc_version,
                first.doc_hash, first.page, 1, len(base.splitlines()), base, fingerprint(base)))
            items.extend((SemanticItem(f'scope:forward:{index}', text, (eid,)),
                          SemanticItem(f'scope:reverse:{index}', base, (candidate.evidence_id,)),
                          SemanticItem(f'scope:qualified:{index}', statement, (candidate.evidence_id,))))
            scope_checks.append((index, missing))
        request = SemanticRequest(ledger.context_id, tuple(items), tuple(audit))
        try:
            validator = validate_simulated_response if self._simulation else validate_local_response
            decisions = []
            # The pinned CPU adapter evaluates items sequentially. Keep each
            # SemanticRequest bounded; its unchanged 10-second deadline and
            # BUSY guard apply to every batch. No item is retried or omitted.
            for start in range(0, len(request.items), 8):
                batch = SemanticRequest(request.context_id, request.items[start:start + 8], request.evidence)
                response = adapter.verify(batch)
                decisions.extend(validator(batch, response))
            by_id = {d.claim_id:d for d in decisions}
            for decision in decisions:
                if decision.claim_id.startswith('context:') and decision.status == SupportStatus.CONTRADICTED:
                    competing = context_entries[decision.claim_id]
                    comparison = proposition_comparability(text, competing.text)
                    # Comparable and ambiguous contradictions both fail closed.
                    # Only an independent deterministic DISTINCT proof discounts
                    # this verdict. Every source/NLI item and provenance remains.
                    if comparison.state != PropositionComparability.DISTINCT:
                        return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'SOURCE_CONFLICT', 'conflict_detection', self._simulation)
            for index, missing in scope_checks:
                related = any(by_id[f'scope:{direction}:{index}'].status == SupportStatus.SUPPORTED
                              for direction in ('forward', 'reverse'))
                covered = by_id[f'scope:qualified:{index}'].status == SupportStatus.SUPPORTED
                if related and (missing or not covered):
                    return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'PROSE_UNCITED_QUALIFICATION',
                                         'prose_validation', self._simulation)
            required = [d for d in decisions if d.claim_id.startswith(('support:', 'reverse:'))]
            if any(d.status == SupportStatus.ERROR for d in decisions):
                return OutputSupport(SupportStatus.ERROR, 'PROSE_VERIFIER_ERROR', 'semantic_adapter', self._simulation)
            if not all(d.status == SupportStatus.SUPPORTED for d in required):
                return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'PROSE_NOT_FULLY_SUPPORTED',
                    'simulated_semantic' if self._simulation else 'qualified_local_nli', self._simulation)
            return OutputSupport(SupportStatus.SUPPORTED, 'PROSE_FULL_CLAIM_AND_CONTEXT_VERIFIED',
                'simulated_semantic' if self._simulation else 'qualified_local_nli', self._simulation)
        except TimeoutError:
            reason = 'VERIFIER_TIMEOUT'
        except SemanticProtocolError:
            reason = 'INVALID_SEMANTIC_PROTOCOL'
        except ValueError as exc:
            reason = 'VERIFIER_CONTEXT_OVERFLOW' if str(exc) == 'VERIFIER_CONTEXT_OVERFLOW' else 'VERIFIER_ERROR'
        except Exception:
            reason = 'VERIFIER_ERROR'
        return OutputSupport(SupportStatus.ERROR, reason, 'semantic_adapter', self._simulation)


    def evaluate_proof(self, parent, ledger):
        """Shared production proof path, including untrusted proof validation."""
        if bounded_conflict(e.text for e in ledger.evidence):
            return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'SOURCE_CONFLICT', 'conflict_detection')
        decision = ClaimSupportController().verify(parent, ledger)
        return OutputSupport(decision.status, decision.reason_code, 'deterministic_proof')

    def evaluate(self, text, ledger, refs):
        failure = audit_ledger(ledger)
        if failure:
            return OutputSupport(*failure, 'validation')
        known = {e.evidence_id: e for e in ledger.evidence}
        if not refs or len(set(refs)) != len(refs) or any(i not in known for i in refs):
            return OutputSupport(SupportStatus.ERROR, 'INVALID_EVIDENCE_REFERENCES', 'validation')
        # Do not let extraction or NLI bypass an unresolved numeric format.
        if ambiguous_number_format(text) or any(ambiguous_number_format(e.text) for e in ledger.evidence):
            return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'AMBIGUOUS_NUMBER_FORMAT', 'validation')
        if bounded_conflict(e.text for e in ledger.evidence):
            return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'SOURCE_CONFLICT', 'conflict_detection')
        cited = tuple(known[i] for i in refs)
        premise = '\n'.join(e.text for e in cited)
        if instruction_data(text) or instruction_data(premise):
            return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'INSTRUCTION_DATA', 'validation')
        proof = bind_declared_proof(text, refs, ledger)
        if proof is not None:
            # Every source line must be within the controlled declaration grammar.
            if any(parse_bound_proposition(s) is None and not re.fullmatch(
                r'.+? \[[^\[\]]+\]: disjoint\(.+?, .+?\); attribute=\w+; unit=\w+\.', s)
                for e in cited for s in e.text.splitlines()):
                return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'UNBOUND_QUALIFICATION', 'validation')
            atom = Atom('proof', text, 0, len(text), refs, proof)
            return self.evaluate_proof(ParentClaim('output', ledger.context_id, text, (atom,)), ledger)
        target = parse_bound_proposition(text)
        # A controlled proposition cannot inherit an unknown qualification about
        # its entity from another sentence in the same request.
        if target:
            for e in ledger.evidence:
                for statement in source_assertions(e.text):
                    if (parse_bound_proposition(statement) is None and re.match(
                            r'(?:if\b|only\b|unless\b|provided\b|except\b|nếu\b|chỉ\b|trừ\b|điều kiện\b)',
                            statement, re.IGNORECASE)):
                        return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'UNBOUND_QUALIFICATION', 'validation')
                    if re.search(r'(?<!\w)' + re.escape(target.entity) + r'(?!\w)', statement, re.IGNORECASE):
                        if parse_bound_proposition(statement) is None:
                            return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'UNBOUND_QUALIFICATION', 'validation')
        sources = source_propositions(premise)
        if target and target.kind in ('quantity', 'date'):
            # Natural-language quantity proofs require one complete assertion.
            comparable = [p for p in sources if (p.kind, p.entity, p.scope, p.attribute, p.unit, p.relation) == (
                target.kind, target.entity, target.scope, target.attribute, target.unit, target.relation)]
            source = comparable[0] if len(set(comparable)) == 1 else None
            if source and target.relation == '=' and all(parse_bound_proposition(s) is not None for s in source_assertions(premise)):
                return OutputSupport(SupportStatus.SUPPORTED if source.value == target.value else SupportStatus.CONTRADICTED,
                                     'BOUND_VALUE_EQUALITY' if source.value == target.value else 'BOUND_VALUE_CONTRADICTION', 'deterministic_proof')
        if _same_text(text, premise):
            unique_sources = {e.text for e in ledger.evidence if not e.evidence_id.startswith('citation:')}
            # Unknown context cannot be silently ignored to turn an excerpt into
            # a fact. Complete extraction keeps all qualifications and negatives.
            if len(unique_sources) == 1 and _same_text(next(iter(unique_sources)), premise):
                return OutputSupport(SupportStatus.SUPPORTED, 'COMPLETE_SOURCE_EXTRACTION', 'deterministic_extraction')
            if target and target in sources and all(parse_bound_proposition(s) is not None for s in source_assertions(premise)):
                return OutputSupport(SupportStatus.SUPPORTED, 'COMPLETE_ASSERTION_EXTRACTION', 'deterministic_extraction')
        if target and target.kind == 'semantic' and sources and all(
                parse_bound_proposition(s) is not None for s in source_assertions(premise)):
            comparable = [p for p in sources if (p.kind, p.entity, p.scope, p.attribute, p.unit) ==
                          (target.kind, target.entity, target.scope, target.attribute, target.unit)]
            if comparable:
                return self._nli(text, ledger, refs, target in comparable)
        # Split only explicit top-level conjunctions; every component must pass.
        parts = re.split(r' and | và |\n+', text)
        if len(parts) > 1 and all(parse_bound_proposition(p) is not None for p in parts):
            decisions = [self.evaluate(p, ledger, refs) for p in parts]
            if all(d.status == SupportStatus.SUPPORTED for d in decisions):
                method = ('deterministic_compound' if all(d.method.startswith('deterministic') for d in decisions)
                          else 'qualified_local_nli_compound')
                return OutputSupport(SupportStatus.SUPPORTED, 'ALL_COMPONENTS_SUPPORTED', method, any(d.simulated for d in decisions))
        if target is None:
            return self._prose(text, ledger, refs)
        return OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'OUTSIDE_BOUND_SUPPORT_SCOPE', 'validation')

    def verify_claims(self, claims, chunks):
        """Consume citation-validated schema claims; never change quote/locator.

        The premise is the exact physical cited span. Original chunk identities
        are retained in evidence_span; all request chunks are conflict-only input.
        """
        context_id = uuid.uuid4().hex
        evidence = tuple(Evidence(context_id, f'source:{i}', c.doc_id, c.doc_version, c.doc_hash,
            c.page_number, c.start_line, c.end_line, c.text, fingerprint(c.text)) for i, c in enumerate(chunks))
        identities = tuple(dict.fromkeys(DocumentIdentity(e.doc_id, e.doc_version, e.doc_hash) for e in evidence))
        selected = tuple(dict.fromkeys(e.doc_id for e in evidence))
        facts, conditions = declared_facts(evidence)
        ledger = EvidenceLedger(context_id, selected, evidence, facts, conditions, documents=identities)
        supported, rejected, decisions = [], [], []
        for index, raw in enumerate(claims):
            claim = raw.model_copy(deep=True)
            claim.thinking, claim.section = None, None
            source = [c for c in chunks if (c.doc_id, c.page_number, c.doc_version, c.doc_hash) ==
                      (claim.cited_doc_id, claim.cited_page, claim.doc_version, claim.doc_hash)
                      and c.start_line <= claim.cited_end_line and claim.cited_start_line <= c.end_line]
            lines = {c.start_line + i: line for c in source for i, line in enumerate(c.text.splitlines())}
            span = range(claim.cited_start_line, claim.cited_end_line + 1)
            if not all(n in lines for n in span):
                decision = OutputSupport(SupportStatus.ERROR, 'UNBOUND_CITATION_SPAN', 'validation')
            else:
                text = '\n'.join(lines[n] for n in span)
                if not _same_text(text, claim.evidence_quote):
                    decision = OutputSupport(SupportStatus.INSUFFICIENT_EVIDENCE, 'PARTIAL_CITATION_CONTEXT', 'validation')
                else:
                    bound = Evidence(context_id, f'citation:{index}', claim.cited_doc_id, claim.doc_version, claim.doc_hash,
                        claim.cited_page, claim.cited_start_line, claim.cited_end_line, text, fingerprint(text))
                    bound_facts, bound_conditions = declared_facts((bound,))
                    scoped = EvidenceLedger(context_id, selected, evidence + (bound,), facts + bound_facts,
                                            conditions + bound_conditions, documents=identities)
                    decision = self.evaluate(claim.claim_text, scoped, (bound.evidence_id,))
            decisions.append(decision)
            if decision.status == SupportStatus.SUPPORTED:
                claim.evidence_span = dict(claim.evidence_span or {}, context_id=context_id,
                    chunk_ids=sorted({c.chunk_id for c in source}), support_status=decision.status.value,
                    support_method=decision.method, support_reason=decision.reason,
                    execution_kind='SIMULATED' if decision.simulated else 'DETERMINISTIC' if decision.method.startswith('deterministic') else 'LOCAL_NLI')
                supported.append(claim)
            else:
                claim.verification_status = decision.reason
                rejected.append(claim)
        return supported, rejected, decisions
