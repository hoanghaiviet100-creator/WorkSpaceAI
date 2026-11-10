import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.repositories.local_library_store import LocalLibraryStore
from backend.repositories.workspace_repository import WorkspaceRepository
from backend.services.document_service import DocumentService
from backend.services import workspace_context


def service(path):
    return DocumentService(WorkspaceRepository(), library_path=path)


def test_restart_restores_documents_selection_and_searchable_evidence(tmp_path):
    path = tmp_path / "workspace.json"
    initial = service(path)
    initial.ingest_file("notes.md", b"Socket programming uses TCP for reliable delivery.\nKeep the evidence line.")
    initial.ingest_file("other.txt", b"Other project notes.")
    initial.set_selected_documents(["notes.md"])
    metadata = initial.list_documents()
    chunks = [chunk.model_dump() for chunk in initial.repository.chunks]

    restarted = service(path)
    assert restarted.list_documents() == metadata
    assert [chunk.model_dump() for chunk in restarted.repository.chunks] == chunks
    assert restarted.get_selected_doc_ids() == ["notes.md"]
    found = restarted.repository.search("Socket TCP", selected_doc_ids=["notes.md"])
    assert found and all(chunk.doc_id == "notes.md" for chunk in found)
    assert restarted.repository.build_page_lookup()[("notes.md", 1)]["doc_hash"] == metadata[0]["file_hash"]


def test_clear_selection_is_retained_after_restart(tmp_path):
    path = tmp_path / "workspace.json"
    initial = service(path)
    initial.ingest_file("notes.txt", b"Notes available offline.")
    initial.set_selected_documents([])
    restarted = service(path)
    assert restarted.get_selected_doc_ids() == []
    assert restarted.repository.search("Notes", selected_doc_ids=[]) == []


def test_csv_versions_and_duplicate_uploads_survive_restart(tmp_path):
    path = tmp_path / "workspace.json"
    initial = service(path)
    first = b"title,owner\nReview source,Alice\n"
    second = b"title,owner\nReview source,Bob\n"
    initial.ingest_file("tasks.csv", first)
    initial.ingest_file("tasks.csv", second)
    restarted = service(path)
    assert restarted.ingest_file("tasks.csv", first)["status"] == "ALREADY_EXISTS"
    assert [(row["doc_id"], row["version_id"]) for row in restarted.list_documents()] == [
        ("tasks.csv", "v1"), ("tasks.csv_v2", "v2")
    ]
    assert len(restarted.repository.chunks) == 2


def test_deleted_last_file_stays_deleted_in_saved_empty_library(tmp_path):
    path = tmp_path / "workspace.json"
    initial = service(path)
    initial.ingest_file("notes.txt", b"Remove this test document.")
    assert initial.delete_document("notes.txt")
    restarted = service(path)
    assert restarted.list_documents() == []
    assert restarted.repository.chunks == []
    assert LocalLibraryStore(path).restore(WorkspaceRepository()) is True


def test_interrupted_write_preserves_previous_snapshot(tmp_path):
    path = tmp_path / "workspace.json"
    initial = service(path)
    initial.ingest_file("notes.txt", b"Keep the last successfully saved library.")
    saved = path.read_bytes()
    with patch("backend.repositories.local_library_store.os.replace", side_effect=OSError("Disk unavailable")):
        with pytest.raises(OSError):
            initial.set_selected_documents([])
    assert path.read_bytes() == saved
    assert not list(tmp_path.glob("*.tmp"))
    assert service(path).get_selected_doc_ids() == ["notes.txt"]


@pytest.mark.parametrize("content", ["broken json", json.dumps({"version": 999}), json.dumps({
    "version": 1, "documents": [], "chunks": [{"doc_id": "missing"}]
})])
def test_invalid_snapshot_is_not_silently_replaced(tmp_path, content):
    path = tmp_path / "workspace.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises((ValueError, KeyError)):
        service(path)
    assert path.read_text(encoding="utf-8") == content


def test_api_context_recreation_preserves_selection_and_workspace_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(workspace_context, "_library_root", tmp_path)
    monkeypatch.setattr(workspace_context, "_contexts", {})
    client = TestClient(app)
    for workspace_id in ("a", "b"):
        headers = {"X-Workspace-ID": workspace_id}
        response = client.post("/api/documents/upload", headers=headers, files={
            "file": ("notes.txt", f"Private notes in workspace {workspace_id}.".encode(), "text/plain")
        })
        assert response.status_code == 200
    client.post("/api/documents/select", headers={"X-Workspace-ID": "a"}, json={"selected_doc_ids": []})
    workspace_context._contexts.clear()
    a = client.get("/api/documents", headers={"X-Workspace-ID": "a"}).json()
    b = client.get("/api/documents", headers={"X-Workspace-ID": "b"}).json()
    assert len(a) == len(b) == 1
    assert not a[0]["is_selected"] and b[0]["is_selected"]
    assert a[0]["file_hash"] != b[0]["file_hash"]
