"""One guarded startup preload, with observable readiness and explicit recovery."""
import json
import os
from pathlib import Path
import threading
import time
import httpx
from backend.core.config import settings
from backend.providers.llm_provider import GenerationError

PREPARING_VI='Đang chuẩn bị mô hình AI. Bạn có thể tải tài liệu lên trong lúc chờ.'
PREPARING_EN='The AI model is getting ready. You can upload documents while you wait.'


def enabled():
    return os.getenv('F1_GENERATION_PRELOAD','false').lower()=='true'


def message(code, vi=False):
    if code=='GENERATION_PREPARING': return PREPARING_VI if vi else PREPARING_EN
    if code=='GENERATION_READY': return ''
    if 'RESOURCE' in code or 'SAFE_APPROVED' in code:
        return ('Máy chưa đủ bộ nhớ để chuẩn bị mô hình. Hãy giải phóng bộ nhớ rồi khởi động lại ứng dụng.' if vi else
                'There is not enough available memory to prepare the model. Free memory, then restart the app.')
    if 'TIMEOUT' in code or 'LOAD_FAILED' in code:
        return ('Mô hình chưa tải xong trong thời gian cho phép. Hãy kiểm tra dịch vụ AI cục bộ rồi khởi động lại ứng dụng.' if vi else
                'The model did not finish loading in time. Check the local AI service, then restart the app.')
    if 'MISSING' in code or 'INVALID_CONFIG' in code:
        return ('Không tìm thấy đúng mô hình đã cấu hình. Hãy kiểm tra các tệp mô hình cục bộ rồi khởi động lại ứng dụng.' if vi else
                'The configured model could not be verified. Check the local model files, then restart the app.')
    return ('Dịch vụ AI cục bộ chưa sẵn sàng. Hãy kiểm tra dịch vụ và khởi động lại ứng dụng.' if vi else
            'The local AI service is unavailable. Check the service and restart the app.')


class GenerationReadiness:
    def __init__(self):
        self.lock=threading.RLock();self.stop_event=threading.Event()
        self.worker=None;self.attempted=False;self.owns_load=False;self.residency_watch=None
        self.state=dict(state='preparing',phase='startup',code='GENERATION_PREPARING',ready=False)

    def record(self, **values):
        with self.lock:
            self.state.update(values)
            path=Path(os.getenv('F1_RUNTIME_DIR','runtime'))/'generation-readiness.json'
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps(self.state,indent=2),encoding='utf-8');temporary.replace(path)

    def start(self):
        with self.lock:
            if self.attempted:return
            self.attempted=True;self.started=time.perf_counter()
            self.worker=threading.Thread(target=self.prepare,name='generation-preload',daemon=True)
            self.worker.start()

    def cancel(self,force=False):
        self.stop_event.set()
        if not (self.owns_load or force):return
        from backend.vendor.surfsense.ollama_residency import abort_active_load
        abort_active_load()
        try:
            response=httpx.post(settings.ollama_base_url+'/api/generate',json=dict(model=settings.f1_generation_model,keep_alive=0),timeout=5,trust_env=False)
            response.raise_for_status()
        except httpx.HTTPError:pass

    def prepare(self):
        from backend.services.f1_adaptive_memory import policy
        from backend.services.f1_session_runtime import ResourceTrace,resource_watch
        trace=None;timer=threading.Timer(240,self.expire);timer.daemon=True;timer.start()
        try:
            self.record(state='preparing',phase='admission',code='GENERATION_PREPARING',ready=False,model=settings.f1_generation_model,attempts=1)
            trace=ResourceTrace()
            with resource_watch(self.cancel,trace):
                self.record(phase='ollama_readiness')
                deadline=time.monotonic()+30
                while True:
                    if self.stop_event.is_set():raise GenerationError('GENERATION_CANCELLED')
                    try:
                        response=httpx.get(settings.ollama_base_url+'/api/tags',timeout=3,trust_env=False);response.raise_for_status()
                        tag=next((m for m in response.json()['models'] if m['name']==settings.f1_generation_model),None)
                        if not tag:raise GenerationError('GENERATION_MODEL_MISSING')
                        if tag['digest']!=os.environ['F1_MODEL_DIGEST']:raise GenerationError('GENERATION_INVALID_CONFIG')
                        break
                    except httpx.HTTPError:
                        if time.monotonic()>=deadline:raise GenerationError('GENERATION_UNAVAILABLE')
                        self.stop_event.wait(.5)
                plan=policy.select(4096)
                self.record(phase='model_loading',admission_elapsed_ms=round((time.perf_counter()-self.started)*1000,2),context=plan.num_ctx)
                if self.stop_event.is_set():raise GenerationError('GENERATION_CANCELLED')
                load_ms=policy.activate(plan,on_load=lambda:setattr(self,'owns_load',True))
                rows=policy.residency()
                resident=next((m for m in rows if m.get('name')==plan.model and m.get('digest')==plan.digest and m.get('context_length')==plan.num_ctx and m.get('size_vram',0)>0),None)
                if not resident:raise GenerationError('GENERATION_RESIDENCY_LOST')
                if self.stop_event.is_set():raise GenerationError('GENERATION_CANCELLED')
                trace.capture()
                measured=trace.summary()
                policy.observe(plan,measured,load_ms>0,True)
                self.record(state='ready',phase='ready',code='GENERATION_READY',ready=True,preload_ms=load_ms,
                    elapsed_ms=round((time.perf_counter()-self.started)*1000,2),resident=resident,resources=measured)
        except BaseException as exc:
            reason=str(exc)
            code=('RESOURCE_LIMIT' if any(t in reason for t in ('RESOURCE_','NO_SAFE_APPROVED')) else
                  'MODEL_LOAD_TIMEOUT' if 'RESIDENCY_LOAD_FAILED' in reason else
                  reason if reason.startswith('GENERATION_') else 'GENERATION_UNAVAILABLE')
            self.cancel()
            try:
                remaining=policy.residency()
                cleanup=not any(m.get('name')==settings.f1_generation_model for m in remaining)
            except Exception:cleanup=False
            self.record(state='failed',phase='failed',code=code,ready=False,cleanup_required=self.owns_load,cleanup_confirmed=cleanup if self.owns_load else None,
                elapsed_ms=round((time.perf_counter()-self.started)*1000,2),resources=trace.summary() if trace else None)
        finally:timer.cancel()
        if self.state['ready']:
            self.residency_watch=threading.Thread(target=self.watch_idle,name='generation-residency',daemon=True)
            self.residency_watch.start()

    def watch_idle(self):
        from backend.services.f1_session_runtime import guard
        from backend.services.f1_adaptive_memory import policy
        while not self.stop_event.wait(2):
            try:
                readings=guard.probe()
                if (readings['physical_free']<guard.RESERVE_PHYSICAL or readings['commit_free']<guard.RESERVE_COMMIT
                        or readings['gpu_free_mib']<guard.BUDGETS['generation_request'][2]):
                    self.cancel(force=True)
                    self.record(state='failed',phase='idle_reserve',code='RESOURCE_LIMIT',ready=False,readings=readings)
                    return
                if not any(m.get('name')==settings.f1_generation_model and m.get('size_vram',0)>0 for m in policy.residency()):
                    self.record(state='failed',phase='residency_lost',code='GENERATION_RESIDENCY_LOST',ready=False)
                    return
            except Exception:
                self.record(state='failed',phase='residency_lost',code='GENERATION_RESIDENCY_LOST',ready=False)
                return

    def expire(self):
        self.stop_event.set();self.cancel()
        self.record(state='failed',phase='failed',code='MODEL_LOAD_TIMEOUT',ready=False)

    def public(self, vi=False):
        with self.lock:state=dict(self.state)
        return dict(ready=state['ready'],preparing=state['state']=='preparing',message=message(state['code'],vi))

    def require_ready(self):
        if not enabled():return
        with self.lock:state=dict(self.state)
        if not state['ready']:raise GenerationError(state['code'])
        from backend.services.f1_adaptive_memory import policy
        try:
            resident=any(m.get('name')==settings.f1_generation_model and m.get('digest')==os.environ['F1_MODEL_DIGEST'] and m.get('size_vram',0)>0 for m in policy.residency())
        except httpx.HTTPError:resident=False
        if not resident:
            self.record(state='failed',phase='failed',code='GENERATION_RESIDENCY_LOST',ready=False)
            raise GenerationError('GENERATION_RESIDENCY_LOST')

    def close(self):
        self.stop_event.set()
        if self.worker and self.worker.is_alive():
            self.cancel();self.worker.join(timeout=7)
        if self.residency_watch:self.residency_watch.join(timeout=7)


readiness=GenerationReadiness()
