"""
simulate_feature1_slo.py - Benchmark and SLO Evaluation Simulation for Feature 1 (Evidence-Grounded Q&A)
Evaluates:
1. Citation Verifier Latency & Precision (R2 Pure stdlib)
2. Hybrid RRF Retrieval Latency & Throughput (R3)
3. End-to-End QA Pipeline Latency & Availability (R1 + R2 + R3 + R4)
4. Hallucination Detection & Abstention Precision (Zero False Claims)
"""
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import statistics
from datetime import datetime
from typing import Dict, List, Any

from fastapi.testclient import TestClient
from backend.main import app
from backend.core.config import settings
from backend.repositories.workspace_repository import workspace_repository
from backend.services.qa_service import qa_service
from backend.algorithms.citation_verifier import CitationClaim, verify_citations


def run_slo_simulation():
    print("=" * 80)
    print(" WORKSPACEAI - FEATURE 1 (EVIDENCE-GROUNDED Q&A) SLO BENCHMARK SIMULATION")
    print(f" Timestamp: {datetime.now().isoformat()}")
    print("=" * 80)

    # Setup demo workspace
    workspace_repository.seed_demo_workspace()
    lookup = workspace_repository.build_page_lookup()
    client = TestClient(app)

    # Target SLOs definition
    slos = {
        "availability_target": 99.5,         # >= 99.5%
        "verifier_latency_p95_target": 20.0, # < 20ms
        "verifier_latency_p99_target": 50.0, # < 50ms
        "retrieval_latency_p95_target": 150.0,# < 150ms
        "anti_hallucination_target": 100.0,   # 100% detection of fake citations
        "e2e_availability_target": 99.0,      # >= 99% HTTP 200 & valid status
    }

    # --------------------------------------------------------------------------
    # 1. SIMULATION: Citation Verifier (Pure Stdlib R2) Latency & Precision
    # --------------------------------------------------------------------------
    print("\n[1/4] Chạy Simulation: Thuật toán Citation Verifier (Pure stdlib R2)...")
    verifier_latencies = []
    hallucination_detected = 0
    total_hallucination_tests = 50

    # 1.1 Valid claims latency test (100 iterations)
    sample_valid_claim = CitationClaim(
        claim_text="Báo cáo kỹ thuật 12-18 trang",
        cited_doc_id="Project_Brief.pdf",
        cited_page=6,
        evidence_quote="01 Engineering Report (12-18 pages recommended)",
        cited_start_line=1,
        cited_end_line=2,
    )

    for _ in range(100):
        t0 = time.perf_counter()
        res = verify_citations([sample_valid_claim], lookup)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        verifier_latencies.append(dt_ms)

    # 1.2 Adversarial / Hallucinated claims test (50 iterations)
    for i in range(total_hallucination_tests):
        fake_claim = CitationClaim(
            claim_text=f"Bịa đặt nội dung {i}",
            cited_doc_id="Project_Brief.pdf",
            cited_page=6,
            evidence_quote=f"Nội dung hoàn toàn không tồn tại trong tài liệu {i}",
            cited_start_line=1,
            cited_end_line=2,
        )
        res_fake = verify_citations([fake_claim], lookup)
        if len(res_fake.hallucination_flags) == 1 and res_fake.hallucination_flags[0].verification_status == "UNGROUNDED_QUOTE":
            hallucination_detected += 1

    verifier_p50 = statistics.median(verifier_latencies)
    verifier_p95 = statistics.quantiles(verifier_latencies, n=100)[94]
    verifier_p99 = statistics.quantiles(verifier_latencies, n=100)[98]
    anti_hallucination_rate = (hallucination_detected / total_hallucination_tests) * 100.0

    print(f"  - Verifier Latency: p50={verifier_p50:.2f}ms, p95={verifier_p95:.2f}ms, p99={verifier_p99:.2f}ms")
    print(f"  - Tỉ lệ phát hiện trích dẫn bịa đặt: {anti_hallucination_rate:.1f}% ({hallucination_detected}/{total_hallucination_tests})")

    # --------------------------------------------------------------------------
    # 2. SIMULATION: Hybrid RRF Retrieval Latency & Throughput (R3)
    # --------------------------------------------------------------------------
    print("\n[2/4] Chạy Simulation: Hybrid RRF Retrieval Engine (BM25 + Dense)...")
    retrieval_latencies = []
    queries = [
        "Submission Package gồm những gì?",
        "Hạn nộp bài cuối kỳ",
        "Tiêu chuẩn kỹ thuật R1 đến R5",
        "Báo cáo kỹ thuật bao nhiêu trang?",
        "Mô hình máy học hoặc kiến trúc hệ thống",
    ]

    for q in queries * 10:  # 50 searches
        t0 = time.perf_counter()
        results = workspace_repository.search(q, top_k=5)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        retrieval_latencies.append(dt_ms)

    retrieval_p50 = statistics.median(retrieval_latencies)
    retrieval_p95 = statistics.quantiles(retrieval_latencies, n=100)[94]
    retrieval_p99 = statistics.quantiles(retrieval_latencies, n=100)[98]

    print(f"  - Retrieval Latency: p50={retrieval_p50:.2f}ms, p95={retrieval_p95:.2f}ms, p99={retrieval_p99:.2f}ms")

    # --------------------------------------------------------------------------
    # 3. SIMULATION: End-to-End QA Fast & Mock Throughput (Load test)
    # --------------------------------------------------------------------------
    print("\n[3/4] Chạy Simulation: End-to-End API /api/chat QA Load & Availability (Mock Engine)...")
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"

    e2e_latencies = []
    successful_requests = 0
    total_e2e_requests = 40

    test_payloads = [
        {"query": "Gói nộp bài gồm những gì?", "selected_doc_ids": ["Project_Brief.pdf"]},
        {"query": "Tiêu chuẩn kỹ thuật R1 đến R5", "selected_doc_ids": ["Project_Brief.pdf"]},
        {"query": "Một câu hỏi hoàn toàn vô nghĩa không có trong tài liệu?", "selected_doc_ids": ["Project_Brief.pdf"]},
    ]

    t_start_total = time.perf_counter()
    for i in range(total_e2e_requests):
        payload = test_payloads[i % len(test_payloads)]
        t0 = time.perf_counter()
        resp = client.post("/api/chat", json=payload)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        e2e_latencies.append(dt_ms)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("route") == "QA_FLOW" and data.get("status") in ("ANSWER_VERIFIED", "ABSTAINED_INSUFFICIENT_EVIDENCE"):
                successful_requests += 1

    total_time_s = time.perf_counter() - t_start_total
    throughput_rps = total_e2e_requests / total_time_s
    e2e_availability = (successful_requests / total_e2e_requests) * 100.0
    e2e_p50 = statistics.median(e2e_latencies)
    e2e_p95 = statistics.quantiles(e2e_latencies, n=100)[94]

    print(f"  - E2E Availability: {e2e_availability:.1f}% ({successful_requests}/{total_e2e_requests} requests)")
    print(f"  - E2E Latency (Mock/Pure Pipeline): p50={e2e_p50:.2f}ms, p95={e2e_p95:.2f}ms")
    print(f"  - Throughput: {throughput_rps:.1f} requests/sec")

    # --------------------------------------------------------------------------
    # 4. LIVE OLLAMA Q&A INFERENCE TIME (Real Local LLM Qwen2.5)
    # --------------------------------------------------------------------------
    print("\n[4/4] Đo kiểm thực tế: Live Ollama Qwen2.5 Local Inference...")
    settings.llm_provider = "ollama"
    real_llm_status = "N/A"
    real_llm_duration_s = 0.0

    try:
        t0 = time.perf_counter()
        res_real = qa_service.answer_question(
            query="Submission Package gồm những gì?",
            selected_doc_ids=["Project_Brief.pdf"]
        )
        real_llm_duration_s = time.perf_counter() - t0
        real_llm_status = res_real.get("status")
        grounding_score = res_real.get("grounding_score", 0.0)
        print(f"  - Live Ollama Result: status={real_llm_status}, grounding_score={grounding_score}")
        print(f"  - Live Ollama Latency: {real_llm_duration_s:.2f} giây")
    except Exception as e:
        print(f"  - Live Ollama Exception: {e}")
    finally:
        settings.llm_provider = original_provider

    # --------------------------------------------------------------------------
    # 5. SLO SCORECARD EVALUATION REPORT
    # --------------------------------------------------------------------------
    print("\n" + "=" * 80)
    print(" BẢNG ĐỐI CHIẾU ĐÁNH GIÁ CHỈ SỐ SLO THỰC TẾ (SLO SCORECARD)")
    print("=" * 80)

    scorecard = [
        {
            "name": "SLO 1: Citation Verifier Latency (p95)",
            "target": f"< {slos['verifier_latency_p95_target']} ms",
            "actual": f"{verifier_p95:.2f} ms",
            "pass": verifier_p95 < slos["verifier_latency_p95_target"]
        },
        {
            "name": "SLO 2: Citation Verifier Latency (p99)",
            "target": f"< {slos['verifier_latency_p99_target']} ms",
            "actual": f"{verifier_p99:.2f} ms",
            "pass": verifier_p99 < slos["verifier_latency_p99_target"]
        },
        {
            "name": "SLO 3: Hybrid Retrieval Latency (p95)",
            "target": f"< {slos['retrieval_latency_p95_target']} ms",
            "actual": f"{retrieval_p95:.2f} ms",
            "pass": retrieval_p95 < slos["retrieval_latency_p95_target"]
        },
        {
            "name": "SLO 4: Anti-Hallucination Precision",
            "target": f"{slos['anti_hallucination_target']}%",
            "actual": f"{anti_hallucination_rate:.1f}%",
            "pass": anti_hallucination_rate >= slos["anti_hallucination_target"]
        },
        {
            "name": "SLO 5: Pipeline Availability (Success Rate)",
            "target": f">= {slos['e2e_availability_target']}%",
            "actual": f"{e2e_availability:.1f}%",
            "pass": e2e_availability >= slos["e2e_availability_target"]
        },
        {
            "name": "SLO 6: Local Ollama E2E Latency",
            "target": "< 10.0 s",
            "actual": f"{real_llm_duration_s:.2f} s",
            "pass": real_llm_duration_s < 10.0 and real_llm_status == "ANSWER_VERIFIED"
        }
    ]

    for item in scorecard:
        status_tag = "[PASS]" if item["pass"] else "[FAIL]"
        print(f" {status_tag:<8} | {item['name']:<42} | Mục tiêu: {item['target']:<10} | Thực tế: {item['actual']}")

    print("=" * 80)
    all_passed = all(item["pass"] for item in scorecard)
    if all_passed:
        print(" >> KẾT QUẢ TỔNG QUAN: TẤT CẢ CÁC CHỈ SỐ SLO ĐỀU ĐẠT CHUẨN (100% MET)")
    else:
        print(" >> KẾT QUẢ TỔNG QUAN: CÓ CHỈ SỐ CẦN TỐI ƯU THÊM.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_slo_simulation()
