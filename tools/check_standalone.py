"""Verify local dependencies and the unchanged pinned encoder contract."""
import hashlib,importlib,importlib.metadata,json,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def check():
    environment=(ROOT/'.venv-pa2').resolve();site=environment/'Lib/site-packages'
    modules={}
    for name in ('fastapi','uvicorn','pydantic','pypdf','rank_bm25','httpx','sqlalchemy','cryptography','numpy','fastembed','onnxruntime','tokenizers'):
        module=importlib.import_module(name);path=Path(module.__file__).resolve()
        if not path.is_relative_to(site):raise RuntimeError('Dependency is outside isolated environment: '+name)
        modules[name]=str(path)
    spec=json.loads((ROOT/'legal/CPU-ENCODER.json').read_text(encoding='utf-8'))
    for name,version in spec['versions'].items():
        if importlib.metadata.version(name)!=version:raise RuntimeError('Encoder runtime version changed: '+name)
    for path in sys.path:
        resolved=Path(path).resolve()
        if not resolved.is_relative_to(ROOT) and not resolved.is_relative_to(Path(sys.base_prefix)):
            raise RuntimeError('External dependency search path: '+str(resolved))
    identity='cpu-onnx-v1:'+hashlib.sha256(json.dumps(spec,sort_keys=True).encode()).hexdigest()
    return dict(standalone=True,environment=str(environment),base_python=sys.base_prefix,modules=modules,index_identity=identity)


if __name__=='__main__':print(json.dumps(check(),indent=2))
