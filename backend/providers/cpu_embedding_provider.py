"""Pinned CPU embeddings with a bounded, independently cancellable worker."""
import atexit
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time

import numpy as np

from backend.providers.embedding_provider import EmbeddingError, validate_vectors


class CPUEmbeddingProvider:
    def __init__(self, manifest=None, timeout=120):
        self.path = Path(manifest or os.environ['F1_CPU_ENCODER'])
        self.timeout = timeout
        self.dimension = None
        self.is_available = False
        self.using_ollama = self.using_hash_fallback = False
        self._identity = None
        self._process = None
        self._lock = threading.RLock()
        self.metrics = {}
        atexit.register(self.close)

    def _verify_files(self):
        spec = json.loads(self.path.read_text(encoding='utf-8'))
        for name, expected in spec['versions'].items():
            if importlib.metadata.version(name) != expected:
                raise EmbeddingError('EMBEDDING_MODEL_CHANGED: runtime version differs from pinned encoder')
        for name, expected in spec['files'].items():
            path = (self.path.parent / name).resolve()
            if not path.is_relative_to(self.path.parent.resolve()) or not path.is_file():
                raise EmbeddingError('EMBEDDING_MODEL_MISSING: pinned encoder file missing')
            stat = path.stat()
            stamp = (stat.st_size, stat.st_mtime_ns)
            cached = getattr(self, '_file_stamps', {}).get(name)
            if cached != stamp:
                with path.open('rb') as handle:
                    actual = hashlib.file_digest(handle, 'sha256').hexdigest()
                if actual != expected:
                    raise EmbeddingError('EMBEDDING_MODEL_CHANGED: pinned encoder hash mismatch')
                if not hasattr(self, '_file_stamps'): self._file_stamps = {}
                self._file_stamps[name] = stamp
        if self._identity is not None and spec != self._identity:
            raise EmbeddingError('EMBEDDING_MODEL_CHANGED: encoder policy changed')
        self._identity = spec
        self.dimension = spec['dimension']

    def close(self):
        process = self._process
        self._process = None
        self.is_available = False
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)
            for stream in (process.stdin, process.stdout):
                if stream: stream.close()
        handle = getattr(self, '_stderr', None)
        if handle: handle.close()

    def _exchange(self, payload):
        from backend.services.f1_session_runtime import admit_embedding, monitor_reserves, resource_watch
        admit_embedding()
        started = time.perf_counter()
        try:
            with resource_watch(self.close):
                if self._process is None or self._process.poll() is not None:
                    self.close()
                    log = Path(os.getenv('F1_RUNTIME_DIR', self.path.parent)) / 'cpu-embedding.stderr.log'
                    log.parent.mkdir(parents=True, exist_ok=True)
                    self._stderr = log.open('a', encoding='utf-8')
                    self._process = subprocess.Popen(
                        [sys.executable, '-B', '-u', '-m', 'backend.providers.cpu_embedding_worker', str(self.path)],
                        cwd=Path(__file__).resolve().parents[2],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
                        text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                        env=dict(os.environ, HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false'))
                process = self._process
                replies = queue.Queue(maxsize=1)
                def read():
                    try: replies.put(process.stdout.readline())
                    except (OSError, ValueError): replies.put('')
                threading.Thread(target=read, daemon=True).start()
                process.stdin.write(json.dumps(payload, ensure_ascii=False) + '\n'); process.stdin.flush()
                remaining=min(self.timeout,max(0,getattr(self,'_deadline',time.monotonic()+self.timeout)-time.monotonic()))
                try: line = replies.get(timeout=remaining)
                except queue.Empty as exc:
                    raise EmbeddingError('EMBEDDING_TIMEOUT: CPU worker exceeded deadline') from exc
                if not line: raise EmbeddingError('EMBEDDING_PROVIDER_FAILURE: CPU worker stopped')
                reply = json.loads(line)
                if reply.get('error'): raise EmbeddingError(reply['error'])
                monitor_reserves()
            self.metrics = dict(reply.get('metrics', {}), elapsed_ms=round((time.perf_counter()-started)*1000,2))
            self.is_available = True
            return validate_vectors(reply['vectors'], len(payload['texts']), self.dimension)
        except BaseException:
            self.close()
            raise

    def load_model(self):
        with self._lock:
            self._verify_files()
            if not self.is_available: self._exchange(dict(texts=['embedding dimension probe'], purpose='document'))
        return True

    def verify_index(self, expected_index_id):
        with self._lock:
            self._verify_files()
            if self.index_id != expected_index_id:
                raise EmbeddingError('EMBEDDING_MODEL_CHANGED: vector namespace differs')

    @property
    def index_identity(self):
        with self._lock:
            self._verify_files()
            return json.loads(json.dumps(self._identity))

    @property
    def index_id(self):
        return 'cpu-onnx-v1:' + hashlib.sha256(json.dumps(self.index_identity, sort_keys=True).encode()).hexdigest()

    def _embed(self, texts, purpose):
        with self._lock:
            self._verify_files()
            if not texts: return np.empty((0,self.dimension),dtype=np.float32)
            if len(texts)>4096 or any(not isinstance(t,str) or not t.strip() or len(t)>100000 for t in texts):
                raise EmbeddingError('EMBEDDING_INVALID_INPUT: invalid or oversized batch')
            batches=[]
            self._deadline=time.monotonic()+self.timeout
            try:
                for text in texts:
                    batches.append(self._exchange(dict(texts=[text],purpose=purpose)))
                self._verify_files()
                return np.concatenate(batches)
            finally:
                self.__dict__.pop('_deadline',None)

    def embed_texts(self, texts): return self._embed(texts, 'document')
    def embed_queries(self, texts): return self._embed(texts, 'query')
    def get_embed_fn(self): return self.embed_texts
