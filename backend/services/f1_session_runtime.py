"""Single-user inference admission with protected system memory reserves."""
import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
import httpx
from tools.resources import Guard, AdmissionDenied, host_memory, GIB
from backend.core.config import settings

runtime_lock = threading.Lock()
guard = Guard(Path(os.getenv('F1_RUNTIME_DIR', 'runtime')) / 'resource-admission.jsonl')

def enabled():
    return os.getenv('F1_SESSION_B', 'false').lower() == 'true'

@contextmanager
def inference_slot():
    if not runtime_lock.acquire(blocking=False):
        raise AdmissionDenied('BUSY: another upload or question is running; wait for it to finish.')
    try:
        yield
    finally:
        runtime_lock.release()

def monitor_reserves(trace=None):
    if enabled():
        m = trace.capture() if trace is not None else host_memory()
        if m['physical_free'] < guard.RESERVE_PHYSICAL or m['commit_free'] < guard.RESERVE_COMMIT:
            raise AdmissionDenied('RESOURCE_RESERVE_VIOLATION:'+('physical_free' if m['physical_free'] < guard.RESERVE_PHYSICAL else 'commit_free'))

def admit_embedding():
    if enabled():
        guard.admit('nli_load') # Existing 6 GiB physical / 10 GiB commit admission.

def admit_generation():
    if not enabled():
        return
    try:
        response = httpx.get(settings.ollama_base_url + '/api/ps', timeout=3, trust_env=False)
        response.raise_for_status()
        loaded = any(m.get('name') == settings.f1_generation_model for m in response.json().get('models', []))
    except (httpx.HTTPError, ValueError):
        loaded = False
    guard.admit('generation_request' if loaded else 'generation_load')


@contextmanager
def resource_watch(cancel, trace=None):
    """Monitor during cold load as well as between streamed output chunks."""
    if not enabled():
        yield
        return
    stop=threading.Event(); failure=[]
    def watch():
        while not stop.wait(0.5):
            try:
                monitor_reserves() if trace is None else monitor_reserves(trace)
            except AdmissionDenied as exc:
                failure.append(exc)
                cancel()
                return
    worker=threading.Thread(target=watch,name='inference-reserves',daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set(); worker.join(timeout=1)
        if failure:
            raise failure[0]

def admission_message(exc):
    text=str(exc)
    if 'BUSY' in text or 'IN_FLIGHT' in text:
        return 'BUSY: Another upload or question is running. Wait for it to finish.'
    if 'commit_free' in text:
        return 'RESOURCE_LIMIT: Available Windows commit memory is below the local-inference reserve.'
    if 'physical_free' in text:
        return 'RESOURCE_LIMIT: Available system RAM is below the local-inference reserve.'
    if 'gpu_free_mib' in text:
        return 'RESOURCE_LIMIT: Available GPU memory is below the local-inference reserve.'
    return 'RESOURCE_LIMIT: Inference stopped to preserve system memory reserves. Free memory before retrying.'


class ResourceTrace:
    """Sampled host peaks, not attribution to a single process."""
    def __init__(self):
        import uuid
        self.request_id=uuid.uuid4().hex
        self.started=time.perf_counter();self.readings=[];self.lock=threading.Lock()
        self.gpu_total_mib=gpu_total_mib()
        self.capture()
    def capture(self):
        readings=guard.probe()
        readings['elapsed_ms']=round((time.perf_counter()-self.started)*1000,2)
        with self.lock:self.readings.append(readings)
        return readings
    def summary(self):
        with self.lock: rows=list(self.readings)
        first=rows[0]
        ram=min(r['physical_free'] for r in rows);commit=min(r['commit_free'] for r in rows);gpu=min(r['gpu_free_mib'] for r in rows)
        return dict(request_id=self.request_id,samples=len(rows),sample_period_target_ms=500,baseline=first,
            physical_free_min_bytes=ram,commit_free_min_bytes=commit,gpu_free_min_mib=gpu,
            gpu_total_mib=self.gpu_total_mib,gpu_used_peak_mib=self.gpu_total_mib-gpu,
            system_ram_used_peak_bytes=first['physical_total']-ram,system_commit_used_peak_bytes=first['commit_limit']-commit,
            ram_increase_bytes=max(0,first['physical_free']-ram),commit_increase_bytes=max(0,first['commit_free']-commit),
            vram_increase_bytes=max(0,int((first['gpu_free_mib']-gpu)*1024**2)),elapsed_ms=round((time.perf_counter()-self.started)*1000,2),
            attribution='Sampled whole-host changes include background activity; peaks between samples may be missed.')


from functools import lru_cache
@lru_cache(maxsize=1)
def gpu_total_mib():
    import subprocess
    result=subprocess.run(['rtk','proxy','nvidia-smi','--query-gpu=memory.total','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
    if result.returncode:raise AdmissionDenied('GPU_SAMPLE_UNAVAILABLE')
    return float(result.stdout.strip())


generation_load_lock=threading.Lock()

@contextmanager
def generation_load_slot():
    if not generation_load_lock.acquire(blocking=False):
        raise AdmissionDenied('BUSY: model preparation is already running')
    handle=None
    try:
        if enabled() and os.name=='nt':
            import msvcrt
            path=Path(__file__).resolve().parents[2]/'.runtime/generation-load.lock'
            path.parent.mkdir(parents=True,exist_ok=True)
            handle=path.open('a+b')
            if handle.tell()==0:handle.write(b'0');handle.flush()
            handle.seek(0)
            try:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:
                handle.close();handle=None
                raise AdmissionDenied('BUSY: model preparation is already running') from exc
        yield
    finally:
        if handle:
            import msvcrt
            handle.seek(0);msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1);handle.close()
        generation_load_lock.release()
