import json
import threading
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from backend.providers.llm_provider import GenerationError
from backend.services.generation_readiness import GenerationReadiness,message


def test_preparing_and_failure_are_natural_language():
    state=GenerationReadiness()
    assert state.public(True)['message']=='Đang chuẩn bị mô hình AI. Bạn có thể tải tài liệu lên trong lúc chờ.'
    assert state.public(False)['preparing']
    assert 'time' in message('MODEL_LOAD_TIMEOUT').lower()
    assert 'RESOURCE_LIMIT' not in message('RESOURCE_LIMIT',True)


def test_start_does_not_launch_duplicate_preloads(monkeypatch):
    state=GenerationReadiness();arrived=threading.Event();release=threading.Event();calls=[]
    def prepare():calls.append(1);arrived.set();release.wait(2)
    monkeypatch.setattr(state,'prepare',prepare)
    state.start();assert arrived.wait(1);state.start();release.set();state.worker.join(2)
    state.start();assert len(calls)==1


def test_request_does_not_load_until_ready(tmp_path,monkeypatch):
    monkeypatch.setenv('F1_GENERATION_PRELOAD','true');monkeypatch.setenv('F1_RUNTIME_DIR',str(tmp_path))
    state=GenerationReadiness()
    with pytest.raises(GenerationError,match='PREPARING'):state.require_ready()
    state.record(state='failed',ready=False,code='MODEL_LOAD_TIMEOUT')
    with pytest.raises(GenerationError,match='MODEL_LOAD_TIMEOUT'):state.require_ready()
    assert not state.attempted


def test_lost_residency_requires_explicit_recovery(tmp_path,monkeypatch):
    from backend.services.f1_adaptive_memory import policy
    monkeypatch.setenv('F1_GENERATION_PRELOAD','true');monkeypatch.setenv('F1_RUNTIME_DIR',str(tmp_path))
    state=GenerationReadiness();state.record(state='ready',code='GENERATION_READY',ready=True)
    monkeypatch.setattr(policy,'residency',lambda:[])
    with pytest.raises(GenerationError,match='RESIDENCY_LOST'):state.require_ready()
    assert not state.public()['ready'] and not state.attempted


def test_preload_failure_cancels_and_records_cleanup(tmp_path,monkeypatch):
    import time
    from backend.services import f1_session_runtime as runtime
    from backend.services.f1_adaptive_memory import policy
    from backend.services import generation_readiness as module
    monkeypatch.setenv('F1_RUNTIME_DIR',str(tmp_path));monkeypatch.setenv('F1_MODEL_DIGEST','pinned')
    monkeypatch.setattr(module.settings,'f1_generation_model','configured')
    monkeypatch.setattr(module.httpx,'get',lambda *a,**kw:SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'models':[dict(name='configured',digest='pinned')]}))
    monkeypatch.setattr(policy,'select',lambda *a:SimpleNamespace(model='configured',digest='pinned',num_ctx=4096))
    def fail_load(*a,on_load=None):
        if on_load:on_load()
        raise RuntimeError('MODEL_RESIDENCY_LOAD_FAILED')
    monkeypatch.setattr(policy,'activate',fail_load)
    monkeypatch.setattr(policy,'residency',lambda:[])
    monkeypatch.setattr(runtime,'resource_watch',lambda *a:nullcontext())
    monkeypatch.setattr(runtime,'ResourceTrace',lambda:SimpleNamespace(summary=lambda:{},capture=lambda:None))
    state=GenerationReadiness();state.started=time.perf_counter();cancelled=[]
    monkeypatch.setattr(state,'cancel',lambda:cancelled.append(1))
    state.prepare()
    assert state.state['code']=='MODEL_LOAD_TIMEOUT' and state.state['cleanup_confirmed']
    assert cancelled==[1] and not state.state['ready']


def test_generation_load_mutex_rejects_duplicate():
    from backend.services.f1_session_runtime import generation_load_slot
    from tools.resources import AdmissionDenied
    with generation_load_slot():
        with pytest.raises(AdmissionDenied,match='BUSY'):
            with generation_load_slot():pass


def test_load_deadline_is_separate_from_warm_generation():
    import inspect
    from backend.vendor.surfsense.ollama_residency import RouterClient
    from backend.providers.f1_basic_provider import BasicProvider
    assert 'Timeout(180' in inspect.getsource(RouterClient.load)
    assert 'Timeout(90' in inspect.getsource(BasicProvider.__init__)


def test_cancellation_before_owned_load_does_not_unload_another_app(monkeypatch):
    import backend.services.generation_readiness as module
    state=GenerationReadiness()
    monkeypatch.setattr(module.httpx,'post',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No owned load to cancel')))
    state.cancel()
    assert state.stop_event.is_set()


def test_transport_load_cancellation_is_observed():
    import asyncio,httpx
    from backend.vendor.surfsense import ollama_residency as module
    async def check():
        entered=asyncio.Event()
        async def delayed(request):
            entered.set();await asyncio.Event().wait()
        task=asyncio.create_task(module.RouterClient('http://test',httpx.MockTransport(delayed)).load('configured'))
        await asyncio.wait_for(entered.wait(),1)
        module.abort_active_load()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(check())


def test_idle_reserve_watch_releases_only_configured_model_and_stops(tmp_path,monkeypatch):
    from backend.services.f1_session_runtime import guard
    from tools.resources import GIB
    monkeypatch.setenv('F1_RUNTIME_DIR',str(tmp_path))
    state=GenerationReadiness();state.state.update(state='ready',code='GENERATION_READY',ready=True)
    waits=iter([False,True]);monkeypatch.setattr(state.stop_event,'wait',lambda *a:next(waits))
    monkeypatch.setattr(guard,'probe',lambda:dict(physical_free=3*GIB,commit_free=20*GIB,gpu_free_mib=12000))
    cancelled=[];monkeypatch.setattr(state,'cancel',lambda force=False:cancelled.append(force))
    state.watch_idle()
    assert cancelled==[True] and state.state['code']=='RESOURCE_LIMIT' and not state.state['ready']


def test_idle_residency_loss_never_reloads(tmp_path,monkeypatch):
    from backend.services.f1_session_runtime import guard
    from backend.services.f1_adaptive_memory import policy
    from tools.resources import GIB
    monkeypatch.setenv('F1_RUNTIME_DIR',str(tmp_path))
    state=GenerationReadiness();state.state.update(state='ready',code='GENERATION_READY',ready=True)
    waits=iter([False,True]);monkeypatch.setattr(state.stop_event,'wait',lambda *a:next(waits))
    monkeypatch.setattr(guard,'probe',lambda:dict(physical_free=12*GIB,commit_free=20*GIB,gpu_free_mib=12000))
    monkeypatch.setattr(policy,'residency',lambda:[])
    monkeypatch.setattr(policy,'activate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('No automatic reload')))
    state.watch_idle()
    assert state.state['code']=='GENERATION_RESIDENCY_LOST' and not state.state['ready']
