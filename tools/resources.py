"""Host-side admission; missing or unsafe samples fail closed before a request."""
import ctypes,subprocess,json,threading,time,math
from pathlib import Path
GIB=1024**3
class AdmissionDenied(RuntimeError):pass
def host_memory():
    class M(ctypes.Structure):
        _fields_=[('length',ctypes.c_ulong),('load',ctypes.c_ulong)]+[(n,ctypes.c_ulonglong) for n in ['total','available','total_page','available_page','total_virtual','available_virtual','extended']]
    m=M();m.length=ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise AdmissionDenied('HOST_MEMORY_UNAVAILABLE')
    return dict(physical_free=m.available,commit_free=m.available_page,physical_total=m.total,commit_limit=m.total_page)
def sample():
    m=host_memory()
    p=subprocess.run(['rtk','proxy','nvidia-smi','--query-gpu=memory.free,utilization.gpu','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=10)
    if p.returncode:raise AdmissionDenied('GPU_SAMPLE_UNAVAILABLE')
    free,util=map(float,p.stdout.strip().split(','));m.update(gpu_free_mib=free,gpu_util_percent=util)
    return m
class Guard:
    RESERVE_PHYSICAL=4*GIB
    RESERVE_COMMIT=8*GIB
    BUDGETS={'metadata':(0,0,0),'nli_load':(2*GIB,2*GIB,0),
             'nli_request':(256*1024**2,256*1024**2,0),
             'generation_load':(4*GIB,4*GIB,10240),'generation_request':(GIB,GIB,2048)}
    def __init__(self,path,probe=sample):self.path=Path(path);self.probe=probe;self.inflight=threading.Lock()
    def admit(self,phase):
        if phase not in self.BUDGETS:raise AdmissionDenied('UNKNOWN_RESOURCE_PHASE')
        readings=self.probe();physical,commit,gpu=self.BUDGETS[phase]
        required=dict(physical_free=self.RESERVE_PHYSICAL+physical,commit_free=self.RESERVE_COMMIT+commit,gpu_free_mib=gpu)
        reasons=[key for key,value in required.items() if type(readings.get(key)) not in (int,float)
                 or not math.isfinite(readings[key]) or readings[key]<value]
        row=dict(monotonic=time.perf_counter(),phase=phase,readings=readings,required=required,admitted=not reasons,denied_metrics=reasons)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.path.open('a',encoding='utf-8') as f:f.write(json.dumps(row)+'\n')
        if reasons:raise AdmissionDenied('RESOURCE_ADMISSION_DENIED:'+','.join(reasons))
        return row
    def run(self,phase,operation):
        if not self.inflight.acquire(blocking=False):raise AdmissionDenied('REQUEST_ALREADY_IN_FLIGHT')
        try:
            self.admit(phase)
            return operation()
        finally:self.inflight.release()
