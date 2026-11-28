"""Offline release regressions and frontend checks; no model campaign."""
import argparse,datetime,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def check(out):
    out.mkdir(parents=True,exist_ok=True)
    backend=['test_generation_readiness','test_cpu_embeddings','test_f1_session_b','test_f1_adaptive_memory','test_f1_final_completion','test_embedding_provider','test_embedding_digest_integrity','test_embedding_concurrency','test_startup_embedding_isolation','test_feature1_grounded_qa','test_r2_r7_pipeline','test_feature3_email_backend','test_feature3_email_reporting','test_f2_study_schemas','test_f2_study_validation','test_f2_source_service']
    node=Path(os.getenv('WORKSPACEAI_NODE',r'D:\WorkspaceAI-F1-Toolchain\node-v22.23.5-win-x64\node.exe'))
    jobs=[('backend',[sys.executable,'-B','tools/offline_pytest.py','-q',*[f'tests/{name}.py' for name in backend],'-p','no:cacheprovider','--basetemp',str(out/'pytest'),'--junitxml',str(out/'backend.xml')],ROOT),('typescript',[str(node),'node_modules/typescript/bin/tsc','-b'],ROOT/'frontend'),('production-build',[str(node),'node_modules/vite/bin/vite.js','build'],ROOT/'frontend'),('frontend-contracts',[str(node),'--test','tests/schema-contracts.test.mjs'],ROOT/'frontend')]
    env=dict(os.environ,F1_GENERATION_PRELOAD='false',F1_EMBEDDING_BACKEND='ollama',PYTHON_DOTENV_DISABLED='1',PYTHONDONTWRITEBYTECODE='1')
    results=[]
    for name,args,cwd in jobs:
        started=time.perf_counter();process=subprocess.run(['rtk','proxy',*args],cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace')
        (out/(name+'.log')).write_text(process.stdout+'\n'+process.stderr,encoding='utf-8')
        results.append(dict(name=name,exit_code=process.returncode,seconds=round(time.perf_counter()-started,2)))
        print(json.dumps(results[-1]),flush=True)
    (out/'checks.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    return all(r['exit_code']==0 for r in results)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    raise SystemExit(0 if check(Path(args.output) if args.output else ROOT/'validation'/('checks-'+stamp)) else 1)
