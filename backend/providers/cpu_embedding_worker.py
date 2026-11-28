"""Offline FastEmbed worker. Only CPUExecutionProvider may execute the graph."""
import json
from pathlib import Path
import sys
import time
import numpy as np
from fastembed import TextEmbedding
from backend.vendor.surfsense.embedding_pooling import pool, Pooling


def main():
    sys.stdin.reconfigure(encoding='utf-8',errors='strict')
    sys.stdout.reconfigure(encoding='utf-8',errors='strict')
    sys.stderr.reconfigure(encoding='utf-8',errors='backslashreplace')
    path=Path(sys.argv[1]); spec=json.loads(path.read_text(encoding='utf-8'))
    started=time.perf_counter()
    encoder=TextEmbedding(model_name=spec['model'],specific_model_path=str(path.parent),
        cache_dir=str(path.parent/'.cache'),providers=['CPUExecutionProvider'],threads=spec['threads'],local_files_only=True)
    engine=encoder.model
    if engine.model.get_providers()!=['CPUExecutionProvider']:
        raise RuntimeError('Unexpected execution provider')
    tokenizer=engine.tokenizer
    # Reject overlong inputs before inference; no silent truncation or vector loss.
    tokenizer.no_truncation()
    loaded_ms=round((time.perf_counter()-started)*1000,2)
    for line in sys.stdin:
        try:
            request=json.loads(line)
            prefix=spec['query_prefix'] if request['purpose']=='query' else spec['document_prefix']
            texts=[prefix+t for t in request['texts']]
            lengths=[sum(e.attention_mask) for e in tokenizer.encode_batch(texts)]
            if any(n>spec['max_tokens'] for n in lengths):
                raise ValueError('EMBEDDING_INVALID_INPUT: text exceeds pinned token budget; split the document')
            started=time.perf_counter()
            # FastEmbed performs tokenization and graph inference. Reuse the pinned
            # pooling function so the configured last-token policy is explicit.
            output=engine.onnx_embed(texts)
            vectors=pool(Pooling.LAST,output.model_output,output.attention_mask)
            vectors=vectors/np.linalg.norm(vectors,axis=1,keepdims=True)
            print(json.dumps(dict(vectors=vectors.astype(np.float32).tolist(),metrics=dict(
                providers=engine.model.get_providers(),tokens=lengths,batch_size=len(texts),threads=spec['threads'],
                load_ms=loaded_ms,inference_ms=round((time.perf_counter()-started)*1000,2)))),flush=True)
            loaded_ms=0
        except Exception as exc:
            import traceback
            traceback.print_exc(file=sys.stderr)
            code=str(exc) if str(exc).startswith('EMBEDDING_') else 'EMBEDDING_PROVIDER_FAILURE: CPU inference failed'
            print(json.dumps(dict(error=code)),flush=True)


if __name__=='__main__': main()
