"""At most one safe context per approved model, then one acceptance campaign."""
from dataclasses import asdict
import datetime,json,sys,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace')
from backend.services.f1_adaptive_memory import AdaptivePolicy,PREFERRED,FALLBACK
from tools.resources import AdmissionDenied

def qualify():
    out=ROOT/'validation/adaptive-demand';out.mkdir(exist_ok=True)
    policy=AdaptivePolicy('http://127.0.0.1:18684',ROOT/'.runtime/adaptive-demand-policy.json')
    state=policy.read()
    if state.get('selected') and state.get('qualification_passed'):
        print('Using already qualified configuration:',json.dumps(state['selected']),flush=True)
        return True
    if state.get('qualification_complete'):
        print('Bounded qualification already completed; no automatic model retry.',flush=True)
        return False
    with httpx.Client(base_url='http://127.0.0.1:18682',headers={'X-Workspace-ID':'f1-session-b-validation'},trust_env=False,timeout=150) as client:
        library=client.get('/api/documents');library.raise_for_status()
        known={d['doc_name']:d['doc_id'] for d in library.json()}
        for name in ('en-cedar.pdf','vi-sao-mai.pdf'):
            if name not in known:
                path=ROOT/'validation/fixtures'/name
                response=client.post('/api/documents/upload',files={'file':(name,path.read_bytes(),'application/pdf')});response.raise_for_status();known[name]=response.json()['document']['doc_id']
        results=[]
        for name in (PREFERRED,FALLBACK):
            policy.recover()
            plan=policy.propose(name)
            if plan is None:
                results.append(dict(model=name,status='NOT_RUN_UNSAFE_PREDICTION',reason='No task-sized context fits measured headroom and the protected allocation budget.'))
                print(name,'NO SAFE CONTEXT; no inference attempted.',flush=True)
                continue
            state=policy.read();state.pop('selected',None);state.update(candidate=asdict(plan),stopped=False)
            policy.write(state)
            print('QUALIFY',json.dumps(asdict(plan)),flush=True)
            attempts=[];passed=True
            for case in [dict(id='Cedar-explanation',query='Why must participants bring laptops to the Cedar workshop?',doc='en-cedar.pdf',word='spreadsheet',page=2),dict(id='Vietnamese-direct',query='Buổi tập huấn Sao Mai bắt đầu lúc mấy giờ?',doc='vi-sao-mai.pdf',word='09:10',page=1)]:
                start=time.perf_counter()
                try:
                    response=client.post('/api/chat',json=dict(query=case['query'],selected_doc_ids=[known[case['doc']]],verification_profile='academic_grounded'))
                    answer=response.json()
                    valid=response.status_code==200 and answer.get('status','').startswith('ANSWERED') and case['word'] in answer.get('answer','').lower() and any(c['cited_page']==case['page'] and c['cited_doc_id']==known[case['doc']] for c in answer.get('validated_claims',[]))
                    row=dict(case=case,http_status=response.status_code,response=answer,e2e_ms=round((time.perf_counter()-start)*1000,2),qualified=valid)
                except Exception as exc:
                    valid=False;row=dict(case=case,error=type(exc).__name__+': '+str(exc),e2e_ms=round((time.perf_counter()-start)*1000,2),qualified=False)
                attempts.append(row)
                print(case['id'],'PASS' if valid else 'FAIL',row['e2e_ms'],'ms',flush=True)
                (out/'qualification-current.json').write_text(json.dumps(dict(model=name,plan=asdict(plan),attempts=attempts),ensure_ascii=False,indent=2),encoding='utf-8')
                if not valid:
                    passed=False;break
            results.append(dict(model=name,plan=asdict(plan),status='PASS' if passed else 'FAIL',attempts=attempts))
            state=policy.read();state['qualification']=results
            if passed:
                state.update(selected=asdict(plan),qualification_passed=True,qualification_complete=True,stopped=False);state.pop('candidate',None);policy.write(state)
                (out/'qualification.json').write_text(json.dumps(dict(status='PASS',selected=asdict(plan),models=results),ensure_ascii=False,indent=2),encoding='utf-8')
                return True
            policy.recover()
            state=policy.read();state.pop('candidate',None);policy.write(state)
        state=policy.read();state.pop('selected',None);state.pop('candidate',None)
        state.update(qualification=results,qualification_complete=True,qualification_passed=False,stopped=True);policy.write(state)
        policy.recover()
        (out/'qualification.json').write_text(json.dumps(dict(status='BOTH_MODELS_UNQUALIFIED',models=results),ensure_ascii=False,indent=2),encoding='utf-8')
        return False
if __name__=='__main__':raise SystemExit(0 if qualify() else 1)
