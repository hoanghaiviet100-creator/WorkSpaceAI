from uuid import uuid4
from fastapi.testclient import TestClient
from backend.main import app
from backend.services.workspace_context import get_workspace_services


def namespace():
    return {"X-Workspace-ID": str(uuid4())}


def upload(client, headers, name, content):
    response = client.post("/api/documents/upload", headers=headers, files={"file": (name, content.encode("utf-8"), "text/plain")})
    assert response.status_code == 200, response.text
    return response.json()["document"]["doc_id"]


def test_new_workspace_starts_with_its_own_empty_library():
    client = TestClient(app)
    assert client.get("/api/documents", headers=namespace()).json() == []
    assert get_workspace_services(None) is get_workspace_services("midterm")


def test_same_filename_and_deduplication_are_isolated_between_workspaces():
    client = TestClient(app)
    a, b = namespace(), namespace()
    upload(client, a, "notes.txt", "Alpha workspace: verification code ALPHA-6194.")
    assert client.get("/api/documents", headers=b).json() == []
    upload(client, b, "notes.txt", "Beta workspace: verification code BETA-6194.")
    docs_a = client.get("/api/documents", headers=a).json()
    docs_b = client.get("/api/documents", headers=b).json()
    assert len(docs_a) == len(docs_b) == 1
    assert docs_a[0]["file_hash"] != docs_b[0]["file_hash"]
    assert docs_a[0]["version_id"] == docs_b[0]["version_id"] == "v1"


def test_select_all_and_single_selection_do_not_change_another_workspace():
    client = TestClient(app)
    a, b = namespace(), namespace()
    for scope in (a, b):
        upload(client, scope, "first.txt", "First document for checkbox selection.")
        upload(client, scope, "second.txt", "Second document for checkbox selection.")
    response = client.post("/api/documents/select", headers=a, json={"selected_doc_ids": ["second.txt"]})
    assert response.status_code == 200
    assert {d["doc_id"] for d in client.get("/api/documents", headers=a).json() if d["is_selected"]} == {"second.txt"}
    assert all(d["is_selected"] for d in client.get("/api/documents", headers=b).json())
    client.post("/api/documents/select", headers=a, json={"selected_doc_ids": []})
    assert not any(d["is_selected"] for d in client.get("/api/documents", headers=a).json())


def test_question_cannot_retrieve_a_document_from_another_workspace():
    client = TestClient(app)
    a, b = namespace(), namespace()
    upload(client, a, "private-a.txt", "Workspace Alpha verification code is ALPHA-6194.")
    upload(client, b, "public-b.txt", "Workspace Beta is about network sockets.")
    response = client.post("/api/chat", headers=b, json={"query": "What is the verification code in private-a.txt?", "selected_doc_ids": ["private-a.txt"], "reference_date": "2026-11-06"})
    assert response.status_code == 200
    assert response.json()["status"].startswith("ABSTAINED")
    assert not response.json()["validated_claims"]
    assert "ALPHA-6194" not in response.text


def test_delete_and_email_drafts_are_isolated():
    client = TestClient(app)
    a, b = namespace(), namespace()
    for scope in (a, b):
        upload(client, scope, "notes.txt", "Notes about the current course project.")
    client.delete("/api/documents/notes.txt", headers=a)
    assert client.get("/api/documents", headers=a).json() == []
    assert len(client.get("/api/documents", headers=b).json()) == 1
    for scope, address in ((a, "alpha@example.org"), (b, "beta@example.org")):
        response = client.post("/api/chat", headers=scope, json={"query": "Draft an email about these course notes", "recipient_email": address, "selected_doc_ids": [], "reference_date": "2026-11-06"})
        assert response.status_code == 200
        assert response.json()["draft"]["recipient_email"] == address
    assert get_workspace_services(a["X-Workspace-ID"]).drafts.get("draft_001").recipient_email == "alpha@example.org"
    assert get_workspace_services(b["X-Workspace-ID"]).drafts.get("draft_001").recipient_email == "beta@example.org"


def test_invalid_namespace_is_rejected_and_custom_report_has_no_demo_citations():
    client = TestClient(app)
    for value in ("../private", "", "x" * 65):
        assert client.get("/api/documents", headers={"X-Workspace-ID": value}).status_code == 400
    response = client.post("/api/chat", headers=namespace(), json={"query": "Reconcile requirements and tasks", "selected_doc_ids": [], "reference_date": "2026-11-06"})
    assert response.json()["reconciliation_report"]["item_reports"] == []
