"""Resource-admitted generation planning and model residency."""
import asyncio
from dataclasses import asdict,dataclass,replace
import json,math,os,threading,time,uuid
from pathlib import Path
import httpx
from backend.core.config import settings
from backend.vendor.surfsense.fit import HardwareBudget,ModelShape,KvPrecision,FitState
from backend.vendor.surfsense.fit.plan_load import plan_load
from backend.vendor.surfsense.fit.itemisation import itemise
from backend.vendor.surfsense.hardware.budget import build_budget
from backend.vendor.surfsense.hardware.devices import Device,DeviceType
from backend.vendor.surfsense.hardware.system_memory import available_bytes
from backend.vendor.surfsense.model_metadata import GgufHeader
from backend.vendor.surfsense.model_shape import to_shape
from backend.vendor.surfsense.residency import SelectedModel,warm_selected
from backend.vendor.surfsense import ollama_residency
from tools.resources import Guard,AdmissionDenied,sample,host_memory,GIB

ROOT=Path(__file__).resolve().parents[2]
PREFERRED='qwen3.5:9b-q4_K_M'
FALLBACK='qwen2.5:7b-q4_K_M'
EMBEDDING='qwen3-embedding:0.6b'
CONTEXTS=(32768,16384,8192,4096,2048)
STATE_LOCK=threading.RLock()

@dataclass(frozen=True)
class InferencePlan:
    model: str
    digest: str
    num_ctx: int
    num_predict: int
    precision: str='q8_0'
    num_batch: int=128
    predicted_ram_bytes: int=0
    predicted_commit_bytes: int=0
    predicted_vram_bytes: int=0
    def options(self,output=None):
        return dict(num_ctx=self.num_ctx,num_predict=output or self.num_predict,num_batch=self.num_batch,
            use_mmap=False,temperature=0.1,top_p=0.85,repeat_penalty=1.1)

class AdaptivePolicy:
    def __init__(self,base_url=None,state_path=None,probe=None):
        self.base_url=(base_url or settings.ollama_base_url).rstrip('/')
        self.path=Path(state_path or os.getenv('F1_ADAPTIVE_POLICY',ROOT/'.runtime/cpu-generation-policy.json' if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu' else ROOT/'.runtime/adaptive-demand-policy.json'))
        self.probe=probe or sample
        self.catalog=json.loads((ROOT/'model-catalog.json').read_text(encoding='utf-8'))['models'] if (ROOT/'model-catalog.json').exists() else {}
        self.metadata_path=ROOT/'.runtime/adaptive-model-metadata.json'
    def read(self):
        with STATE_LOCK:
            return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(format=1,observations={},qualification=[])
    def write(self,state):
        with STATE_LOCK:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            temp=self.path.with_suffix('.tmp');temp.write_text(json.dumps(state,indent=2),encoding='utf-8');temp.replace(self.path)
    def residency(self):
        with httpx.Client(timeout=httpx.Timeout(5,connect=2),trust_env=False) as c:
            response=c.get(self.base_url+'/api/ps');response.raise_for_status();data=response.json()
        if not isinstance(data.get('models'),list):raise AdmissionDenied('RESIDENCY_UNAVAILABLE')
        return data['models']
    def recover(self,keep=None):
        """Unload only this daemon's models. Switching is not allowed before recovery."""
        rows=self.residency()
        for row in rows:
            name=row.get('name','')
            if name!=keep:
                with httpx.Client(timeout=15,trust_env=False) as c:
                    response=c.post(self.base_url+'/api/generate',json=dict(model=name,keep_alive=0));response.raise_for_status()
        deadline=time.monotonic()+20
        while True:
            remaining=self.residency()
            if all(m.get('name')==keep for m in remaining):
                m=host_memory()
                if m['physical_free']>=Guard.RESERVE_PHYSICAL and m['commit_free']>=Guard.RESERVE_COMMIT:
                    self.event(dict(type='recovered',keep=keep,resident_models=[m.get('name') for m in remaining],readings=self.probe()))
                    return remaining
            if time.monotonic()>deadline:raise AdmissionDenied('MODEL_CLEANUP_OR_MEMORY_RECOVERY_FAILED')
            time.sleep(0.5)
    def metadata(self,name):
        rows=json.loads(self.metadata_path.read_text(encoding='utf-8')) if self.metadata_path.exists() else {}
        if name not in rows:raise AdmissionDenied('MODEL_METADATA_UNAVAILABLE')
        info=dict(rows[name]['model_info']);info.pop('tokenizer.ggml.tokens',None)
        shape=to_shape(GgufHeader(info))
        if not shape.block_count or not shape.embedding_length or not shape.n_vocab:raise AdmissionDenied('MODEL_SHAPE_INCOMPLETE')
        return shape,rows[name]
    def event(self,event):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        event=dict(utc=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**event)
        with STATE_LOCK:
            with self.path.with_name('adaptive-events.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(event)+'\n')
    def propose(self,name,readings=None,resident=None,needed=4096):
        if name not in (PREFERRED,FALLBACK) or name not in self.catalog:raise AdmissionDenied('GENERATION_MODEL_NOT_APPROVED')
        readings=readings or self.probe();resident=self.residency() if resident is None else resident
        # Source hardware detection is executed; take the lower OS reading rather than capacity.
        ram=min(readings['physical_free'],available_bytes())
        commit=readings['commit_free'];free_gpu=int(readings['gpu_free_mib']*1024**2)
        device=Device('CUDA0','RTX 5060 Ti',DeviceType.GPU,16*GIB,free_gpu)
        live=build_budget([device],max(0,min(ram-Guard.RESERVE_PHYSICAL,commit-Guard.RESERVE_COMMIT)))
        live=replace(live,fit_reserve_bytes=2*GIB)
        shape,_=self.metadata(name);weights=self.catalog[name]['weights_bytes']
        context_cap=next((size for size in reversed(CONTEXTS) if size >= max(4096,needed)),32768)
        upstream=plan_load(replace(shape,context_length=min(shape.context_length,context_cap)),weights,live,live,slots=1)
        observations=self.read().get('observations',{});reasons=[]
        for ctx in CONTEXTS:
            if ctx>upstream.n_ctx:continue
            items=itemise(shape,weights,ctx,KvPrecision.Q8_0,slots=1)
            # A mapped/cold weight read can occupy host pages even with full GPU offload.
            # Include the capped prompt cache. Observed peaks can only raise the estimate.
            ram_need=items.total+512*1024**2
            commit_need=ram_need+256*1024**2
            key=name+'@'+str(ctx)
            related=[(int(k.rsplit('@',1)[1]),o) for k,o in observations.items() if k.startswith(name+'@') and o.get('last_success')]
            # After a measured successful cold load with use_mmap=False, use its
            # actual host footprint, keeping one GiB for pinned/cache allocations.
            # Commit remains device-dependent: remove only the upstream-priced
            # window term before pricing a narrower window, never the fixed model.
            if related:
                ram_need=max(GIB,max(int(o.get('cold_ram_increase_bytes',0)*1.25) for _,o in related))
                learned_commit=[]
                for old_ctx,o in related:
                    old_items=itemise(shape,weights,old_ctx,KvPrecision.Q8_0,slots=1)
                    fixed=max(0,o.get('cold_commit_increase_bytes',0)-old_items.kv_bytes-old_items.compute_bytes)
                    learned_commit.append(int((fixed+items.kv_bytes+items.compute_bytes)*1.10))
                commit_need=max(items.total+256*1024**2,max(learned_commit,default=0))
                gpu_need=max(items.total,max(int(o.get('cold_vram_increase_bytes',0)*1.10) for _,o in related))
            else:
                gpu_need=items.total
            failed=[o for k,o in observations.items() if k.startswith(name+'@') and not o.get('last_success')]
            if failed:
                ram_need=max(ram_need,max(int(o.get('cold_ram_increase_bytes',0)*1.10) for o in failed))
                commit_need=max(commit_need,max(int(o.get('cold_commit_increase_bytes',0)*1.10) for o in failed))
                gpu_need=max(gpu_need,max(int(o.get('cold_vram_increase_bytes',0)*1.10) for o in failed))
            # Leave the existing warm-admission headroom after residency as well
            # as protecting the cold/transient load. No guard threshold changes.
            required=dict(physical_free=max(8*GIB,5*GIB+ram_need),
                commit_free=max(12*GIB,9*GIB+commit_need),gpu_free_mib=max(10240,gpu_need/1024**2+2048))
            denied=[k for k,v in required.items() if (ram if k=="physical_free" else readings[k])<v]
            reasons.append(dict(context=ctx,required=required,denied=denied))
            if not denied:
                output={32768:1600,16384:1400,8192:1200,4096:768,2048:512}[ctx]
                plan=InferencePlan(name,self.catalog[name]['digest'],ctx,output,predicted_ram_bytes=ram_need,predicted_commit_bytes=commit_need,predicted_vram_bytes=gpu_need)
                self.event(dict(type='plan',selected=asdict(plan),readings=readings,candidates=reasons))
                return plan
        self.event(dict(type='no_safe_context',model=name,readings=readings,candidates=reasons))
        return None
    def select(self,needed=4096):
        state=self.read()
        if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu' and any(state.get(key,{}).get('model',FALLBACK)!=FALLBACK for key in ('selected','candidate')):
            raise AdmissionDenied('GENERATION_MODEL_NOT_APPROVED')
        if state.get('stopped'):
            raise AdmissionDenied('BOTH_MODEL_QUALIFICATION_STOPPED')
        selected=state.get('selected') or state.get('candidate')
        resident=self.residency()
        if selected:
            plan=InferencePlan(**selected)
            if plan.model not in (PREFERRED,FALLBACK) or plan.digest!=self.catalog.get(plan.model,{}).get('digest') or plan.num_ctx not in CONTEXTS:
                raise AdmissionDenied('INVALID_ADAPTIVE_CONFIGURATION')
            active=next((m for m in resident if m.get('name')==plan.model),None)
            if active and not state.get('candidate') and active.get('context_length') in CONTEXTS:
                ctx=active['context_length']
                plan=replace(plan,num_ctx=ctx,num_predict={2048:512,4096:768,8192:1200,16384:1400,32768:1600}[ctx])
            matching=next((m for m in resident if m.get('name')==plan.model and m.get('context_length')==plan.num_ctx),None)
            # Reprice a larger task before unloading. If current free memory
            # alone qualifies the larger load, switching is conservative.
            if needed > plan.num_ctx and not state.get('candidate'):
                larger=self.propose(plan.model,needed=needed)
                if larger and larger.num_ctx>plan.num_ctx:
                    return larger
            if matching:
                Guard(self.path.with_name('adaptive-admission.jsonl'),probe=self.probe).admit('generation_request')
                obs=state.get('observations',{}).get(plan.model+'@'+str(plan.num_ctx),{})
                readings=self.probe()
                if readings['physical_free']<Guard.RESERVE_PHYSICAL+max(GIB,int(obs.get('warm_ram_increase_bytes',0)*1.1)) or readings['commit_free']<Guard.RESERVE_COMMIT+max(GIB,int(obs.get('warm_commit_increase_bytes',0)*1.1)):
                    raise AdmissionDenied('RESOURCE_ADMISSION_DENIED:physical_free,commit_free')
                return plan
            # Metadata/content maps survive model unloads. Keep the same qualified window.
            self.recover(keep=plan.model if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu' else EMBEDDING)
            readings=self.probe()
            need_ram=max(8*GIB,5*GIB+plan.predicted_ram_bytes)
            need_commit=max(12*GIB,9*GIB+plan.predicted_commit_bytes)
            if readings['physical_free']<need_ram or readings['commit_free']<need_commit:
                smaller=self.propose(plan.model,needed=min(plan.num_ctx,needed))
                if smaller and not state.get('candidate'):return smaller
                raise AdmissionDenied('RESOURCE_ADMISSION_DENIED:physical_free,commit_free')
            Guard(self.path.with_name('adaptive-admission.jsonl'),probe=self.probe).admit('generation_load')
            return plan
        self.recover()
        for name in ((FALLBACK,) if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu' else (FALLBACK,PREFERRED)):
            plan=self.propose(name,needed=needed)
            if plan:
                if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu':
                    state=self.read();state['selected']=asdict(plan)
                    state['qualification_passed']=False
                    self.write(state)
                return plan
        raise AdmissionDenied('NO_SAFE_APPROVED_MODEL_CONFIGURATION')
    def observe(self,plan,trace,cold,success):
        state=self.read();observations=state.setdefault('observations',{});key=plan.model+'@'+str(plan.num_ctx)
        obs=observations.setdefault(key,{})
        for metric in ('ram','commit','vram'):
            field=('cold_' if cold else 'warm_')+metric+'_increase_bytes'
            obs[field]=max(obs.get(field,0),trace.get(metric+'_increase_bytes',0))
        obs['last_success']=success;obs['last_trace']=trace
        self.write(state)
    def activate(self,plan,on_load=None):
        from backend.services.f1_session_runtime import generation_load_slot
        with generation_load_slot():
            return self._activate(plan,on_load)
    def _activate(self,plan,on_load=None):
        rows=self.residency()
        if any(m.get('name')==plan.model and m.get('context_length')==plan.num_ctx for m in rows):return 0.0
        self.recover(keep=plan.model if os.getenv('F1_EMBEDDING_BACKEND') == 'fastembed_cpu' else EMBEDDING);Guard(self.path.with_name('adaptive-admission.jsonl'),probe=self.probe).admit('generation_load')
        ollama_residency.ACTIVE_OPTIONS.clear();ollama_residency.ACTIVE_OPTIONS.update(plan.options())
        start=time.perf_counter()
        if on_load:on_load()
        if not asyncio.run(warm_selected(SelectedModel(plan.model),self.base_url)):raise AdmissionDenied('MODEL_RESIDENCY_LOAD_FAILED')
        rows=self.residency()
        if not any(row.get('name')==plan.model and row.get('context_length')==plan.num_ctx for row in rows):raise AdmissionDenied('MODEL_RESIDENCY_MISMATCH')
        return round((time.perf_counter()-start)*1000,2)

policy=AdaptivePolicy()
