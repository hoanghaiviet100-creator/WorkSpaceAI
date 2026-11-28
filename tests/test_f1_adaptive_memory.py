"""Affected integration/control checks; no mocked text proves AI quality."""
from dataclasses import asdict
import json
import pytest
from tools.resources import AdmissionDenied,GIB,Guard
from backend.services.f1_adaptive_memory import AdaptivePolicy,InferencePlan,PREFERRED,FALLBACK

def readings(ram=14,commit=24,gpu=14000):
    return dict(physical_free=int(ram*GIB),commit_free=int(commit*GIB),physical_total=32*GIB,commit_limit=48*GIB,gpu_free_mib=gpu,gpu_util_percent=0)

def policy(tmp_path,monkeypatch,snapshot):
    import backend.services.f1_adaptive_memory as module
    monkeypatch.setattr(module,'available_bytes',lambda:snapshot['physical_free'])
    p=AdaptivePolicy('http://unused.test',tmp_path/'policy.json',probe=lambda:snapshot)
    monkeypatch.setattr(p,'residency',lambda:[])
    return p

def test_9b_preference_when_resources_allow(tmp_path,monkeypatch):
    p=policy(tmp_path,monkeypatch,readings())
    plan=p.propose(PREFERRED)
    assert plan.model==PREFERRED and plan.num_ctx==4096

@pytest.mark.parametrize('snapshot',[readings(commit=10),readings(ram=7),readings(gpu=8000)])
def test_resource_constraints_never_relax_fixed_admission(tmp_path,monkeypatch,snapshot):
    p=policy(tmp_path,monkeypatch,snapshot)
    assert p.propose(FALLBACK) is None

def test_smaller_window_selected_without_inference_trials(tmp_path,monkeypatch):
    snap=readings();p=policy(tmp_path,monkeypatch,snap)
    wide=p.propose(FALLBACK,needed=8192)
    snap['physical_free']=5*GIB+wide.predicted_ram_bytes-80*1024**2
    reduced=p.propose(FALLBACK,needed=8192)
    assert reduced is not None and reduced.num_ctx in (2048,4096)

def test_measured_peak_only_raises_future_requirements(tmp_path,monkeypatch):
    snap=readings(ram=12);p=policy(tmp_path,monkeypatch,snap)
    p.write(dict(format=1,observations={FALLBACK+'@4096':dict(cold_ram_increase_bytes=9*GIB)}))
    assert p.propose(FALLBACK) is None

def test_qualified_context_stays_stable_with_more_memory(tmp_path,monkeypatch):
    snap=readings();p=policy(tmp_path,monkeypatch,snap)
    plan=InferencePlan(FALLBACK,p.catalog[FALLBACK]['digest'],4096,768)
    p.write(dict(selected=asdict(plan),observations={}))
    monkeypatch.setattr(p,'residency',lambda:[dict(name=FALLBACK,context_length=4096)])
    assert p.select().num_ctx==4096

def test_unapproved_model_and_invalid_context_are_rejected(tmp_path,monkeypatch):
    p=policy(tmp_path,monkeypatch,readings())
    with pytest.raises(AdmissionDenied):p.propose('unapproved:99b')
    selected=InferencePlan(FALLBACK,p.catalog[FALLBACK]['digest'],65536,512)
    p.write(dict(selected=asdict(selected)))
    with pytest.raises(AdmissionDenied):p.select()

def test_both_failures_stop_future_automatic_generation(tmp_path,monkeypatch):
    p=policy(tmp_path,monkeypatch,readings());p.write(dict(stopped=True))
    with pytest.raises(AdmissionDenied,match='BOTH_MODEL'):p.select()

def test_recovery_does_not_switch_while_old_model_remains(tmp_path,monkeypatch):
    import backend.services.f1_adaptive_memory as module
    p=policy(tmp_path,monkeypatch,readings())
    monkeypatch.setattr(p,'residency',lambda:[dict(name=PREFERRED)])
    class Response:
        def raise_for_status(self):pass
    class Client:
        def __init__(self,*a,**k):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def post(self,*a,**kw):assert kw['json']['keep_alive']==0;return Response()
    monkeypatch.setattr(module.httpx,'Client',Client)
    times=iter([0,21]);monkeypatch.setattr(module.time,'monotonic',lambda:next(times))
    with pytest.raises(AdmissionDenied,match='RECOVERY'):p.recover()

class AdaptiveFake:
    metrics={}
    def __init__(self):self.calls=0;self.sent=[];self.output=0
    def prepare(self,needed=4096):return InferencePlan(FALLBACK,'controlled-digest',2048,512)
    def generate(self,messages,*a,**kw):
        self.calls+=1;self.sent=messages;self.output=kw['output_tokens'];return 'It starts at 10:00 [1].'

def test_budget_preserves_question_and_provenance():
    from backend.services.f1_basic_qa import BasicQA
    from backend.repositories.workspace_repository import WorkspaceRepository
    from backend.vendor.surfsense.admission.cost import request_cost
    repo=WorkspaceRepository();repo.ingest_text_document('doc','doc.txt',[(1,'The workshop starts at 10:00.')])
    fake=AdaptiveFake();result=BasicQA(repo,fake).answer_question('When does it start?',['doc'])
    assert fake.calls==1 and 'When does it start?' in fake.sent[-1].content
    assert request_cost(fake.sent,fake.output,budget=2048,slots=1)+128<=2048
    assert result['validated_claims'][0]['evidence_quote']=='The workshop starts at 10:00.'
    assert result['semantic_verified'] is False

def test_oversized_essential_question_is_not_truncated_or_generated():
    from backend.services.f1_basic_qa import BasicQA
    from backend.repositories.workspace_repository import WorkspaceRepository
    repo=WorkspaceRepository();repo.ingest_text_document('doc','doc.txt',[(1,'The workshop starts at 10:00.')])
    fake=AdaptiveFake();result=BasicQA(repo,fake).answer_question('x'*4000,['doc'])
    assert result['status']=='ABSTAINED_INSUFFICIENT_EVIDENCE' and fake.calls==0

def test_telemetry_reports_sampled_peaks(monkeypatch):
    import backend.services.f1_session_runtime as runtime
    samples=iter([readings(),readings(ram=12,commit=21,gpu=11000)])
    monkeypatch.setattr(runtime.guard,'probe',lambda:next(samples));monkeypatch.setattr(runtime,'gpu_total_mib',lambda:16000)
    trace=runtime.ResourceTrace();trace.capture();result=trace.summary()
    assert result['ram_increase_bytes']==2*GIB and result['commit_increase_bytes']==3*GIB
    assert result['gpu_used_peak_mib']==5000 and result['samples']==2


def test_cold_selection_also_leaves_warm_commit_headroom(tmp_path,monkeypatch):
    p=policy(tmp_path,monkeypatch,readings(ram=14,commit=14))
    assert p.propose(FALLBACK) is None

def test_measured_host_footprint_does_not_charge_weights_twice(tmp_path,monkeypatch):
    snap=readings(ram=10,commit=15)
    p=policy(tmp_path,monkeypatch,snap)
    p.write(dict(context_caps={FALLBACK:4096},observations={FALLBACK+'@8192':dict(last_success=True,cold_ram_increase_bytes=400*1024**2,cold_commit_increase_bytes=5200*1024**2,cold_vram_increase_bytes=4800*1024**2)}))
    plan=p.propose(FALLBACK)
    assert plan is not None and plan.num_ctx<=4096 and plan.predicted_ram_bytes>=GIB
    assert snap['commit_free']-plan.predicted_commit_bytes>=9*GIB


@pytest.mark.parametrize('tokens,expected',[(3000,4096),(7000,8192),(15000,16384),(90000,32768)])
def test_context_tracks_task_demand(tmp_path,monkeypatch,tokens,expected):
    p=policy(tmp_path,monkeypatch,readings(ram=30,commit=40,gpu=16000))
    assert p.propose(FALLBACK,needed=tokens).num_ctx==expected
