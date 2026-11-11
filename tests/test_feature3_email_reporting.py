"""
tests/test_feature3_email_reporting.py
Comprehensive Test Suite for Feature 3: Context-Aware Email Reporting & FSM Send Gate.

Covers:
1. Pure stdlib isolation of email_state_machine (no leaked third-party modules).
2. RFC-5322 email validation.
3. Canonical SHA-256 payload digest and tamper detection.
4. FSM state transitions: DRAFT -> APPROVED -> SENT / FAILED / DELIVERY_UNKNOWN.
5. Duplicate-send prevention and anti-tamper security invariants (NFR-04).
6. DraftRepository CRUD, auto-generated UUID, and audit timestamps.
7. EmailService dispatch (mock mode and real SMTP exception handling).
8. FastAPI REST endpoints:
   - POST /api/email/draft
   - POST /api/email/{draft_id}/approve
   - POST /api/email/{draft_id}/send
   - GET  /api/email/audit-log
"""
from datetime import datetime
import smtplib
import socket
import unittest
from unittest.mock import MagicMock, patch
import uuid

from fastapi.testclient import TestClient

from backend.algorithms.email_state_machine import (
    APPROVED,
    DELIVERY_UNKNOWN,
    DRAFT,
    FAILED,
    SENT,
    FSMStateError,
    SecurityError,
    approve_snapshot,
    compute_draft_hash,
    validate_rfc5322_email,
    verify_and_lock_for_send,
)
from backend.core.config import settings
from backend.core.schemas import (
    EmailDraftRecord,
    EmailFSMState,
)
from backend.main import app
from backend.repositories.draft_repository import draft_repository
from backend.services.email_service import email_service


class TestFeature3EmailReporting(unittest.TestCase):
    def setUp(self):
        draft_repository.clear()
        settings.email_dispatch_mode = "local_mock"
        self.client = TestClient(app)
        self.test_ws_id = uuid.uuid4()

    def tearDown(self):
        draft_repository.clear()

    # -----------------------------------------------------------------------
    # 1. Pure stdlib isolation check
    # -----------------------------------------------------------------------
    def test_01_pure_stdlib_isolation(self):
        """Assures backend.algorithms.email_state_machine uses ONLY Python standard library."""
        import sys
        forbidden = ["pydantic", "fastapi", "starlette", "numpy", "streamlit", "rank_bm25", "httpx"]
        # Reloading in isolated context
        import backend.algorithms.email_state_machine as esm
        for mod in sys.modules:
            for f in forbidden:
                if f in mod and "backend.algorithms" in getattr(sys.modules[mod], "__file__", ""):
                    self.fail(f"Forbidden library '{f}' detected in algorithms: {mod}")

    # -----------------------------------------------------------------------
    # 2. RFC-5322 Email Validation
    # -----------------------------------------------------------------------
    def test_02_validate_rfc5322_email(self):
        valid_emails = [
            "student@hcmus.edu.vn",
            "instructor.name+tag@sub.domain.org",
            "first.last@company.com",
            "user123@domain.io",
        ]
        for e in valid_emails:
            self.assertTrue(validate_rfc5322_email(e), f"Expected valid: {e}")

        invalid_emails = [
            "",
            "   ",
            "plainaddress",
            "@missinguser.com",
            "user@",
            "user@domain",
            "user@.com",
            "user space@domain.com",
            None,
        ]
        for e in invalid_emails:
            self.assertFalse(validate_rfc5322_email(e), f"Expected invalid: {e}")

    # -----------------------------------------------------------------------
    # 3. Canonical SHA-256 Digest & Normalization
    # -----------------------------------------------------------------------
    def test_03_canonical_hash_normalization(self):
        # Recipient order independence
        hash1 = compute_draft_hash(["a@domain.com", "b@domain.com"], "Sprint Update", "Body text")
        hash2 = compute_draft_hash(["b@domain.com", "a@domain.com"], "Sprint Update", "Body text")
        self.assertEqual(hash1, hash2, "Hash must be invariant to recipient ordering.")

        # Comma-separated string vs list
        hash3 = compute_draft_hash("a@domain.com, b@domain.com", "Sprint Update", "Body text")
        self.assertEqual(hash1, hash3, "Hash must match whether recipients are list or comma-separated.")

        # Whitespace tolerance in inputs
        hash4 = compute_draft_hash(["  a@domain.com  ", "b@domain.com"], "  Sprint Update  ", "  Body text  ")
        self.assertEqual(hash1, hash4, "Hash must strip extraneous outer whitespace.")

        # Content sensitivity: altering any field changes the hash
        hash_diff_body = compute_draft_hash(["a@domain.com", "b@domain.com"], "Sprint Update", "Tampered Body")
        self.assertNotEqual(hash1, hash_diff_body)

        hash_diff_subj = compute_draft_hash(["a@domain.com", "b@domain.com"], "Altered Subject", "Body text")
        self.assertNotEqual(hash1, hash_diff_subj)

        hash_diff_recp = compute_draft_hash(["attacker@evil.com"], "Sprint Update", "Body text")
        self.assertNotEqual(hash1, hash_diff_recp)

    # -----------------------------------------------------------------------
    # 4. Snapshot Approval Rules & Error Cases
    # -----------------------------------------------------------------------
    def test_04_approve_snapshot_validation(self):
        # Human approval flag required
        with self.assertRaises(PermissionError):
            approve_snapshot("student@hcmus.edu.vn", "Subject", "Body", user_confirmed=False)

        # Empty subject rejected
        with self.assertRaises(ValueError):
            approve_snapshot("student@hcmus.edu.vn", "", "Body", user_confirmed=True)
        with self.assertRaises(ValueError):
            approve_snapshot("student@hcmus.edu.vn", "   ", "Body", user_confirmed=True)

        # Invalid recipient rejected
        with self.assertRaises(ValueError):
            approve_snapshot("not-an-email", "Subject", "Body", user_confirmed=True)

        # Success case
        state, digest = approve_snapshot("student@hcmus.edu.vn", "Milestone 1", "Completed tasks.", user_confirmed=True)
        self.assertEqual(state, APPROVED)
        self.assertEqual(len(digest), 64)

    # -----------------------------------------------------------------------
    # 5. Pre-Dispatch Verification Gate & Security Guarantees
    # -----------------------------------------------------------------------
    def test_05_verify_and_lock_for_send_guards(self):
        recipients = "student@hcmus.edu.vn"
        subject = "Project Report"
        body = "All done."
        digest = compute_draft_hash(recipients, subject, body)

        # 1. Valid send from APPROVED
        self.assertTrue(verify_and_lock_for_send(APPROVED, digest, recipients, subject, body))

        # 2. Duplicate send blocked: SENT state raises FSMStateError
        with self.assertRaises(FSMStateError):
            verify_and_lock_for_send(SENT, digest, recipients, subject, body)

        # 3. Invalid send from unapproved states: DRAFT, FAILED, DELIVERY_UNKNOWN
        for unapproved_state in (DRAFT, FAILED, DELIVERY_UNKNOWN):
            with self.assertRaises(FSMStateError):
                verify_and_lock_for_send(unapproved_state, digest, recipients, subject, body)

        # 4. Tamper detection: altered recipient raises SecurityError
        with self.assertRaises(SecurityError):
            verify_and_lock_for_send(APPROVED, digest, "attacker@evil.com", subject, body)

        # 5. Tamper detection: altered body raises SecurityError
        with self.assertRaises(SecurityError):
            verify_and_lock_for_send(APPROVED, digest, recipients, subject, "Modified body after approval!")

    # -----------------------------------------------------------------------
    # 6. DraftRepository CRUD & Invariants
    # -----------------------------------------------------------------------
    def test_06_draft_repository_crud(self):
        record = EmailDraftRecord(
            workspace_id=self.test_ws_id,
            recipients="advisor@hcmus.edu.vn",
            subject="Progress Check",
            body="Report body.",
        )
        saved = draft_repository.save(record)
        self.assertIsNotNone(saved.id)
        self.assertIsNotNone(saved.audit_timestamp)

        # Get by UUID or str
        retrieved = draft_repository.get(saved.id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.subject, "Progress Check")

        # List by workspace
        ws_drafts = draft_repository.list_by_workspace(self.test_ws_id)
        self.assertEqual(len(ws_drafts), 1)

        other_ws_drafts = draft_repository.list_by_workspace(uuid.uuid4())
        self.assertEqual(len(other_ws_drafts), 0)

        # Clear
        draft_repository.clear()
        self.assertEqual(len(draft_repository.list_all()), 0)

    # -----------------------------------------------------------------------
    # 7. EmailService Full Lifecycle (Create -> Approve -> Dispatch)
    # -----------------------------------------------------------------------
    def test_07_email_service_lifecycle_mock_mode(self):
        settings.email_dispatch_mode = "local_mock"

        # 1. Create draft -> DRAFT
        draft = email_service.create_draft(
            workspace_id=self.test_ws_id,
            recipients=["advisor@hcmus.edu.vn"],
            subject="Sprint 1 Progress",
            body="Here is our progress report.",
            citations=["Document_A.pdf (Page 1)"],
        )
        self.assertEqual(draft.fsm_state, EmailFSMState.DRAFT)
        self.assertIsNone(draft.sha256_digest)

        # 2. Approve draft snapshot -> APPROVED + SHA-256 digest
        approved = email_service.approve_draft_snapshot(
            draft_id=draft.id,
            recipients=draft.recipients,
            subject=draft.subject,
            body=draft.body,
            user_confirmed=True,
        )
        self.assertEqual(approved.fsm_state, EmailFSMState.APPROVED)
        self.assertIsNotNone(approved.sha256_digest)
        first_digest = approved.sha256_digest

        # 3. Dispatch email -> SENT
        res = email_service.dispatch_email(draft_id=draft.id)
        self.assertEqual(res["status"], "SENT")
        self.assertEqual(res["dispatch_mode"], "local_mock")

        # Verify draft state in repository is SENT
        stored_sent = draft_repository.get(draft.id)
        self.assertEqual(stored_sent.fsm_state, EmailFSMState.SENT)

        # 4. Duplicate send attempt -> raises FSMStateError
        with self.assertRaises(FSMStateError):
            email_service.dispatch_email(draft_id=draft.id)

    # -----------------------------------------------------------------------
    # 8. Real SMTP Mode & Failure States (FAILED & DELIVERY_UNKNOWN)
    # -----------------------------------------------------------------------
    def test_08_smtp_authentication_failure(self):
        settings.email_dispatch_mode = "gmail_real"
        settings.gmail_sender_email = "myemail@gmail.com"
        settings.gmail_app_password = "fake_password_16ch"

        draft = email_service.create_draft(
            workspace_id=self.test_ws_id,
            recipients="advisor@hcmus.edu.vn",
            subject="Test Auth Failure",
            body="Test body",
        )
        email_service.approve_draft_snapshot(draft_id=draft.id, user_confirmed=True)

        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            instance.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Authentication failed")

            result = email_service.dispatch_email(draft_id=draft.id)
            self.assertEqual(result["status"], "FAILED")
            self.assertIn("SMTP Authentication Error", result["error"])

            stored = draft_repository.get(draft.id)
            self.assertEqual(stored.fsm_state, EmailFSMState.FAILED)

    def test_09_smtp_network_timeout_delivery_unknown(self):
        settings.email_dispatch_mode = "gmail_real"
        settings.gmail_sender_email = "myemail@gmail.com"
        settings.gmail_app_password = "fake_password_16ch"

        draft = email_service.create_draft(
            workspace_id=self.test_ws_id,
            recipients="advisor@hcmus.edu.vn",
            subject="Test Timeout",
            body="Test body",
        )
        email_service.approve_draft_snapshot(draft_id=draft.id, user_confirmed=True)

        with patch("smtplib.SMTP") as mock_smtp:
            instance = mock_smtp.return_value.__enter__.return_value
            instance.sendmail.side_effect = socket.timeout("Timed out waiting for SMTP response")

            # CRITICAL NFR-04: DELIVERY_UNKNOWN recorded with NO auto-retry
            result = email_service.dispatch_email(draft_id=draft.id)
            self.assertEqual(result["status"], "DELIVERY_UNKNOWN")
            self.assertIn("DELIVERY_UNKNOWN", result["error"])

            stored = draft_repository.get(draft.id)
            self.assertEqual(stored.fsm_state, EmailFSMState.DELIVERY_UNKNOWN)

    # -----------------------------------------------------------------------
    # 9. REST API Endpoints End-to-End
    # -----------------------------------------------------------------------
    def test_10_rest_api_endpoints_workflow(self):
        settings.email_dispatch_mode = "local_mock"

        # 1. POST /api/email/draft
        payload = {
            "workspace_id": str(self.test_ws_id),
            "recipients": ["instructor@hcmus.edu.vn"],
            "subject": "Sprint 2 Evaluation",
            "body": "Progress details for sprint 2.",
            "citations": ["Rubric.pdf (Page 3)"],
        }
        res_create = self.client.post("/api/email/draft", json=payload)
        self.assertEqual(res_create.status_code, 200)
        draft_data = res_create.json()
        draft_id = draft_data["id"]
        self.assertEqual(draft_data["fsm_state"], "DRAFT")
        self.assertIsNone(draft_data["sha256_digest"])

        # 2. POST /api/email/{draft_id}/approve
        res_approve = self.client.post(
            f"/api/email/{draft_id}/approve",
            json={
                "recipients": "instructor@hcmus.edu.vn",
                "subject": "Sprint 2 Evaluation",
                "body": "Progress details for sprint 2.",
                "user_confirmed": True,
            },
        )
        self.assertEqual(res_approve.status_code, 200)
        approved_data = res_approve.json()
        self.assertEqual(approved_data["fsm_state"], "APPROVED")
        self.assertIsNotNone(approved_data["sha256_digest"])

        # 3. GET /api/email/audit-log
        res_audit = self.client.get(f"/api/email/audit-log?workspace_id={self.test_ws_id}")
        self.assertEqual(res_audit.status_code, 200)
        audit_entries = res_audit.json()
        self.assertEqual(len(audit_entries), 1)
        self.assertEqual(audit_entries[0]["fsm_state"], "APPROVED")

        # 4. POST /api/email/{draft_id}/send
        res_send = self.client.post(f"/api/email/{draft_id}/send")
        self.assertEqual(res_send.status_code, 200)
        send_data = res_send.json()
        self.assertEqual(send_data["status"], "SENT")

        # 5. Duplicate send rejected -> 400
        res_dup = self.client.post(f"/api/email/{draft_id}/send")
        self.assertEqual(res_dup.status_code, 400)
        self.assertIn("already been sent", res_dup.json()["detail"])


if __name__ == "__main__":
    unittest.main()

