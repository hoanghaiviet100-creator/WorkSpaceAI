from pathlib import Path
import json,httpx
ROOT=Path(__file__).resolve().parents[1]
def cache():
    path=ROOT/'.runtime/adaptive-model-metadata.json'
    rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    catalog=json.loads((ROOT/'model-catalog.json').read_text(encoding='utf-8'))['models']
    with httpx.Client(base_url='http://127.0.0.1:18684',trust_env=False,timeout=20) as client:
        for name in ('qwen3.5:9b-q4_K_M','qwen2.5:7b-q4_K_M'):
            if rows.get(name,{}).get('digest')==catalog[name]['digest']:continue
            response=client.post('/api/show',json=dict(model=name,verbose=True));response.raise_for_status();data=response.json();meta=data['model_info']
            tokens=meta.pop('tokenizer.ggml.tokens',[])
            if tokens:meta[meta['general.architecture']+'.vocab_size']=len(tokens)
            rows[name]=dict(model_info=meta,capabilities=data.get('capabilities',[]),details=data['details'],digest=catalog[name]['digest'])
    for row in rows.values():
        info=row['model_info'];arch=info['general.architecture']
        row['model_info']={k:v for k,v in info.items() if k=='general.architecture' or k.startswith(arch+'.')}
    path.write_text(json.dumps(rows,indent=2),encoding='utf-8')
if __name__=='__main__':cache()
