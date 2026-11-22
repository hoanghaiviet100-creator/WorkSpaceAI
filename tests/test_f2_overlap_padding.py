"""Real ingestion regression for pipe-margin trimming; genuine conflicts fail."""
import io

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.core.f2_study_schemas import StudySourceSelection
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services.f2_source_service import F2SourceService, SourceAccessContext, SourcePreparationError


TEXT = "\n".join(
    f"| Row {i}: The documented threshold is <= 8 C for item {i} in this source. |"
    for i in range(1, 31)
)


def pdf_bytes(text):
    """A real text-layer PDF in memory, using the already installed pypdf."""
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
        NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
        DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    commands = ["BT /F1 9 Tf 36 755 Td 16 TL"]
    for line in text.splitlines():
        escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        commands.append("(" + escaped + ") Tj T*")
    commands.append("ET")
    stream = DecodedStreamObject()
    stream.set_data("\n".join(commands).encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    result = io.BytesIO()
    writer.write(result)
    return result.getvalue()


def workspace(extension="txt", text=TEXT):
    repo = WorkspaceRepository()
    data = pdf_bytes(text) if extension == "pdf" else text.encode()
    doc = DocumentService(repo).ingest_file("overlap-bars." + extension, data)["document"]
    selection = StudySourceSelection(selected_doc_ids=[doc.doc_id], study_format="quiz")
    context = SourceAccessContext("overlap-test", frozenset({doc.doc_id}))
    return repo, doc, selection, context


def prepare(repo, selection, context):
    return F2SourceService(repo).prepare_sources(selection, context=context)


def overlaps(repo):
    result = []
    for index, a in enumerate(repo.chunks):
        for b in repo.chunks[index + 1:]:
            if a.page_number == b.page_number:
                for line in range(max(a.start_line, b.start_line), min(a.end_line, b.end_line) + 1):
                    result.append((a, b, line))
    return result


@pytest.mark.parametrize("extension", ("txt", "pdf"))
def test_actual_pipe_row_ingestion_no_longer_has_false_overlap_error(extension):
    repo, doc, selection, context = workspace(extension)
    assert len(repo.chunks) > 2
    witnesses = overlaps(repo)
    assert any(a.text.splitlines()[line - a.start_line] != b.text.splitlines()[line - b.start_line]
               for a, b, line in witnesses)
    before = [c.model_dump_json() for c in repo.chunks]
    prepared = prepare(repo, selection, context)
    assert prepared.passages
    inspected = F2SourceService(repo).inspect_sources(selection, context=context)
    assert inspected.documents[0].usable_passage_count == len(prepared.passages)
    assert before == [c.model_dump_json() for c in repo.chunks]
    for passage in prepared.passages:
        ref = passage.source_ref
        chunk = next(c for c in repo.chunks if c.chunk_id == ref.chunk_id)
        assert ref.evidence_quote == "\n".join(chunk.text.splitlines()[ref.start_line - chunk.start_line:ref.end_line - chunk.start_line + 1])
        assert ref.doc_hash == doc.file_hash and ref.verification_status == "UNVERIFIED"


def test_witness_order_and_three_way_tail_overlap_do_not_change_prepared_snapshot():
    repo, _, selection, context = workspace()
    first = prepare(repo, selection, context)
    assert sum(c.start_line <= 30 <= c.end_line for c in repo.chunks) >= 3
    repo.chunks.reverse()
    second = prepare(repo, selection, context)
    assert second == first


@pytest.mark.parametrize("old,new", [
    ("documented", "undocumented"), ("<=", ">="), ("8 C", "9 C"), ("8 C", "8 c"),
    ("threshold is", "threshold  is"), ("| Row", "|  Row"),
])
@pytest.mark.parametrize("extension", ("txt", "pdf"))
def test_real_content_and_internal_spacing_conflicts_still_block_with_locator(extension, old, new):
    repo, doc, selection, context = workspace(extension)
    a, b, line_number = overlaps(repo)[0]
    lines = b.text.splitlines()
    index = line_number - b.start_line
    assert old in lines[index]
    lines[index] = lines[index].replace(old, new, 1)
    b.text = "\n".join(lines)
    with pytest.raises(SourcePreparationError) as error:
        prepare(repo, selection, context)
    assert error.value.code == "SOURCE_INCONSISTENT" and error.value.doc_ids == (doc.doc_id,)
    message = str(error.value)
    assert doc.doc_name in message and "trang 1" in message and f"dòng {line_number}" in message
    assert a.chunk_id in message and b.chunk_id in message


@pytest.mark.parametrize("edge", ("leading", "trailing"))
def test_pipe_padding_differences_away_from_trimmable_chunk_boundary_still_block(edge):
    repo, _, selection, context = workspace()
    a, b = repo.chunks[:2]
    line_number = a.end_line if edge == "leading" else b.start_line
    assert line_number != b.start_line if edge == "leading" else line_number != b.end_line
    lines = b.text.splitlines()
    index = line_number - b.start_line
    lines[index] = lines[index].lstrip(" ") if edge == "leading" else lines[index].rstrip(" ")
    b.text = "\n".join(lines)
    with pytest.raises(SourcePreparationError) as error:
        prepare(repo, selection, context)
    assert error.value.code == "SOURCE_INCONSISTENT"


def test_non_pipe_code_indentation_is_not_normalized_even_at_boundary():
    text = "\n".join(f"Item {i}: A documented source sentence with enough text to create overlapping chunks." for i in range(30))
    repo, _, selection, context = workspace(text=text)
    _, b, line_number = overlaps(repo)[0]
    lines = b.text.splitlines()
    lines[line_number - b.start_line] = "    " + lines[line_number - b.start_line]
    b.text = "\n".join(lines)
    with pytest.raises(SourcePreparationError):
        prepare(repo, selection, context)


def test_different_documents_with_same_page_and_line_numbers_remain_isolated():
    repo, first, _, _ = workspace()
    second = DocumentService(repo).ingest_file("another.txt", TEXT.replace("8 C", "5 C").encode())["document"]
    ids = (first.doc_id, second.doc_id)
    prepared = prepare(repo, StudySourceSelection(selected_doc_ids=ids, study_format="quiz"),
        SourceAccessContext("overlap-test", frozenset(ids)))
    assert {p.source_ref.doc_id for p in prepared.passages} == set(ids)
