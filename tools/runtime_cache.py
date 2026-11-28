import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.vendor.surfsense.prompt_cache import prompt_cache_mib
from backend.vendor.surfsense.types import HardwareBudget
print(prompt_cache_mib(HardwareBudget(2*1024**3)))
