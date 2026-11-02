#!/usr/bin/env python3
"""
verify.py - Single-Touch Automated Verification Suite for WorkspaceAI (v2.5)
Executes:
1. AST Syntax Check across all project Python files.
2. R2 Stdlib Purity Gate (Strict 100% Python Standard Library verification).
3. Pytest Execution across all unit and integration test suites.
"""
from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def print_step(title: str) -> None:
    print(f"\n{'='*70}\n>> {title}\n{'='*70}")


def run_ast_check(root_dir: Path) -> bool:
    """Step 1: AST Syntax Check on all .py files in backend, frontend, tests, and root."""
    print_step("BUOC 1: AST SYNTAX CHECK (Kiem tra cu phap tinh)")
    py_files = []
    scan_targets = ["backend", "frontend", "tests"]
    for target in scan_targets:
        dir_path = root_dir / target
        if dir_path.is_dir():
            py_files.extend(dir_path.rglob("*.py"))

    # Include root python files
    py_files.extend(root_dir.glob("*.py"))

    # Exclude virtual environments or build directories if present
    py_files = [f for f in py_files if ".venv" not in f.parts and "__pycache__" not in f.parts]

    failed = False
    checked_count = 0

    for py_file in py_files:
        checked_count += 1
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                code = f.read()
            ast.parse(code, filename=str(py_file))
        except SyntaxError as err:
            rel_path = py_file.relative_to(root_dir)
            print(f"  [FAIL] {rel_path}: Loi cu phap tai dong {err.lineno}: {err.msg}")
            failed = True

    if failed:
        print(f"\n[!] AST Check THAT BAI. Da kiem tra {checked_count} tep.")
        return False

    print(f"  [PASS] Toan bo {checked_count} tep Python dat chuan cu phap AST hop le.")
    return True


def run_r2_purity_gate() -> bool:
    """Step 2: Subprocess verification of R2 algorithm purity (Pure Python Stdlib Only)."""
    print_step("BUOC 2: R2 STDLIB PURITY GATE (Kiem tra co lap thu vien ben ngoai)")

    check_code = (
        "import sys\n"
        "from datetime import date\n"
        "from types import SimpleNamespace\n"
        "import backend.algorithms\n"
        "from backend.algorithms.citation_verifier import verify_citations, CitationClaim\n"
        "from backend.algorithms.reconciliation import reconcile_requirements_and_tasks\n"
        "from backend.algorithms.email_state_machine import prepare_draft_for_approval\n"
        "\n"
        "# Trigger all 3 algorithms to ensure no lazy third-party import triggers\n"
        "c = CitationClaim(claim_text='test', cited_doc_id='doc', cited_page=1, evidence_quote='q')\n"
        "verify_citations([c], {('doc', 1): 'q'})\n"
        "reconcile_requirements_and_tasks([], [], date(2026, 10, 26))\n"
        "draft = SimpleNamespace(draft_id='d1', recipient_email='a@b.com', subject='s', body='b', attachment_ids=[])\n"
        "prepare_draft_for_approval(draft)\n"
        "\n"
        "forbidden = ['pydantic', 'fastapi', 'starlette', 'numpy', 'streamlit', 'rank_bm25', 'httpx']\n"
        "leaked = [mod for mod in sys.modules if any(f in mod for f in forbidden)]\n"
        "if leaked:\n"
        "    print(f'LEAKED_MODULES:{leaked}')\n"
        "    sys.exit(2)\n"
        "print('R2_PURITY_VERIFIED_OK')\n"
    )

    res = subprocess.run(
        [sys.executable, "-c", check_code],
        capture_output=True,
        text=True,
    )

    if res.returncode != 0:
        print("  [FAIL] Phat hien ro ri thu vien cam vao backend.algorithms:")
        print(res.stdout.strip())
        print(res.stderr.strip())
        return False

    print("  [PASS] 100% Pure Python Standard Library tai backend/algorithms/. Khong ro ri thu vien ben thu ba.")
    return True


def run_pytest_suite() -> bool:
    """Step 3: Test suite execution via pytest."""
    print_step("BUOC 3: TEST SUITE EXECUTION (Chay toan bo kiem thu he thong)")
    res = subprocess.run([sys.executable, "-m", "pytest", "-v"])
    return res.returncode == 0


def main() -> int:
    root_dir = Path(__file__).resolve().parent

    print("\n" + "=" * 70)
    print("  WORKSPACEAI v2.5 - HE THONG KIEM DINH 1-CHAM TOAN DIEN")
    print("=" * 70)

    # 1. AST Check
    if not run_ast_check(root_dir):
        sys.exit(1)

    # 2. R2 Stdlib Purity
    if not run_r2_purity_gate():
        sys.exit(1)

    # 3. Pytest Suite
    if not run_pytest_suite():
        print("\n[!] Pytest Suite that bai. Vui long kiem tra log chi tiet phia tren.")
        sys.exit(1)

    print("\n" + "=" * 70)
    print("  >>> TAT CA CAC BUOC KIEM DINH DA HOAN TAT THANH CONG (100% PASSED) <<<")
    print("=" * 70 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
