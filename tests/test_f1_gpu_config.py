"""Render real Compose merges without a daemon, secrets, or inference requests."""
import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
BASE = "docker-compose.yml"
F1 = "deploy/f1/compose.yml"
GPU = "deploy/f1/compose.gpu.yml"
CPU = "deploy/f1/compose.cpu.yml"
LAT = "benchmarks/f1_latency/compose.override.yml"
OLD_GPU = "benchmarks/f1_latency/compose.gpu.yml"


@pytest.fixture(scope="module")
def configs(tmp_path_factory):
    temp = tmp_path_factory.mktemp("f1-gpu-config")
    empty_env = temp / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    # A synthetic legacy reservation exercises the other Docker GPU request form.
    reservation = temp / "reservation.yml"
    reservation.write_text(
        "services:\n  ollama:\n    deploy:\n      resources:\n        reservations:\n"
        "          devices:\n            - driver: nvidia\n              count: all\n"
        "              capabilities: [gpu]\n", encoding="utf-8",
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("COMPOSE_")}
    # Verify the F1 overlay overrides stale template/host values in both modes.
    env.update(LLM_PROVIDER="gemini", OLLAMA_MODEL="qwen2.5:3b",
               OLLAMA_EMBED_MODEL="nomic-embed-text", OLLAMA_DOCKER_URL="http://wrong.invalid",
               F1_GENERATION_MODEL="wrong:stale", F1_GENERATION_THINK="false")
    cases = {
        "base": [BASE],
        "legacy_gpu": [BASE, OLD_GPU],
        "latency_cpu": [BASE, LAT],
        "latency_gpu": [BASE, LAT, OLD_GPU],
        "f1_native": [BASE, F1],
        "f1_cpu": [BASE, F1, CPU],
        "f1_gpu": [BASE, F1, GPU],
        "f1_cpu_after_gpu": [BASE, F1, GPU, CPU],
        "f1_cpu_after_legacy_gpu": [BASE, F1, OLD_GPU, CPU],
        "f1_cpu_after_reservation": [BASE, F1, str(reservation), CPU],
    }
    result = {}
    for name, files in cases.items():
        command = ["rtk", "proxy", "docker", "compose", "--project-directory", str(ROOT),
                   "--env-file", str(empty_env), "-p", "f1-gpu01-config"]
        for file in files:
            command.extend(["-f", str(ROOT / file)])
        command.extend(["config", "--no-env-resolution", "--format", "json"])
        run = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env, timeout=45)
        assert run.returncode == 0, f"{name}: {run.stderr}"
        result[name] = json.loads(run.stdout)
        print(f"COMPOSE_VALID {name}: exit=0")
    return result


def gpu_requests(service):
    return service.get("gpus") or service.get("deploy", {}).get("resources", {}).get("reservations", {}).get("devices")


def test_all_supported_compose_modes_validate(configs):
    assert len(configs) == 10
    for config in configs.values():
        assert set(config["services"]) == {"app", "ollama"}


@pytest.mark.parametrize("mode", ["f1_native", "f1_cpu", "f1_gpu", "f1_cpu_after_gpu", "f1_cpu_after_legacy_gpu", "f1_cpu_after_reservation"])
def test_f1_models_and_endpoint_ignore_stale_environment(configs, mode):
    env = configs[mode]["services"]["app"]["environment"]
    assert env["LLM_PROVIDER"] == "ollama"
    assert env["OLLAMA_BASE_URL"] == "http://ollama:11434"
    assert env["OLLAMA_MODEL"] == "qwen2.5:7b"
    assert env["F1_GENERATION_MODEL"] == "qwen3.5:9b-q4_K_M"
    assert env["F1_GENERATION_THINK"] == "true"
    assert env["OLLAMA_EMBED_MODEL"] == "qwen3-embedding:0.6b"


@pytest.mark.parametrize("mode", ["base", "latency_cpu", "f1_native", "f1_cpu", "f1_cpu_after_gpu", "f1_cpu_after_legacy_gpu", "f1_cpu_after_reservation"])
def test_cpu_startup_has_no_gpu_request(configs, mode):
    assert not gpu_requests(configs[mode]["services"]["ollama"])


@pytest.mark.parametrize("mode", ["legacy_gpu", "latency_gpu", "f1_gpu"])
def test_gpu_mode_requests_all_gpus(configs, mode):
    requests = configs[mode]["services"]["ollama"]["gpus"]
    assert len(requests) == 1 and requests[0]["count"] == -1


def test_cpu_last_removes_requests_and_disables_gpu_libraries(configs):
    for name in ("f1_cpu", "f1_cpu_after_gpu", "f1_cpu_after_legacy_gpu", "f1_cpu_after_reservation"):
        service = configs[name]["services"]["ollama"]
        assert service["runtime"] == "runc"
        assert service["environment"] == {
            "CUDA_VISIBLE_DEVICES": "-1", "NVIDIA_VISIBLE_DEVICES": "void", "OLLAMA_VULKAN": "0",
        }


def test_device_mode_preserves_app_model_storage_and_native_startup(configs):
    native = configs["f1_native"]
    for name in ("f1_cpu", "f1_gpu", "f1_cpu_after_gpu", "f1_cpu_after_legacy_gpu", "f1_cpu_after_reservation"):
        config = configs[name]
        assert config["services"]["app"] == native["services"]["app"]
        assert config["volumes"] == native["volumes"]
        assert config["networks"] == native["networks"]
        ollama = config["services"]["ollama"]
        assert ollama["image"] == native["services"]["ollama"]["image"]
        assert ollama["volumes"] == native["services"]["ollama"]["volumes"]
        assert ollama["volumes"][0]["target"] == "/root/.ollama"
        assert config["volumes"]["ollama_models"]["name"] == "workspaceai_ollama_models"
        assert ollama.get("entrypoint") is None and ollama.get("command") is None
