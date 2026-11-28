"""Fetch the approved encoder revision and verify every artifact hash."""
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def prepare():
    os.environ['HF_HUB_DISABLE_XET']='1'
    os.environ['HF_HOME']=str(ROOT/'.runtime/huggingface')
    from huggingface_hub import snapshot_download
    spec=json.loads((ROOT/'legal/CPU-ENCODER.json').read_text(encoding='utf-8'))
    destination=ROOT/'.runtime/cpu-embedding/qwen3-0.6b-int8'
    snapshot_download(spec['repo'],revision=spec['revision'],local_dir=destination,allow_patterns=list(spec['files']))
    for name,expected in spec['files'].items():
        with (destination/name).open('rb') as handle:
            if hashlib.file_digest(handle,'sha256').hexdigest()!=expected:
                raise ValueError('Pinned encoder hash mismatch: '+name)
    (destination/'encoder.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    print(destination/'encoder.json')

if __name__=='__main__':prepare()
