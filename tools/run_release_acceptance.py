"""One complete acceptance campaign against a frozen, ready local candidate."""
import argparse,datetime,hashlib,json,os,shutil,subprocess,sys,threading,time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.resources import sample,Guard
from tools.validate_session_b import actual

def run(out):
    out.mkdir(parents=True,exist_ok=True)
    with (out/'started.json').open('x',encoding='utf-8') as f:json.dump(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),campaigns=1,retries=0),f)
    pin=json.loads((ROOT/'validation/release-qualification-20261127/final-candidate-source.json').read_text())
    if any(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest for name,digest in pin['files'].items()):raise RuntimeError('Frozen candidate changed')
    ready=httpx.get('http://127.0.0.1:18682/api/runtime/generation-ready',timeout=5,trust_env=False);ready.raise_for_status()
    if not ready.json()['ready']:raise RuntimeError('Generation not ready; no case started')
    os.environ.pop('F1_ACCEPTANCE_CONTINUE',None)
    stopped=threading.Event();samples=[];residency=[]
    def watch():
        last=0
        with (out/'resources.jsonl').open('a',encoding='utf-8') as log:
            while not stopped.is_set():
                try:
                    row=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),**sample());samples.append(row);log.write(json.dumps(row)+'\n');log.flush()
                    if time.monotonic()-last>3:
                        response=httpx.get('http://127.0.0.1:18684/api/ps',timeout=3,trust_env=False);response.raise_for_status();residency.append(dict(utc=row['utc'],**response.json()));last=time.monotonic()
                except Exception as exc:log.write(json.dumps(dict(error=str(exc)))+'\n');log.flush()
                stopped.wait(.5)
    watcher=threading.Thread(target=watch,daemon=True);watcher.start()
    try:
        result=actual(out)
        (out/'candidate.json').write_text(json.dumps(dict(candidate=pin['candidate']),indent=2))
        return result
    except Exception as exc:
        (out/'execution-error.json').write_text(json.dumps(dict(type=type(exc).__name__,message=str(exc)),indent=2),encoding='utf-8')
        raise
    finally:
        stopped.set();watcher.join(timeout=5)
        (out/'residency.json').write_text(json.dumps(residency,indent=2),encoding='utf-8')
        if samples:
            peaks=dict(samples=len(samples),ram_used_peak_bytes=max(r['physical_total']-r['physical_free'] for r in samples),commit_used_peak_bytes=max(r['commit_limit']-r['commit_free'] for r in samples),vram_used_peak_mib=16311-min(r['gpu_free_mib'] for r in samples),reserve_violations=sum(r['physical_free']<Guard.RESERVE_PHYSICAL or r['commit_free']<Guard.RESERVE_COMMIT for r in samples),attribution='Whole-host sampled values, including background activity; sub-sample peaks may be missed.')
            (out/'peaks.json').write_text(json.dumps(peaks,indent=2),encoding='utf-8')
        for name in ('generation-readiness.json','app.stderr.log','resource-admission.jsonl'):
            path=ROOT/'.runtime-validation'/name
            if path.exists():shutil.copyfile(path,out/name)
        logs=subprocess.run(['rtk','proxy','docker','logs','workspaceai-f1-session-b-ollama-1'],capture_output=True,text=True,encoding='utf-8',errors='replace')
        (out/'ollama.log').write_text(logs.stdout+'\n'+logs.stderr,encoding='utf-8')


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8',errors='backslashreplace')
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args();run(Path(args.output))
