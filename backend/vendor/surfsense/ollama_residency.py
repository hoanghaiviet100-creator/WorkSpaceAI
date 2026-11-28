import asyncio
import httpx
PROVIDER='ollama'
class RouterClient:
    def __init__(self,base_url,transport=None): self.base_url=base_url;self.transport=transport
    async def load(self,name):
        global ACTIVE_TASK,ACTIVE_LOOP
        ACTIVE_TASK=asyncio.current_task();ACTIVE_LOOP=asyncio.get_running_loop()
        # Empty generation loads/reserves the model, and generates zero answer tokens.
        async with httpx.AsyncClient(timeout=httpx.Timeout(180,connect=3),transport=self.transport,trust_env=False) as client:
            response=await client.post(self.base_url+'/api/generate',json=dict(model=name,prompt='',stream=False,keep_alive=-1,options=ACTIVE_OPTIONS))
            response.raise_for_status()
            data=response.json()
            if data.get('error') or data.get('model')!=name: raise httpx.ProtocolError('Invalid local residency response')
            LAST_LOAD.clear();LAST_LOAD.update(data)
ACTIVE_OPTIONS={}
LAST_LOAD={}

ACTIVE_TASK=None
ACTIVE_LOOP=None
def abort_active_load():
    if ACTIVE_TASK is not None and ACTIVE_LOOP is not None and ACTIVE_LOOP.is_running():
        ACTIVE_LOOP.call_soon_threadsafe(ACTIVE_TASK.cancel)
