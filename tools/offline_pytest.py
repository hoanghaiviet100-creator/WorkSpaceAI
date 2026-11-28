import inspect, os, socket, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ["F1_SESSION_B"]="false"
os.environ.pop("F1_STORE_PATH",None)
os.environ.update(PYTHON_DOTENV_DISABLED='1', LLM_PROVIDER='mock', EMAIL_DISPATCH_MODE='local_mock', GEMINI_API_KEY='', GMAIL_APP_PASSWORD='', OLLAMA_MODEL='qwen2.5:7b', OLLAMA_EMBED_MODEL='qwen3-embedding:0.6b', F1_GENERATION_MODEL='qwen3.5:9b-q4_K_M', F1_GENERATION_THINK='true', PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
os.environ.pop('RUN_OLLAMA_EMBEDDING_SMOKE', None)
os.environ.pop('F1_GENERATION_TEST_EVIDENCE', None)
def blocked(*args, **kwargs):
    raise AssertionError("F1-MODEL-01: real HTTP/SMTP/network access is forbidden")

original_connect = socket.socket.connect
original_connect_ex = socket.socket.connect_ex

def local_socketpair():
    # Windows asyncio needs the standard library's loopback socketpair helper.
    return any(f.function in {"_socketpair", "_fallback_socketpair", "socketpair"}
               and f.filename == socket.__file__
               for f in inspect.stack(context=0))

def guarded_connect(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not local_socketpair():
        return blocked()
    return original_connect(sock, address)

def guarded_connect_ex(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6) and not local_socketpair():
        return blocked()
    return original_connect_ex(sock, address)

socket.create_connection = blocked
socket.socket.connect = guarded_connect
socket.socket.connect_ex = guarded_connect_ex

import httpx
httpx.HTTPTransport.handle_request = blocked

async def async_blocked(*args, **kwargs):
    return blocked()

httpx.AsyncHTTPTransport.handle_async_request = async_blocked

import smtplib
smtplib.SMTP.connect = blocked
smtplib.SMTP_SSL.connect = blocked


import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
