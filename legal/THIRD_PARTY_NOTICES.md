# Third-party notices

SurfSense — Copyright (c) SurfSense. Apache License 2.0. Reused open-source paths are pinned to b764f2838969974fd1b0e8c386326039a0f3ad3a. No proprietary plugin code is imported. The full license is in SurfSense-LICENSE; SURFSENSE-REUSE.json lists exact source paths and hashes. No applicable upstream NOTICE was present in this source tree.

The CPU embedder directly reuses the open-source embedding spec and last-token pooling implementation, adapted only for local imports. FastEmbed 0.9.1 supplies tokenizer loading and ONNX inference. Its Apache-2.0 license and upstream NOTICE are retained under dependencies/fastembed. That package's NOTICE mentions other optional model families; those models are not downloaded or used here.

The selected encoder is Qwen/Qwen3-Embedding-0.6B-Q from Qdrant/Qwen3-Embedding-0.6B-onnx, revision af95f2c416ffe9379369ad64f9113e865db6112c, declared Apache-2.0. CPU-ENCODER.json pins all artifact hashes, tokenizer, prefixes and execution versions. This is a different vector identity from the previous Ollama GGUF artifact even though the base model and dimension agree.

ONNX Runtime's MIT license and third-party notices, tokenizers' Apache-2.0 license, and NumPy's BSD and bundled dependency licenses remain in the installed distributions and are copied under dependencies with package-relative paths. DEPENDENCY-LICENSES.json identifies each copied notice and its hash. Existing application dependencies remain governed by their own included licenses.

IN-FILE-NOTICES.md reports only the exact modification notices retained under Apache-2.0 section 4(b), with file/line and relocation constraints. Applicable source notices are preserved under 4(c); the dependency NOTICE is preserved under 4(d). No individual contribution assignment or AI-agent credit is added.
