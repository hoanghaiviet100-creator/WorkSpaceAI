import io
import json

from pypdf import PdfWriter

from backend.algorithms.feature1.outline_builder import build_outline, map_packets
from backend.core.config import settings
from backend.core.schemas import DocumentChunk, DocumentHeading
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.feature1 import document_summary
from backend.services.feature1.qa_service import QAService


def chunks(*pages: str, file_hash: str = "a") -> list[DocumentChunk]:
    return [
        DocumentChunk(
            chunk_id=str(page),
            doc_id="guide.pdf",
            doc_name="guide.pdf",
            doc_hash=file_hash,
            page_number=page,
            end_line=len(text.splitlines()),
            text=text,
        )
        for page, text in enumerate(pages, 1)
    ]


def test_outline_prefers_bookmarks_and_tracks_subsections_and_pages():
    source = chunks(
        "Overview\nContext",
        "Main body\nSetup\nRun git config.",
        "Continue here.",
        "Glossary\nBranch definition.",
    )
    hints = [
        DocumentHeading(title="Main body", page=2, origin="bookmark"),
        DocumentHeading(title="Setup", page=2, level=2, origin="bookmark"),
        DocumentHeading(title="Appendix A — Glossary", page=4, origin="bookmark"),
    ]
    intro, main, setup, appendix = build_outline(source, hints)
    assert intro.title == "Giới thiệu"
    assert (main.start_page, main.end_page) == (2, 3)
    assert setup.parent_id == main.id and "Continue here." in setup.content
    assert appendix.kind == "appendix" and appendix.start_page == 4


def test_pdf_parser_extracts_actual_bookmark_page():
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.add_blank_page(200, 200)
    writer.add_outline_item("Chapter 1: Setup", 1)
    data = io.BytesIO()
    writer.write(data)
    hints: list[DocumentHeading] = []
    try:
        DocumentService().parse_pdf_pages(
            "outline.pdf", data.getvalue(), headings=hints
        )
    except ValueError:
        pass
    assert [(hint.title, hint.page, hint.origin) for hint in hints] == [
        ("Chapter 1: Setup", 2, "bookmark")
    ]


def test_outline_reads_body_titles_without_bookmarks_and_preserves_examples():
    outline = build_outline(
        chunks(
            "Contents\n1. Setup ........ 2\n2. Example ........ 4",
            "1. Setup\n1.1 Install Git\nUse the package manager.\n\n$ git --version\nGit version 2.",
            "Now configure your email address.",
            "2. Example\nStage before committing.\nAppendix A — Reference\nA command table.",
        )
    )
    roots = [item for item in outline if item.counts_for_coverage]
    assert [item.title for item in roots] == [
        "1. Setup",
        "2. Example",
        "Appendix A — Reference",
    ]
    assert roots[0].end_page == 3 and roots[-1].kind == "appendix"
    packets = map_packets(roots[0], budget=45)
    assert any(
        "Use the package manager.\n\n$ git --version" in block.text
        for packet in packets
        for block in packet
    )


def test_numbered_subsections_survive_shortened_bookmark_titles():
    source = chunks(
        "Chapter 1\nIntroduction\nBackground.",
        "Chapter 2\nSystem Requirements\n2.1 Functional Requirements and Computational Thinking\n"
        "2.1.1 Feature 1 - Learning Assistant\nMatches answers with document excerpts.",
    )
    hints = [
        DocumentHeading(title="Introduction", page=1, origin="bookmark"),
        DocumentHeading(title="System Requirements", page=2, origin="bookmark"),
        DocumentHeading(title="Functional Requirements and CT Analysis", page=2, level=2, origin="bookmark"),
    ]
    outline = build_outline(source, hints)
    requirements, functional, feature = outline[-3:]
    assert functional.title == "2.1 Functional Requirements and Computational Thinking"
    assert functional.parent_id == requirements.id and feature.parent_id == functional.id


def test_outline_uses_font_then_overlapping_page_ranges():
    source = chunks(
        "Read this first.",
        "Setup instructions\nInstall Git.",
        "Git Workflow\nAdd and commit.",
        "Final notes.",
    )
    fonts = [DocumentHeading(title="Git Workflow", page=3, origin="font")]
    assert build_outline(source, fonts)[-1].title == "Git Workflow"
    first, second = build_outline(source)
    assert (first.start_page, first.end_page, second.start_page, second.end_page) == (
        1,
        3,
        3,
        4,
    )


def test_chapter_bookmarks_override_numbered_exercises_and_keep_numbered_titles():
    source = chunks(
        "Mục lục\n1 Hàm nhiều biến 2\n1.1 Miền xác định ........ 2\n2 Vi phân 4",
        "2 Miền xác định\nChương 1\nHàm nhiều biến\n1.1 Miền xác định\nXét miền xác định của hàm nhiều biến.",
        "1. lim\n2. f.x; y/D y\n40. cos t, 0\x14\x19=4",
        "Chương 2\nVi phân\nXét sự biến thiên theo một biến.",
    )
    hints = [
        DocumentHeading(title="Hàm nhiều biến", page=2, origin="bookmark"),
        DocumentHeading(title="Miền xác định", page=2, level=2, origin="bookmark"),
        DocumentHeading(title="Vi phân", page=4, origin="bookmark"),
    ]
    outline = build_outline(source, hints)
    first, second = [item for item in outline if item.counts_for_coverage]
    assert (first.title, first.end_page, second.title) == ("1. Hàm nhiều biến", 3, "2. Vi phân")
    children = [item for item in outline if item.parent_id == first.id]
    assert [item.title for item in children] == ["1.1 Miền xác định"]
    assert children[0].blocks[0].start_line == 4
    packets = map_packets(first)
    assert all("f.x; y/D" not in part.text and "\x19" not in part.text for packet in packets for part in packet)


def test_lists_and_fenced_examples_do_not_become_chapters_in_unstructured_source():
    outline = build_outline(chunks(
        "Checklist:\n1. Request access\n2. Confirm the details\n3. Send the form",
        "```markdown\n# Temporary heading\n```\nThe remainder is ordinary text.",
    ))
    assert len(outline) == 1 and outline[0].kind == "page_range"
    assert outline[0].start_page == 1 and outline[0].end_page == 2


def test_markdown_headings_are_structural_only_in_markdown_sources():
    source = chunks("# Access policy\nApproval is required.\n```\n# Example command comment\n```\n## Exceptions")
    assert build_outline(source)[0].kind == "page_range"
    markdown = [chunk.model_copy(update={"doc_name": "policy.md"}) for chunk in source]
    assert [(section.title, section.level) for section in build_outline(markdown)] == [
        ("Access policy", 1), ("Exceptions", 2),
    ]


def test_brief_summary_uses_one_note_per_chapter_and_separate_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    source = chunks(
        "1. Setup\nRun git init.",
        "2. Workflow\nUse git add before commit.",
    )
    repo = WorkspaceRepository()
    repo.chunks = source
    provider = FakeModel()
    lookup = repo.build_page_lookup()
    result = document_summary.summarize_long_document(source, [], lookup, provider, tmp_path, brief=True)
    assert result["coverage"]["explained_sections"] == 2
    assert len(result["validated_claims"]) == 2
    assert provider.reduce_calls == 0
    assert document_summary.summarize_long_document(source, [], lookup, provider, tmp_path, brief=True)["summary_cache_hit"]
    result = document_summary.summarize_long_document(source, [], lookup, provider, tmp_path)
    assert not result["summary_cache_hit"] and provider.reduce_calls == 1


def test_summary_caches_only_semantically_supported_map_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "offline_only", False)
    monkeypatch.setattr(settings, "feature1_semantic_verify", True)
    source = chunks("1. Setup\nRun git init.", "2. Workflow\nStage files first.")
    repo = WorkspaceRepository()
    repo.chunks = source

    class ReviewingModel(FakeModel):
        def judge_claim_support(self, pairs):
            return {key: "SUPPORTED" if "git init" in pair["evidence"] else "CONTRADICTED"
                    for key, pair in pairs.items()}

    provider = ReviewingModel()
    result = document_summary.summarize_long_document(
        source, [], repo.build_page_lookup(), provider, tmp_path, brief=True,
    )
    assert result["coverage"]["missing_sections"] == ["2. Workflow"]
    assert [claim.semantic_status for claim in result["validated_claims"]] == ["SUPPORTED"]
    cache = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert len(cache["notes"]) == 1


class FakeModel:
    def __init__(self, *, omit_initial_notes: bool = True) -> None:
        self.map_calls: list[list[str]] = []
        self.omit_initial_notes = omit_initial_notes
        self.reduce_calls = 0

    def get_effective_ollama_model(self) -> str:
        return "local-test"

    def generate_summary_stage(
        self,
        prompt: str,
        *,
        stage: str,
        engine: str,
        model: str,
        sources: dict | None = None,
    ) -> dict:
        source = json.loads(
            prompt.split("<untrusted_document_data>\n")[1].split(
                "\n</untrusted_document_data>"
            )[0]
        )
        if stage == "reduce":
            self.reduce_calls += 1
            return {
                "overview": [
                    {
                        "claim": "Hướng dẫn thiết lập và tạo commit.",
                        "source": source[0]["source"],
                    }
                ],
                "groups": [
                    {
                        "title": "Quy trình Git",
                        "chapters": [item["chapter"] for item in source],
                    }
                ],
            }
        ids = [task["id"] for task in source]
        self.map_calls.append(ids)
        return {
            "notes": {
                item["id"]: {
                    "purpose": "Thao tác trong " + item["section"],
                    "actions": item["passages"][0].splitlines()[-1],
                    "source": 1,
                }
                for index, item in enumerate(source)
                if not self.omit_initial_notes or len(self.map_calls) > 1 or index == 0
            }
        }


def test_numbered_questions_resolve_selected_chapter_and_never_retrieve_other_pages(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "offline_only", False)
    source = chunks(
        "1. Why Version Control?\nGit stores project snapshots.",
        "2. Installing Git\nRun git --version to verify installation.",
        "3. Exercises\n1. Python Bootcamp",
    )
    repo = WorkspaceRepository()
    repo.chunks = source
    model = FakeModel()
    qa = QAService(repo, model)
    qa.summary_cache_dir = tmp_path
    doc_ids = ["guide.pdf"]

    cold = qa.answer_question("Chương 2 đang nói về gì?", selected_doc_ids=doc_ids)
    assert cold["status"] == "ANSWER_VERIFIED"
    assert len(model.map_calls) == 1
    assert {claim.cited_page for claim in cold["validated_claims"]} == {2}

    document_summary.summarize_long_document(source, [], repo.build_page_lookup(), model, tmp_path)
    calls = len(model.map_calls)
    for query in ("mục 1 đang nói về gì", "Chương 1 đang nói về gì"):
        answer = qa.answer_question(query, selected_doc_ids=doc_ids)
        assert answer["status"] == "ANSWER_VERIFIED"
        assert {claim.cited_page for claim in answer["validated_claims"]} == {1}
        assert all("Python" not in claim.claim_text for claim in answer["validated_claims"])
    assert len(model.map_calls) == calls
    missing = qa.answer_question("Chương 20 đang nói về gì", selected_doc_ids=doc_ids)
    excluded = qa.answer_question("Chương 1 đang nói về gì", selected_doc_ids=["other.pdf"])
    assert missing["status"] == excluded["status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"


def test_compound_chapter_question_explains_each_subsection_and_keeps_citations(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "offline_only", False)
    monkeypatch.setattr(settings, "feature1_semantic_verify", False)
    source = chunks(
        "1. Networking\n1.1 UDP\nUDP sends datagrams.\n0\x14\x19=4",
        "1.2 TCP\nTCP provides an ordered stream of bytes.",
        "2. Storage\nThis chapter discusses SSDs.",
    )
    repo = WorkspaceRepository()
    repo.chunks = source
    model = FakeModel()
    qa = QAService(repo, model)
    result = qa.answer_question(
        "Chương 1 nói về gì? Hãy giải thích theo các tiểu mục trong chương",
        selected_doc_ids=["guide.pdf"],
    )
    assert result["status"] == "ANSWER_VERIFIED"
    items = result["validated_claims"]
    assert [item.subsection for item in items] == ["1.1 UDP", "1.2 TCP"]
    assert [item.cited_page for item in items] == [1, 2]
    assert "UDP sends datagrams." in items[0].claim_text
    assert items[1].claim_text == "Trích đoạn: TCP provides an ordered stream of bytes."
    assert len(model.map_calls) == 1


def test_detailed_chapter_question_covers_subsections_and_later_pages(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "offline_only", False)
    monkeypatch.setattr(settings, "feature1_semantic_verify", False)
    repo = WorkspaceRepository()
    repo.chunks = chunks(
        "Chapter 8: Networking\n8.1 Setup\nCreate a remote.",
        "8.2 Sync and release\nFetch before merging.",
        "The instructor inspects the state of the repository at each milestone tag.",
        "Chapter 9: Storage\nThis chapter discusses SSDs.",
    )
    model = FakeModel(omit_initial_notes=False)
    service = QAService(repo, model)
    for query in (
        "Hãy nêu chi tiết những gì trong chương 8",
        "Mô tả chi tiết nội dung của Chương 8.",
        "Giải thích chương 8 chi tiết",
    ):
        result = service.answer_question(query, selected_doc_ids=["guide.pdf"])
        assert result["status"] == "ANSWER_VERIFIED"
        claims = result["validated_claims"]
        assert [claim.subsection for claim in claims] == ["8.1 Setup", "8.2 Sync and release", "8.2 Sync and release"]
        assert [claim.cited_page for claim in claims] == [1, 2, 3]
        assert any("milestone tag" in claim.claim_text for claim in claims)


def test_detailed_chapter_preserves_procedure_commands_and_source_caveat(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "offline_only", False)
    repo = WorkspaceRepository()
    repo.chunks = chunks(
        "Chapter 8: Networking\n8.1 Update\n"
        "$ git switch feature $ git fetch origin $ git merge origin/main # or: git rebase origin/main (your own branch only)"
        "\nRun tests before publishing changes.\n"
        "$ git remote -v origin | https://example.test/team/repo (fetch)\n"
        "Tag\nMilestone\nv1.0\nReleased"
    )
    model = FakeModel()
    result = QAService(repo, model).answer_question(
        "Hãy nêu chi tiết những gì trong chương 8", selected_doc_ids=["guide.pdf"],
    )
    claim = result["validated_claims"][0]
    assert claim.subsection == "8.1 Update"
    assert claim.verification_status == "VERIFIED_EXACT"
    assert "`git switch feature` → `git fetch origin`" in claim.claim_text
    assert "your own branch only" in claim.claim_text
    assert "Run tests before publishing changes." in claim.claim_text
    assert "`git remote -v` → `origin |" in claim.claim_text
    assert "`v1.0` — Released." in claim.claim_text
    assert not model.map_calls


def test_coverage_retries_only_missing_and_cache_invalidates(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    source = chunks(
        "1. Setup\nRun git init.",
        "2. Git Workflow\nUse git add, then commit.",
        "Appendix A — FAQ\nRun git status.",
    )
    model = FakeModel()

    def summarize():
        repo = WorkspaceRepository()
        repo.chunks = source
        return document_summary.summarize_long_document(
            source, [], repo.build_page_lookup(), model, tmp_path
        )

    first = summarize()
    initial, retry = model.map_calls
    assert retry == initial[1:]
    assert (
        first["coverage"]["explained_sections"]
        == first["coverage"]["total_sections"]
        == 3
    )
    assert first["coverage"]["missing_sections"] == []
    assert all("Hướng dẫn thiết lập và tạo commit." != claim.claim_text for claim in first["validated_claims"])
    assert [claim.subsection for claim in first["validated_claims"]] == [
        "1. Setup",
        "2. Git Workflow",
        "Appendix A — FAQ",
    ]
    assert not first["summary_cache_hit"]
    assert summarize()["summary_cache_hit"]
    assert len(model.map_calls) == 2 and model.reduce_calls == 1
    source = [chunk.model_copy(update={"doc_hash": "new-file"}) for chunk in source]
    assert not summarize()["summary_cache_hit"]
    monkeypatch.setattr(document_summary, "ALGO_VERSION", "next")
    assert not summarize()["summary_cache_hit"]
    assert len(model.map_calls) == 4 and model.reduce_calls == 3


def test_summary_cache_hit_does_not_wait_for_same_file_in_another_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    source = chunks("1. Setup\nRun git init.")
    repo = WorkspaceRepository()
    repo.chunks = source
    lookup = repo.build_page_lookup()
    model = FakeModel()
    workspace_a = tmp_path / "a"
    key = document_summary.summary_cache_key(source[0].doc_hash, "ollama", "local-test")
    assert not document_summary.summarize_long_document(source, [], lookup, model, workspace_a)["summary_cache_hit"]
    calls = len(model.map_calls), model.reduce_calls

    path_a = workspace_a / f"{key}.json"
    path_b = tmp_path / "b" / path_a.name
    lock_a = document_summary._cache_lock(path_a)
    assert lock_a is document_summary._cache_lock(path_a)
    lock_b = document_summary._cache_lock(path_b)
    assert lock_a is not lock_b
    with lock_b:
        result = document_summary.summarize_long_document(source, [], lookup, model, workspace_a)
    assert result["summary_cache_hit"]
    assert (len(model.map_calls), model.reduce_calls) == calls


def test_large_outline_gets_all_chapters_first_and_reuses_partial_details(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    source = chunks(
        *(f"{number}. Section {number}\nRun git status." for number in range(1, 10)),
        "Appendix A — FAQ\nUse git help.",
    )

    class CoverageOnly(FakeModel):
        def generate_summary_stage(
            self,
            prompt: str,
            *,
            stage: str,
            engine: str,
            model: str,
            sources: dict | None = None,
        ) -> dict:
            output = super().generate_summary_stage(
                prompt, stage=stage, engine=engine, model=model
            )
            if stage == "map":
                output["notes"] = {
                    key: row
                    for key, row in output["notes"].items()
                    if key.endswith(":overview")
                }
            return output

    provider = CoverageOnly()
    repo = WorkspaceRepository()
    repo.chunks = source
    first = document_summary.summarize_long_document(
        source, [], repo.build_page_lookup(), provider, tmp_path
    )
    calls = list(provider.map_calls)
    assert first["coverage"]["explained_sections"] == 10
    assert first["coverage"]["partial_sections"]
    assert first["coverage"]["complete_sections"] == 0
    assert first["message"].startswith("Đã tổng hợp đầy đủ 0/10 mục.")
    assert all(task.endswith(":overview") for task in calls[0])

    repeated = document_summary.summarize_long_document(
        source, [], repo.build_page_lookup(), provider, tmp_path
    )
    assert (
        repeated["summary_cache_hit"]
        and provider.map_calls == calls
        and provider.reduce_calls == 1
    )


def test_partial_cache_resumes_only_the_missing_chapter(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    source = chunks(
        *(f"{number}. Section {number}\nRun git status." for number in range(1, 10)),
        "Appendix A — FAQ\nUse git help.",
    )

    class IntermittentModel(FakeModel):
        recovering = False

        def generate_summary_stage(
            self,
            prompt: str,
            *,
            stage: str,
            engine: str,
            model: str,
            sources: dict | None = None,
        ) -> dict:
            output = super().generate_summary_stage(
                prompt, stage=stage, engine=engine, model=model
            )
            if stage == "map" and not self.recovering:
                output["notes"] = {
                    key: row
                    for key, row in output["notes"].items()
                    if key.endswith(":overview") and not key.startswith("s10:")
                }
            return output

    provider = IntermittentModel()
    repo = WorkspaceRepository()
    repo.chunks = source
    lookup = repo.build_page_lookup()
    cold = document_summary.summarize_long_document(
        source, [], lookup, provider, tmp_path
    )
    assert cold["coverage"]["missing_sections"] == ["Appendix A — FAQ"]
    previous_calls = len(provider.map_calls)
    provider.recovering = True
    repeat = document_summary.summarize_long_document(
        source, [], lookup, provider, tmp_path
    )
    assert not repeat["coverage"]["missing_sections"]
    assert {
        task.split(":")[0]
        for batch in provider.map_calls[previous_calls:]
        for task in batch
    } == {"s10"}
    assert document_summary.summarize_long_document(
        source, [], lookup, provider, tmp_path
    )["summary_cache_hit"]


def test_summary_retries_missing_details_after_chapter_already_has_notes(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "feature1_semantic_verify", False)
    monkeypatch.setattr(document_summary, "MAP_BUDGET", 110)
    monkeypatch.setattr(document_summary, "LONG_DOCUMENT_CHARS", 1)
    source = chunks(
        "Chapter 1\nRequirements\n1.1 Sources\n" + "The learner chooses source documents. " * 3,
        "1.2 Evidence\n" + "An answer links to exact evidence in the selected document. " * 2,
        "Chapter 2\nReferences\nThe appendix lists the cited studies.",
    )
    outline = build_outline(source)
    task = next(task for task in document_summary._map_tasks(outline) if task.title == "1.2 Evidence")

    class PartialModel(FakeModel):
        provides_evidence = False

        def generate_summary_stage(self, prompt, *, stage, engine, model, sources=None):
            data = super().generate_summary_stage(prompt, stage=stage, engine=engine, model=model, sources=sources)
            if stage == "map" and task.id in data["notes"] and not self.provides_evidence:
                data["notes"][task.id]["actions"] = "Xem mục lục để biết chi tiết."
            return data

    provider = PartialModel(omit_initial_notes=False)
    repository = WorkspaceRepository()
    repository.chunks = source
    lookup = repository.build_page_lookup()
    first = document_summary.summarize_long_document(source, [], lookup, provider, tmp_path)
    assert first["coverage"]["explained_sections"] == 2
    assert first["coverage"]["complete_sections"] == 1
    assert first["coverage"]["partial_sections"] == ["1. Requirements"]
    assert "Xem mục lục" not in first["summary"]
    previous = len(provider.map_calls)
    provider.provides_evidence = True

    second = document_summary.summarize_long_document(source, [], lookup, provider, tmp_path)
    assert provider.map_calls[previous:] == [[task.id]]
    assert second["coverage"]["complete_sections"] == 2
    assert second["coverage"]["partial_sections"] == []
