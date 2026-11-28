"""Offline lifecycle tests; these do not claim real model inference evidence."""
import asyncio
import threading
from types import SimpleNamespace

import pytest

from backend.providers.f1_claim_support_provider import (
    QualifiedLocalNLI, ScriptedSemanticVerifier,
)


def test_warmup_and_claim_share_bounded_worker_without_changing_claim_deadline(monkeypatch):
    adapter = QualifiedLocalNLI(model_path='unused', timeout_seconds=0.03)
    calls = []
    def infer(request):
        calls.append((threading.get_ident(), request))
        return ScriptedSemanticVerifier().verify(request)
    monkeypatch.setattr(adapter, '_infer', infer)
    try:
        adapter.warmup()
        adapter.verify(calls[0][1])
        assert len(calls) == 2 and calls[0][0] == calls[1][0]
        assert adapter.timeout_seconds == 0.03
    finally:
        adapter._worker.shutdown(wait=True)


def test_warmup_timeout_cannot_queue_another_claim(monkeypatch):
    adapter = QualifiedLocalNLI(model_path='unused', timeout_seconds=0.01)
    release = threading.Event()
    calls = []
    def infer(request):
        calls.append(request)
        release.wait(2)
        return ScriptedSemanticVerifier().verify(request)
    monkeypatch.setattr(adapter, '_infer', infer)
    try:
        # Exercise the same execution path with a short test-only deadline.
        from backend.providers.f1_claim_support_provider import SemanticRequest, SemanticItem
        from backend.algorithms.f1_claim_support import Evidence, fingerprint
        text = 'Permit P has been approved.'
        e = Evidence('ctx','e','d','v',fingerprint(text),1,1,1,text,fingerprint(text))
        request = SemanticRequest('ctx',(SemanticItem('c',text,('e',)),),(e,))
        with pytest.raises(TimeoutError): adapter._execute(request, 0.01)
        with pytest.raises(TimeoutError, match='VERIFIER_BUSY'): adapter.verify(request)
        assert len(calls) == 1
    finally:
        release.set()
        adapter._worker.shutdown(wait=True)


def test_missing_warmup_artifact_fails_closed():
    adapter = QualifiedLocalNLI(model_path='')
    try:
        with pytest.raises(RuntimeError, match='QUALIFIED_MODEL_UNAVAILABLE'): adapter.warmup()
    finally:
        adapter._worker.shutdown(wait=True)


@pytest.mark.parametrize('enabled,broken,expected', [(False,False,False),(True,False,True),(True,True,False)])
def test_startup_opt_in_and_failure_preserve_api_lifespan(monkeypatch, enabled, broken, expected):
    import backend.main as main
    import backend.providers.f1_claim_support_provider as provider
    calls = []
    def warmup():
        calls.append('warmup')
        if broken: raise RuntimeError('private artifact path must not be logged')
    monkeypatch.setenv('F1_NLI_WARMUP', str(enabled).lower())
    monkeypatch.setattr(main.workspace_repository, 'seed_demo_workspace', lambda:None)
    monkeypatch.setattr(provider, 'get_f1_semantic_verifier', lambda:SimpleNamespace(warmup=warmup))
    app = SimpleNamespace(state=SimpleNamespace())
    async def lifecycle():
        async with main.lifespan(app):
            assert app.state.f1_nli_ready is expected
            assert app.state.f1_embedding_ready is True
    asyncio.run(lifecycle())
    assert len(calls) == int(enabled)
