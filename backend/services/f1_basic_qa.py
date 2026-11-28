"""Document question answering with bounded context and checked source locations."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import time
from backend.core.config import settings
from backend.core.guardrails import detect_prompt_injection
from backend.algorithms.f1_claim_support import bounded_conflict, source_assertions
from backend.algorithms.citation_verifier import verify_citations, build_f1_citation_lookup
from backend.providers.f1_basic_provider import BasicProvider
from backend.providers.llm_provider import GenerationError
from backend.services.qa_service import expand_contextual_query, claim_schema_to_algorithm, verification_result_to_schema
from backend.core.schemas import GeneratedClaim
from backend.repositories.workspace_repository import workspace_repository
from backend.vendor.surfsense.prompt import build_context, resolve_citations, _TOKEN, _outside_code
from backend.vendor.surfsense.history import build_messages
from backend.vendor.surfsense.types import Hit, ChatMessage, MessageRole
from backend.services.f1_session_runtime import inference_slot
from backend.vendor.surfsense.admission.cost import request_cost

DISCLOSURE = 'Citation locations and source text were checked. Answer meaning has not been independently semantically verified; conflict checks cover the displayed context only.'

def conflict_evidence(chunks):
    """Locate explicit contradictory assertions from distinct sources."""
    assertions = [source_assertions(chunk.text) for chunk in chunks]
    for left, chunk in enumerate(chunks):
        for right in range(left + 1, len(chunks)):
            other = chunks[right]
            if chunk.doc_id == other.doc_id or not bounded_conflict((chunk.text, other.text)):
                continue
            for a in assertions[left]:
                for b in assertions[right]:
                    if a != b and bounded_conflict((a, b)) and not (
                        bounded_conflict((a,)) or bounded_conflict((b,))
                    ):
                        return (left + 1, a), (right + 1, b)
    return None


def explicit_abstention(text):
    """Accept only a standalone abstention marker, optionally Markdown-wrapped."""
    return bool(re.fullmatch(r'(?:\*\*INSUFFICIENT_EVIDENCE\*\*|__INSUFFICIENT_EVIDENCE__|`INSUFFICIENT_EVIDENCE`|INSUFFICIENT_EVIDENCE)[.!]?', text))


class BasicQA:
    def __init__(self, repository=None, provider=None):
        self.repository = repository or workspace_repository
        self.provider = provider or BasicProvider()

    def answer_question(self, query, selected_doc_ids=None, conversation_history=None, progress=lambda event:None, cancelled=lambda:False):
        start=time.perf_counter()
        with inference_slot():
            result=self._answer(query, selected_doc_ids, conversation_history or [], progress, cancelled)
        result['latency_ms']=round((time.perf_counter()-start)*1000,2)
        return result

    def _answer(self, query, selected, history, progress, cancelled):
        def abstain(message, status='ABSTAINED_INSUFFICIENT_EVIDENCE'):
            from backend.services.answer_messages import vietnamese
            vi = vietnamese(query)
            chinese = requested_languages(query)==('zh',)
            if status == 'ABSTAINED_INSUFFICIENT_EVIDENCE':
                message = ("Mình chưa tìm thấy đủ thông tin trong các tài liệu đã chọn để trả lời câu hỏi này." if vi
                           else "I couldn't find enough information in the selected documents to answer this question.")
            elif status == 'ABSTAINED_NO_SOURCE_SELECTED':
                message = ("Bạn hãy chọn tài liệu mà mình cần phân tích nhé." if vi
                           else "Please select the documents you would like me to analyze.")
            elif status == 'ABSTAINED_INVALID_SELECTION':
                message = ('Một tài liệu đã chọn không còn tồn tại. Bạn hãy chọn lại tài liệu nhé.' if vi else 'A selected document is no longer available. Please select your documents again.')
            elif status == 'BLOCKED_BY_SAFEGUARD':
                message = ("Mình không thể làm theo yêu cầu truy cập dữ liệu ngoài tài liệu đã chọn." if vi
                           else "I can't follow instructions to access information outside your selected documents.")
            if chinese:
                message={'ABSTAINED_INSUFFICIENT_EVIDENCE':'所选文档未提供足够信息来回答这个问题。',
                    'ABSTAINED_NO_SOURCE_SELECTED':'请先选择需要分析的文档。',
                    'ABSTAINED_INVALID_SELECTION':'所选文档已不可用，请重新选择。',
                    'BLOCKED_BY_SAFEGUARD':'无法访问所选文档之外的信息。'}.get(status,message)
            return dict(route='QA_FLOW',status=status,message=message,validated_claims=[],hallucination_flags=[],citations=[],verification_method='citation_integrity_only',semantic_verified=False)
        from backend.algorithms.answer_language import requested_languages,language_constraint,language_valid,repair_preserves
        try:
            from backend.algorithms.claim_evidence import select_sources,bind_fact,summary_excerpts,deduplicate_items
        except ImportError:
            select_sources=lambda *args,**kwargs: []
            bind_fact=lambda *args,**kwargs: dict(items=[],state='error',components=[])
            summary_excerpts=lambda *args,**kwargs: []
            deduplicate_items=lambda items: items
        languages=requested_languages(query)
        bilingual=len(languages)==2
        if isinstance(self.provider,BasicProvider):self.provider.bilingual_request=bilingual
        if not query.strip() or len(query)>4096 or len(history)>20 or any(len(t.get('content',''))>8000 for t in history):
            raise ValueError('Question or conversation is too large. Start a new conversation or shorten the question.')
        if detect_prompt_injection(query)[0]:
            return abstain('Request blocked by the prompt-injection safeguard.','BLOCKED_BY_SAFEGUARD')
        selection=self.repository.get_selected_doc_ids() if selected is None else selected
        if not selection:
            return abstain('Select at least one document to ask a question.','ABSTAINED_NO_SOURCE_SELECTED')
        canonical=[]
        for key in selection:
            doc=self.repository.documents.get(key)
            if doc is None:
                return abstain('A selected document no longer exists. Refresh the library and select it again.','ABSTAINED_INVALID_SELECTION')
            canonical.append(doc.doc_id)
        authorized=[c.model_copy(deep=True) for c in self.repository.chunks if c.doc_id in canonical]
        if not authorized:
            return abstain('The selected documents contain no readable text.')
        # Previous replies are reference aids only. Selection-mismatched history is discarded.
        scope=json.dumps(sorted(canonical),ensure_ascii=False)
        history=[t for t in history if t.get('role') in ('user','assistant') and t.get('scope',scope)==scope and not detect_prompt_injection(t.get('content',''))[0]][-8:]
        if re.search(r'^(?:new topic|change topic|chuyển chủ đề|chủ đề mới)\b',query,re.I):
            history=[]
        retrieval_query=expand_contextual_query(query,history)
        progress(dict(type='status',stage='retrieving'))
        budget=9000
        complete=len(authorized)<=12 and sum(len(c.text) for c in authorized)<=budget
        if complete:
            chosen=authorized
        else:
            ranked=self.repository.search(retrieval_query,top_k=12,selected_doc_ids=canonical)
            threshold=settings.dense_tau_rel if self.repository.dense_available else settings.bm25_tau_rel
            if not ranked or ranked[0].score < threshold:
                return abstain('No sufficiently relevant evidence was found in the selected documents.')
            chosen=[]; used=0
            # Keep source diversity for synthesis without another retrieval/model pass.
            ordered=[]
            for doc_id in canonical:
                candidate=next((c for c in ranked if c.doc_id==doc_id),None)
                if candidate: ordered.append(candidate)
            ordered += [c for c in ranked if c.chunk_id not in {x.chunk_id for x in ordered}]
            for chunk in ordered:
                if used+len(chunk.text)<=budget:
                    chosen.append(chunk.model_copy(deep=True)); used+=len(chunk.text)
        if not chosen:
            return abstain('Relevant passages exceed the context budget. Ask a narrower question.')
        # Exclude obvious embedded command passages rather than follow their instructions.
        chosen=[c for c in chosen if not detect_prompt_injection(c.text)[0]]
        if not chosen:
            return abstain('The retrieved passages contain embedded instructions and cannot safely support this answer.')
        complete = complete and len(chosen)==len(authorized)
        # Include the actual grounded prompt and whole history in the demand estimate.
        from backend.vendor.surfsense.admission.cost import _text_tokens
        from backend.vendor.surfsense.prompt import prompting
        SYSTEM_PROMPT=prompting.load("backend.vendor.surfsense","capable")+"\n"+language_constraint(languages)
        demand = 896 + _text_tokens(SYSTEM_PROMPT) + _text_tokens(query)
        demand += sum(_text_tokens(c.text)+64 for c in chosen)
        demand += sum(_text_tokens(t['content'])+8 for t in history)
        plan=self.provider.prepare(demand) if hasattr(self.provider,'prepare') else None
        window=plan.num_ctx if plan else 8192
        output_cap=plan.num_predict if plan else 1200
        minimum_output=256
        turns=[ChatMessage(i,MessageRole(t['role']),dict(text=t['content'])) for i,t in enumerate(history)]
        # The upstream conservative request-cost utility prices dense scripts
        # separately. Keep system/question verbatim and drop only whole excerpts.
        while chosen:
            hits=[Hit(i,c.doc_id,c.start_line,c.end_line,c.doc_name+' | page '+str(c.page_number),c.text) for i,c in enumerate(chosen,1)]
            context=build_context(hits,'capable')
            context=type(context)(context.instruction+'\n'+language_constraint(languages),context.excerpts,context.citations)
            excerpts="<untrusted_document_data>\n"+context.excerpts+"\n</untrusted_document_data>"
            base=asyncio.run(build_messages(context.instruction,[],query,excerpts=excerpts,history_budget=0))
            cost=request_cost(base.messages,0,budget=window,slots=1)
            history_room=min(window//4,max(0,window-cost-minimum_output-128))
            prompt=asyncio.run(build_messages(context.instruction,turns,query,excerpts=excerpts,history_budget=history_room))
            cost=request_cost(prompt.messages,0,budget=window,slots=1)
            output_budget=min(output_cap,window-cost-128)
            if output_budget>=minimum_output:break
            complete=False
            chosen=chosen[:-1]
        if not chosen:
            return abstain('The complete question, grounding instructions and relevant source excerpts do not fit the selected safe context. Ask a narrower question or select fewer documents.')
        manifest=[(c.chunk_id,c.doc_hash,c.doc_version,c.text) for c in chosen]
        pair = conflict_evidence(chosen)
        if pair:
            vietnamese = bool(re.search(r'[\u0102-\u01b0\u1ea0-\u1ef9]', query))
            intro = (
                'Hai ngu\u1ed3n \u0111\u01b0a ra th\u00f4ng tin m\u00e2u thu\u1eabn:'
                if vietnamese else 'The sources disagree:'
            )
            raw = 'SOURCE_CONFLICT ' + intro + ' ' + '\n\n'.join(
                f'{statement} [{source_id}]' for source_id, statement in pair
            )
        elif plan:
            progress(dict(type='status',stage='generating'))
            raw=self.provider.generate(prompt.messages,progress,cancelled,plan=plan,output_tokens=output_budget).strip()
        else:
            progress(dict(type='status',stage='generating'))
            raw=self.provider.generate(prompt.messages,progress,cancelled).strip()
        def reject(reason, **details):
            runtime = Path(os.getenv('F1_RUNTIME_DIR', '.'))
            if os.getenv('F1_SYNTHETIC_DIAGNOSTICS') == '1':
                runtime.mkdir(parents=True,exist_ok=True)
                with (runtime/'answer-rejections.jsonl').open('a',encoding='utf-8') as log:
                    log.write(json.dumps(dict(reason=reason,**details))+'\n')
            raise GenerationError('GENERATION_INVALID_RESPONSE')

        omitted=0
        if isinstance(self.provider,BasicProvider) and not pair and not raw.startswith('{'):
            return abstain('The structured claim contract was unavailable.')
        if raw.startswith('{'):
            try:
                structured=json.loads(raw)
                model_abstained=structured['status']=='insufficient_evidence' and structured['facts']==[]
                if not model_abstained and (structured['status']!='answer' or not structured['facts']):
                    reject('structured_answer')
                facts=[f for f in structured['facts'] if isinstance(f,dict)]
                invalid=[]
                for index,fact in enumerate(facts):
                    for field,language in zip(('text','translation'),languages):
                        value=fact.get(field)
                        if isinstance(value,str) and not language_valid(value,language,chosen):
                            invalid.append((index,field,language,value))
                repair_info=dict(attempts=0,latency_ms=0,outcome='not_needed')
                if invalid and hasattr(self.provider,'repair_language'):
                    entries=[dict(language=language,prose=value) for _,_,language,value in invalid]
                    # A repair cannot choose evidence: keep the original arrays immutable.
                    initial_metrics=dict(self.provider.metrics);repair_start=time.perf_counter()
                    repair_info['attempts']=1
                    try:
                        repair_refs={n for i,_,_,_ in invalid for n in (facts[i].get('sources',[]) if isinstance(facts[i].get('sources'),list) else []) if type(n) is int and 1<=n<=len(chosen)}
                        proposal=self.provider.repair_language(entries,[dict(text=chosen[n-1].text) for n in sorted(repair_refs)],progress,cancelled,plan=plan,output_tokens=output_budget)
                        try:proposed=json.loads(proposal)['texts']
                        except (ValueError,KeyError,TypeError):proposed=[]
                        if isinstance(proposed,list) and len(proposed)==len(invalid):
                            for (index,field,language,original),value in zip(invalid,proposed):
                                refs=facts[index].get('sources',[])
                                source_chunks=[chosen[n-1] for n in refs if type(n) is int and 1<=n<=len(chosen)] if isinstance(refs,list) else []
                                if isinstance(value,str) and language_valid(value,language,chosen) and repair_preserves(original,value,source_chunks):
                                    facts[index][field]=value
                        repair_info['outcome']='validated' if all(language_valid(facts[i][field],lang,chosen) for i,field,lang,_ in invalid) else 'fallback'
                        repair_info['model_metrics']=dict(self.provider.metrics)
                    finally:
                        repair_info['latency_ms']=round((time.perf_counter()-repair_start)*1000,2)
                        self.provider.metrics=initial_metrics
                elif invalid:repair_info['outcome']='unavailable'
                self.provider.metrics=dict(self.provider.metrics,language_repair=repair_info)
                admissible=[]
                for c in chosen:
                    doc=self.repository.documents.get(c.doc_id)
                    valid=bool(doc and c.doc_id in canonical and c.doc_hash==doc.file_hash and c.doc_version==doc.version_id
                               and 1<=c.page_number<=doc.page_count and 1<=c.start_line<=c.end_line)
                    admissible.append(c if valid else None)
                rendered=[];omitted=0;bound_items=[];binding_states=[]
                for fact in facts:
                    text=fact.get('text');translation=fact.get('translation') if bilingual else None
                    labels=fact.get('sources')
                    values=(text,translation) if bilingual else (text,)
                    if any(not isinstance(v,str) or not v.strip() or _TOKEN.search(v) or not language_valid(v,lang,chosen) for v,lang in zip(values,languages)):
                        omitted+=1;continue
                    try:
                        bound=bind_fact(text,labels,admissible,translation,languages)
                    except Exception:
                        bound=dict(items=[],state='error',components=[])
                    binding_states.append(bound['state'])
                    bound_items.extend(bound['items'])
                    if not bound['items'] or bound['state'].startswith('partial_'):omitted+=1
                bound_items=deduplicate_items(bound_items)
                additions=summary_excerpts(query,admissible,bound_items,languages)
                bound_items=deduplicate_items(bound_items+additions)
                self.provider.metrics=dict(self.provider.metrics,evidence_binding=dict(states=binding_states,
                    raw_facts=len(facts),published_items=len(bound_items),summary_source_additions=len(additions),model_abstained=model_abstained))
                for item in bound_items:
                    suffix=' '+''.join(f'[{n}]' for n in item['sources'])
                    rendered.append(item['text'].strip()+suffix)
                    if bilingual:rendered.append(item['translation'].strip()+suffix)
                if not rendered:
                    if model_abstained:return abstain('No supported answer in selected excerpts.')
                    if bilingual and any(not isinstance(f.get('translation'),str) for f in facts):
                        reject('structured_translation')
                    # Binding failure is not evidence that a document lacks facts.
                    if any(state!='absent' for state in binding_states):reject('binding_uncertain')
                    return abstain('The proposed facts are absent from the current excerpts.')
                raw='\n\n'.join(rendered)
            except (KeyError,TypeError,ValueError):
                reject('structured_answer')
        marker_text = _TOKEN.sub('', raw).strip()
        valid_labels = {c.source_id for c in context.citations}
        labels = [int(m.group(1) or m.group(2)) for m in _TOKEN.finditer(raw)]
        if explicit_abstention(marker_text) and set(labels) <= valid_labels:
            return abstain('The selected source excerpts do not establish the requested information.')
        conflict=raw.startswith('SOURCE_CONFLICT')
        raw=re.sub(r'^SOURCE_CONFLICT\s*[:.-]?\s*','',raw).strip()
        # Check each answer paragraph before publishing any generated prose.
        paragraphs=[p.strip() for p in re.split(r'\n\s*\n|\n(?=[-*] )',raw) if p.strip()]
        valid={c.source_id for c in context.citations}
        def ids(text):
            found=[]
            _outside_code(text,lambda span: found.extend(int(m.group(1) or m.group(2)) for m in _TOKEN.finditer(span)) or span)
            return found
        missing = [i for i, paragraph in enumerate(paragraphs, 1) if not ids(paragraph)]
        unknown = sorted({label for paragraph in paragraphs for label in ids(paragraph)} - valid)
        markup = bool(re.search(r'<\s*/?\s*[a-zA-Z][^>]*>', raw))
        embedded_marker = 'INSUFFICIENT_EVIDENCE' in raw
        if missing or unknown or markup or embedded_marker:
            reject('answer_format', uncited_paragraphs=missing, unknown_labels=unknown,
                   forbidden_markup=markup, nonstandalone_abstention_marker=embedded_marker)
        answer, used=resolve_citations(raw,context.citations)
        claims=[]
        for citation in used:
            chunk=chosen[citation.source_id-1]
            finding='\n\n'.join(p for p in paragraphs if citation.source_id in ids(p))
            # The exact chunk, not a model-invented quote, supplies the clickable source span.
            claims.append(GeneratedClaim(claim_text=finding,cited_doc_id=chunk.doc_id,cited_page=chunk.page_number,
                cited_start_line=chunk.start_line,cited_end_line=chunk.end_line,doc_version=chunk.doc_version,doc_hash=chunk.doc_hash,evidence_quote=chunk.text))
        checked=verification_result_to_schema(verify_citations([claim_schema_to_algorithm(c) for c in claims],build_f1_citation_lookup(chosen),strict=True,allow_locator_correction=False,theta_match=settings.theta_match))
        if len(checked.validated_claims)!=len(claims) or not claims:
            reject('citation_verification', proposed_claims=len(claims), validated_claims=len(checked.validated_claims))
        # No stale answer after deletion, replacement or concurrent library mutation.
        current={c.chunk_id:c for c in self.repository.chunks}
        if any(k not in current or (current[k].doc_hash,current[k].doc_version,current[k].text)!=(h,v,t) for k,h,v,t in manifest):
            reject('source_snapshot_changed')
        if omitted:
            note=('Mình chưa thể đối chiếu chắc chắn một phần câu trả lời với các đoạn trích; thông tin đã đối chiếu được giữ lại ở trên.' if languages[0]=='vi' or bilingual else
                  '部分回答尚无法与原文可靠对应；已对应的信息保留在上方。' if languages[0]=='zh' else 'I could not reliably match part of the proposed answer to the excerpts; the supported information is retained above.')
            answer+='\n\n'+note
        coverage='complete_selected_text' if complete and len(chosen)==len(authorized) else 'retrieved_excerpts_only'
        return dict(route='QA_FLOW',status='ANSWERED_WITH_CONFLICT' if conflict else 'ANSWERED_CITATION_CHECKED',
            answer=answer,message=DISCLOSURE,validated_claims=[dict(c.model_dump(),citation_index=ref.chunk_id) for c,ref in zip(checked.validated_claims,used)],hallucination_flags=[],
            citations=[dict(source_id=c.chunk_id,chunk_id=c.chunk_id,doc_id=chosen[c.source_id-1].doc_id,page=chosen[c.source_id-1].page_number) for c in used],
            verification_method='citation_integrity_only',semantic_verified=False,coverage=coverage,
            context_chunk_count=len(chosen),selected_chunk_count=len(authorized),
            selected_doc_ids=canonical,context_sha256=hashlib.sha256(json.dumps(manifest,ensure_ascii=False).encode()).hexdigest(),
            conflict_assessment='confirmed' if pair else ('model_reported_unresolved' if conflict else 'not_established'),
            model_metrics={} if pair else self.provider.metrics,context_budget=dict(window=window,estimated_input_tokens=cost,output_tokens=output_budget,history_budget=history_room),suggested_questions=[])

basic_qa=BasicQA()
