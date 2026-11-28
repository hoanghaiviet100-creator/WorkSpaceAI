# CPU embedding and safe index rebuild

The active local profile uses FastEmbed 0.9.1, ONNX Runtime 1.32.0 and Qwen/Qwen3-Embedding-0.6B-Q on CPU. Ollama runs only Qwen2.5 7B generation on GPU. Encoder artifacts, tokenizer, prefixes, last-token pooling, L2 output policy and execution versions are pinned in legal/CPU-ENCODER.json. The old Ollama vectors are never read by the new encoder namespace.

Latest targeted campaign: 23/25 API and 11/12 actual browser acceptance; release remains NOT qualified. See validation/final-bugfix-release-20261127/FINAL-REPORT.md. The prior 25/25 API, 10/12 browser and 3/3 model-cold startup results remain preserved under validation/release-qualification-20261127; the historical 24/25 cold-load failure is also retained. Encoder, index and standalone configuration are unchanged.

## Environment

The isolated `.venv-pa2` now contains all pinned application dependencies locally. The shared `workspace-dependencies.pth` was removed and preserved in qualification evidence; system-site package inheritance is disabled. Isolated-mode imports and offline bitwise vector compatibility were verified. Setup uses requirements-standalone.lock without modifying D:\WorkSpaceAI or downloading duplicate models.

```powershell
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File .\Setup-Standalone.ps1
rtk proxy powershell -NoProfile -ExecutionPolicy Bypass -File .\Start-SessionB.ps1
```

The application opens while one guarded generation preload runs. The model-load deadline is 180 seconds; ordinary warm generation remains 90 seconds. Successful preparation verifies actual model/digest/context/GPU residency. The configured model is pinned while services run and monitored for idle memory reserves; lost residency or unsafe resources produce a natural recovery message without automatic reload. Use Stop-SessionB.ps1 -StopModels to release the complete owned service.

CPU inference remains offline, two threads and batch one. The existing 120-second reply bound now also bounds the total embedding batch. Oversized inputs fail rather than truncate. The upload-only browser deadline is 150 seconds, allowing bounded ingestion to return; other endpoint deadlines are unchanged. Ingestion runs off the API event loop. All admission and reserve thresholds remain unchanged.

## Existing documents

Old snapshots stay at `.runtime-app/library.json` and `.runtime-validation/library.json`. New snapshots are below `indexes/cpu-onnx-v1-<identity hash>/library.json` within the corresponding runtime directory. They do not share vectors, even though old and new encoder dimensions are both 1024.

For an old library, rebuild from the exact original PDFs/TXT/MD files. Stop the task-owned app before rebuilding; do not run inference concurrently. Choose a directory containing the original source files, or the new hash-named immutable originals archive. The command verifies every document's original SHA-256 before encoding. Missing originals, changed bytes, unsupported structured CSV migration, existing destination indexes or encoding failure stop publication. The old index stays untouched. Cached extracted chunks are not substituted for original files.

```powershell
$env:PYTHON_DOTENV_DISABLED='1'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:F1_SESSION_B='true'
$env:F1_EMBEDDING_BACKEND='fastembed_cpu'
$env:F1_CPU_ENCODER='D:\WorkspaceAI-F1-V2\.runtime\cpu-embedding\qwen3-0.6b-int8\encoder.json'
$env:F1_RUNTIME_DIR='D:\WorkspaceAI-F1-V2\.runtime-app'
rtk proxy .\.venv-pa2\Scripts\python.exe -B tools\rebuild_cpu_index.py --source .runtime-app\library.json --originals 'D:\YourOriginalDocuments' --destination .runtime-app\library.json
```

The destination base name may equal the old base name: the tool resolves the CPU encoder's versioned namespace, rejects an existing target, then publishes atomically only after every original document succeeds. Its returned path and index identity are reviewable. Start the app with Start-SessionB.ps1 to open that namespace. If original files are unavailable, re-upload originals through the new library; do not convert old vectors or relabel their namespace. Each successful upload retains immutable original bytes by content hash for future rebuilds.

The tests verify encoder/file/version identity, changed-output-policy isolation, old snapshot preservation, missing-original rejection, atomic target refusal, source scope and citation provenance. A live rebuild of every unrelated user library was not performed. The acceptance corpus was rebuilt from actual original uploads.

## Reproduce checks

```powershell
rtk proxy .\.venv-pa2\Scripts\python.exe -B tools\offline_pytest.py -q tests/test_cpu_embeddings.py tests/test_f1_session_b.py tests/test_f1_adaptive_memory.py tests/test_startup_embedding_isolation.py -p no:cacheprovider
```

The consolidated qualification evidence is saved under validation/release-qualification-20261127. Do not repeat it to replace failures. Any future human-directed campaign must retain the historical timeout and the two current browser citation blockers. Balanced RRF remains 0.50/0.50 after the limited independent comparison; no general optimum is claimed.
