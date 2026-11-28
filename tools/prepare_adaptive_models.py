"""Reuse only approved model manifests and immutable read-only blob mounts."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[1]
PRIMARY=Path(r'D:\WorkspaceAI-M4-F1-LAT-01\m4-v3-20261125\ollama-state\models')
FALLBACK=Path(r'D:\WorkSpaceAI-Models\ollama\models')
SPECS=[('qwen3.5:9b-q4_K_M',PRIMARY,'qwen3.5/9b-q4_K_M','Q4_K_M'),('qwen3-embedding:0.6b',PRIMARY,'qwen3-embedding/0.6b','Q8_0'),('qwen2.5:7b-q4_K_M',FALLBACK,'qwen2.5/7b','Q4_K_M')]
def prepare():
    model_dir=ROOT/'.runtime/adaptive-models';(model_dir/'blobs').mkdir(parents=True,exist_ok=True)
    entries={};mounts={}
    for tag,source,relative,quant in SPECS:
        manifest=source/'manifests/registry.ollama.ai/library'/relative
        data=json.loads(manifest.read_text(encoding='utf-8'))
        config_path=source/'blobs'/data['config']['digest'].replace(':','-')
        config=json.loads(config_path.read_text(encoding='utf-8'))
        if config.get('file_type')!=quant: raise RuntimeError('Unexpected installed model quantization: '+tag)
        weights=next(layer for layer in data['layers'] if layer['mediaType']=='application/vnd.ollama.image.model')
        destination=model_dir/'manifests/registry.ollama.ai/library'/tag.replace(':','/')
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(manifest,destination)
        for layer in [data['config'],*data['layers']]:
            blob=layer['digest'].replace(':','-');path=source/'blobs'/blob
            if not path.is_file() or path.stat().st_size!=layer['size']: raise RuntimeError('Installed model blob missing or truncated: '+tag)
            mounts[blob]=dict(source=str(path).replace('\\','/'),target='/models/blobs/'+blob)
        entries[tag]=dict(name=tag,digest=hashlib.sha256(manifest.read_bytes()).hexdigest(),weights_bytes=weights['size'],quantization=quant,source_manifest=str(manifest))
    lines=['services:','  ollama:','    volumes:']
    for blob,mount in sorted(mounts.items()):
        lines.extend(['      - type: bind','        source: '+mount['source'],'        target: '+mount['target'],'        read_only: true'])
    (ROOT/'compose.models-readonly.yml').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ROOT/'model-catalog.json').write_text(json.dumps(dict(models=entries,weights_reused_read_only=True,downloaded_models=[]),indent=2),encoding='utf-8')
    return entries
if __name__=='__main__':
    print(json.dumps(prepare(),indent=2))
