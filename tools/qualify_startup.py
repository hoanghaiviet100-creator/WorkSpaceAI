"""Three individually recorded model-cold startup smoke trials; no retries."""
import argparse,datetime,json,os,shutil,subprocess,sys,threading,time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.resources import sample,Guard

MODEL='qwen2.5:7b-q4_K_M'
OLLAMA='http://127.0.0.1:18684'
APP='http://127.0.0.1:18682'

def run(trial,out):
    directory=out/f'cold-{trial}';directory.mkdir(parents=True,exist_ok=True)
    with (directory/'started.json').open('x',encoding='utf-8') as f:json.dump(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),trial=trial),f)
    client=httpx.Client(timeout=3,trust_env=False);stop=threading.Event();samples=[]
    def sample_loop():
        with (directory/'resources.jsonl').open('a',encoding='utf-8') as log:
            while not stop.is_set():
                try:
                    row=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**sample());samples.append(row);log.write(json.dumps(row)+'\n');log.flush()
                except Exception as exc:log.write(json.dumps(dict(error=str(exc)))+'\n')
                stop.wait(.5)
    watcher=threading.Thread(target=sample_loop,daemon=True);watcher.start()
    started=time.perf_counter();result=dict(trial=trial,model=MODEL,model_cold=True,machine_cold=False,os_cache='Not cleared or controlled',status='FAIL')
    pin_path=ROOT/'validation/release-qualification-20261127/final-candidate-source.json'
    if pin_path.exists():
        import hashlib
        pin=json.loads(pin_path.read_text())
        if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=value for name,value in pin['files'].items()):raise RuntimeError('Pinned candidate changed')
        result['candidate']=pin['candidate']
    try:
        result['baseline']=sample()
        daemon=time.perf_counter()
        try:response=client.get(OLLAMA+'/api/ps');response.raise_for_status()
        except httpx.HTTPError:
            command=['rtk','proxy','docker','compose','-p','workspaceai-f1-session-b','-f',str(ROOT/'compose.session-b.yml'),'-f',str(ROOT/'compose.models-readonly.yml'),'up','-d','--pull','never']
            p=subprocess.run(command,capture_output=True,text=True,timeout=45)
            (directory/'daemon-start.log').write_text(p.stdout+'\n'+p.stderr,encoding='utf-8')
            if p.returncode:raise RuntimeError('Owned Ollama daemon did not start')
            deadline=time.monotonic()+30
            while True:
                try:response=client.get(OLLAMA+'/api/ps');response.raise_for_status();break
                except httpx.HTTPError:
                    if time.monotonic()>deadline:raise
                    time.sleep(.5)
        result['daemon_readiness_ms']=round((time.perf_counter()-daemon)*1000,2)
        result['residency_before']=response.json()
        if any(m.get('name')==MODEL for m in response.json()['models']):raise RuntimeError('Generation was resident before trial; trial invalid')
        Guard(directory/'initial-admission.jsonl').admit('generation_load')
        launch=time.perf_counter()
        with (directory/'start.log').open('w',encoding='utf-8') as log:
            process=subprocess.Popen(['rtk','proxy','powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Start-SessionB.ps1'),'-Validation','-NoOpen'],stdout=log,stderr=subprocess.STDOUT,cwd=ROOT)
        deadline=time.monotonic()+60
        while True:
            try:response=client.get(APP+'/openapi.json');response.raise_for_status();break
            except httpx.HTTPError:
                if time.monotonic()>deadline:raise RuntimeError('Application startup deadline exceeded')
                time.sleep(.5)
        result['application_http_ready_ms']=round((time.perf_counter()-launch)*1000,2)
        print('APP_AVAILABLE',trial,APP,flush=True)
        deadline=time.monotonic()+245
        while True:
            state=client.get(APP+'/api/runtime/generation-ready').json()
            if state.get('ready'):break
            if not state.get('preparing'):raise RuntimeError('Preload failed: '+state.get('message',''))
            if time.monotonic()>deadline:raise RuntimeError('Startup readiness deadline exceeded')
            time.sleep(.5)
        result['startup_to_generation_ready_ms']=round((time.perf_counter()-launch)*1000,2)
        result['preload']=json.loads((ROOT/'.runtime-validation/generation-readiness.json').read_text(encoding='utf-8'))
        first=time.perf_counter()
        response=client.post(APP+'/api/chat',headers={'X-Workspace-ID':'f1-session-b-validation'},json=dict(query='Buổi tập huấn Sao Mai bắt đầu lúc mấy giờ?',selected_doc_ids=['vi-sao-mai.pdf'],verification_profile='academic_grounded'),timeout=95)
        result['first_post_preload_answer_ms']=round((time.perf_counter()-first)*1000,2)
        response.raise_for_status();answer=response.json();result['answer']=answer
        claims=answer.get('validated_claims',[])
        result['correct_with_citation']='09:10' in answer.get('answer','') and any(c['cited_doc_id']=='vi-sao-mai.pdf' and c['cited_page']==1 and '09:10' in c['evidence_quote'] for c in claims)
        result['residency_after']=client.get(OLLAMA+'/api/ps').json()
        result['status']='PASS' if result['correct_with_citation'] else 'FAIL'
    except Exception as exc:
        result['error']=type(exc).__name__+': '+str(exc)
    finally:
        result['startup_plus_first_answer_total_ms']=round((time.perf_counter()-started)*1000,2)
        stop.set();watcher.join(timeout=5)
        if samples:result['peaks']=dict(samples=len(samples),ram_used_bytes=max(r['physical_total']-r['physical_free'] for r in samples),commit_used_bytes=max(r['commit_limit']-r['commit_free'] for r in samples),vram_used_mib=16311-min(r['gpu_free_mib'] for r in samples),unsafe_samples=sum(r['physical_free']<Guard.RESERVE_PHYSICAL or r['commit_free']<Guard.RESERVE_COMMIT for r in samples))
        for name in ('generation-readiness.json','app.stderr.log','resource-admission.jsonl'):
            p=ROOT/'.runtime-validation'/name
            if p.exists():shutil.copyfile(p,directory/name)
        logs=subprocess.run(['rtk','proxy','docker','logs','workspaceai-f1-session-b-ollama-1'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        (directory/'ollama.log').write_text(logs.stdout+'\n'+logs.stderr,encoding='utf-8')
        if trial<3:
            stopped=subprocess.run(['rtk','proxy','powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Stop-SessionB.ps1'),'-Validation'],capture_output=True,text=True)
            try:
                unloaded=client.post(OLLAMA+'/api/generate',json=dict(model=MODEL,keep_alive=0),timeout=15);unloaded.raise_for_status()
                deadline=time.monotonic()+20
                while True:
                    remaining=client.get(OLLAMA+'/api/ps').json()
                    if not any(m.get('name')==MODEL for m in remaining['models']):break
                    if time.monotonic()>deadline:raise RuntimeError('Configured model did not unload')
                    time.sleep(.5)
                result['cleanup_residency']=remaining
            except Exception as exc:result['cleanup_error']=str(exc)
        (directory/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in ('answer','preload')},ensure_ascii=False,indent=2),flush=True)
    return result


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace')
    parser=argparse.ArgumentParser();parser.add_argument('--trial',type=int,choices=[1,2,3],required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    result=run(args.trial,Path(args.output));raise SystemExit(0 if result['status']=='PASS' and not result.get('peaks',{}).get('unsafe_samples') else 1)
