"""
tests/test_feature3_email_backend.py
Comprehensive Unit and Integration Test Suite for Feature 3: Context-Aware Email FSM Backend.

Covers:
1. RFC-5322 validation (valid / invalid email addresses).
2. SHA-256 integrity check and tamper detection (modify draft after approval -> SecurityError).
3. FSM enforcement (draft -> approve -> send flow; illegal transitions -> FSMStateError).
4. Duplicate-send protection (cannot re-send a SENT draft).
5. Mocked SMTP outcomes using unittest.mock.patch (success, auth error, timeout/disconnect).
6. FastAPI endpoints (/api/email/draft, /approve, /send, /audit-log) using TestClient.
7. Fixtures resetting in-memory DraftRepository between tests.

Execution:
    python -m unittest tests/test_feature3_email_backend.py
"""
import smtplib
import socket
import unittest
from unittest.mock import MagicMock, patch
import uuid
from uuid import UUID

from fastapi.testclient import TestClient

from backend.algorithms.email_state_machine import (
    ALL_FSM_STATES,
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
from backend.core.schemas import CreateDraftRequest, EmailDraftRecord, EmailFSMState
from backend.main import app
from backend.repositories.draft_repository import draft_repository
from backend.services.email_service import email_service


class TestFeature3EmailBackend(unittest.TestCase):
    """Test suite covering Feature 3 Email FSM, anti-tamper security, and REST API."""

    def setUp(self) -> None:
        """Reset repository fixture and prepare test client."""
        draft_repository.clear()
        settings.email_dispatch_mode = "local_mock"
        self.client = TestClient(app)
        self.workspace_id = uuid.uuid4()

    def tearDown(self) -> None:
        """Clean up repository after each test."""
        draft_repository.clear()

    # -------------------------------------------------------------------------
    # 1. RFC-5322 Email Validation
    # -------------------------------------------------------------------------
    def test_rfc5322_validation_valid_addresses(self) -> None:
        """Verifies valid RFC-5322 email syntax acceptance."""
        valid_addresses = [
            "student@hcmus.edu.vn",
            "instructor.name+label@sub.domain.edu.vn",
            "simple@example.com",
            "first.middle.last@company.org",
            "user_name.123@tech-corp.io",
        ]
        for email in valid_addresses:
            self.assertTrue(validate_rfc5322_email(email), f"Expected '{email}' to be valid.")

    def test_rfc5322_validation_invalid_addresses(self) -> None:
        """Verifies invalid RFC-5322 email syntax rejection."""
        invalid_addresses = [
            "",
            "   ",
            None,
            "plainaddress",
            "@missinguser.com",
            "user@",
            "user@domain",
            "user@.com",
            "user space@domain.com",
            "user@domain..com",
        ]
        for email in invalid_addresses:
            self.assertFalse(validate_rfc5322_email(email), f"Expected '{email}' to be invalid.")

    # -------------------------------------------------------------------------
    # 2. SHA-256 Cryptographic Integrity & Anti-Tamper Check
    # -------------------------------------------------------------------------
    def test_sha256_canonical_digest_determinism(self) -> None:
        """Computes deterministic SHA-256 hash regardless of whitespace or recipient ordering."""
        digest1 = compute_draft_hash("alice@example.com, bob@example.com", "Project Status", "Summary text.")
        digest2 = compute_draft_hash(["bob@example.com", "alice@example.com"], "Project Status", "Summary text.")
        digest3 = compute_draft_hash("  alice@example.com , bob@example.com  ", "Project Status", "Summary text.")
        self.assertEqual(digest1, digest2)
        self.assertEqual(digest1, digest3)
        self.assertEqual(len(digest1), 64)

    def test_sha256_tamper_detection_after_approval(self) -> None:
        """Modifying recipients, subject, or body after approval raises SecurityError."""
        state, expected_digest = approve_snapshot(
            recipients="advisor@hcmus.edu.vn",
            subject="Midterm Report",
            body="Initial approved draft content.",
            user_confirmed=True,
        )
        self.assertEqual(state, APPROVED)

        # 1. Unmodified -> OK
        self.assertTrue(
            verify_and_lock_for_send(
                current_state=state,
                expected_digest=expected_digest,
                recipients="advisor@hcmus.edu.vn",
                subject="Midterm Report",
                body="Initial approved draft content.",
            )
        )

        # 2. Tampered recipient -> SecurityError
        with self.assertRaises(SecurityError):
            verify_and_lock_for_send(
                current_state=state,
                expected_digest=expected_digest,
                recipients="attacker@evil.com",
                subject="Midterm Report",
                body="Initial approved draft content.",
            )

        # 3. Tampered subject -> SecurityError
        with self.assertRaises(SecurityError):
            verify_and_lock_for_send(
                current_state=state,
                expected_digest=expected_digest,
                recipients="advisor@hcmus.edu.vn",
                subject="Phishing Link Attached",
                body="Initial approved draft content.",
            )

        # 4. Tampered body -> SecurityError
        with self.assertRaises(SecurityError):
            verify_and_lock_for_send(
                current_state=state,
                expected_digest=expected_digest,
                recipients="advisor@hcmus.edu.vn",
                subject="Midterm Report",
                body="Malicious altered content after approval.",
            )

    # -------------------------------------------------------------------------
    # 3. FSM Lifecycle & Illegal Transition Enforcement
    # -------------------------------------------------------------------------
    def test_fsm_happy_path_lifecycle(self) -> None:
        """Verifies full lifecycle transition: DRAFT -> APPROVED -> SENT."""
        draft = email_service.create_draft(
            workspace_id=self.workspace_id,
            recipients=["advisor@hcmus.edu.vn"],
            subject="Progress Check",
            body="Review needed.",
        )
        self.assertEqual(draft.fsm_state, EmailFSMState.DRAFT)
        self.assertIsNone(draft.sha256_digest)

        # Approve snapshot
        approved = email_service.approve_draft_snapshot(
            draft_id=draft.id,
            user_confirmed=True,
        )
        self.assertEqual(approved.fsm_state, EmailFSMState.APPROVED)
        self.assertIsNotNone(approved.sha256_digest)

        # Dispatch
        outcome = email_service.dispatch_email(draft_id=draft.id)
        self.assertEqual(outcome["status"], SENT)
        stored = draft_repository.get(draft.id)
        self.assertEqual(stored.fsm_state, EmailFSMState.SENT)

    def test_fsm_illegal_transitions_rejected(self) -> None:
        """Enforces that send is prohibited from unapproved or invalid states."""
        draft = email_service.create_draft(
            workspace_id=self.workspace_id,
            recipients=["advisor@hcmus.edu.vn"],
            subject="Incomplete Work",
            body="Drafting in progress...",
        )
        self.assertEqual(draft.fsm_state, EmailFSMState.DRAFT)

        # Dispatch directly from DRAFT -> FSMStateError
        with self.assertRaises(FSMStateError):
            email_service.dispatch_email(draft_id=draft.id)

        # Approve without explicit human confirmation -> PermissionError
        with self.assertRaises(PermissionError):
            email_service.approve_draft_snapshot(draft_id=draft.id, user_confirmed=False)

        # Approve with empty subject -> ValueError
        with self.assertRaises(ValueError):
            email_service.approve_draft_snapshot(draft_id=draft.id, subject="   ", user_confirmed=True)

        # Approve with invalid recipient -> ValueError
        with self.assertRaises(ValueError):
            email_service.approve_draft_snapshot(
                draft_id=draft.id, recipients="invalid-email-address", user_confirmed=True
            )

    # -------------------------------------------------------------------------
    # 4. Duplicate-Send Protection
    # -------------------------------------------------------------------------
    def test_duplicate_send_prevention(self) -> None:
        """Verifies that a SENT draft cannot be dispatched a second time."""
        draft = email_service.create_draft(
            workspace_id=self.workspace_id,
            recipients=["faculty@hcmus.edu.vn"],
            subject="Final Report",
            body="All requirements completed.",
        )
        email_service.approve_draft_snapshot(draft_id=draft.id, user_confirmed=True)

        # First send -> Success
        first_send = email_service.dispatch_email(draft_id=draft.id)
        self.assertEqual(first_send["status"], SENT)

        # Second send -> Rejected with FSMStateError
        with self.assertRaises(FSMStateError) as ctx:
            email_service.dispatch_email(draft_id=draft.id)
        self.assertIn("already been sent", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 5. Mocked SMTP Outcomes (Success, Auth Error, Timeout)
    # -------------------------------------------------------------------------
    @patch("smtplib.SMTP")
    def test_mocked_smtp_success(self, mock_smtp_class: MagicMock) -> None:
        """Verifies successful SMTP delivery with patched smtplib.SMTP."""
        settings.email_dispatch_mode = "gmail_real"
        settings.gmail_sender_email = "team@workspaceai.edu.vn"
        settings.gmail_app_password = "abcd efgh ijkl mnop"

        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        draft = email_service.create_draft(
            workspace_id=self.workspace_id,
            recipients=["advisor@hcmus.edu.vn"],
            subject="Submission Complete",
            body="Code is pushed to GitHub.",
        )
        email_service.approve_draft_snapshot(draft_id=draft.id, user_confirmed=True)

        result = email_service.dispatch_email(draft_id=draft.id)
        self.assertEqual(result["status"], SENT)
        self.assertEqual(result["dispatch_mode"], "gmail_real")
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("team@workspaceai.edu.vn", "abcdefghijklmnop")
        mock_server.sendmail.assert_called_once()

    @patch("smtplib.SMTP")
    def test_mocked_smtp_authentication_failure(self, mock_smtp_class: MagicMock) -> None:
        """Simulates SMTPAuthenticationError and verifies state transition to FAILED."""
        settings.email_dispatch_mode = "gmail_real"
        settings.gmail_sender_email = "team@workspaceai.edu.vn"
        settings.gmail_app_password = "wrong_app_password"

        mock_server = MagicMock()
        mock_server.login.side_effect = smtplib.SMTPAuthenticationError(535, b"5.7.8 Bad credentials")
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        draft = email_service.create_draft(
            workspace_id=self.workspace_id,
            recipients=["advisor@hcmus.edu.vn"],
            subject="Weekly Progress",
            body="Status update.",
        )
        email_service.approve_draft_snapshot(draft_id=draft.id, user_confirmed=True)

        result = email_service.dispatch_email(draft_id=draft.id)
        self.assertEqual(result["status"], FAILED)
        self.assertIn("SMTP Authentication Error", result["error"])

        stored = draft_repository.get(draft.id)
        self.assertEqual(stored.fsm_state, EmailFSMState.FAILED)

    @patch("smtplib.SMTP")
    def test_mocked_smtp_timeout_delivery_unknown_nfr04(self, mock_smtp_class: MagicMock) -> None:
        """
        Simulates socket.timeout / network drop during SMTP send.
        Verifies state is marked DELIVERY_UNKNOWN without auto-retry per NFR-04.
        """
        settings.email_dispatch_mode = "gmail_real"
        settings.gmail_sender_email = "team@workspaceai.edu.vn"
        settings.gmail_app_password = "valid_password_16"

        mock_server = MagicMock()
        mock_server.sendmail.side_effect = socket.timeout("Timed out waiting for SMTP response")
        mock_smtp_class.return_value.__enter__.return_value = mock_server

        draft = email_service.create_draft(
            workspace_id=self.workspace_id,
            recipients=["advisor@hcmus.edu.vn"],
            subject="Timeout Check",
            body="Testing network disconnect.",
        )
        email_service.approve_draft_snapshot(draft_id=draft.id, user_confirmed=True)

        result = email_service.dispatch_email(draft_id=draft.id)
        self.assertEqual(result["status"], DELIVERY_UNKNOWN)
        self.assertIn("Automatic retries prohibited", result["error"])

        stored = draft_repository.get(draft.id)
        self.assertEqual(stored.fsm_state, EmailFSMState.DELIVERY_UNKNOWN)

    # -------------------------------------------------------------------------
    # 6. FastAPI Endpoints Integration (/draft, /approve, /send, /audit-log)
    # -------------------------------------------------------------------------
    def test_fastapi_rest_endpoints_complete_flow(self) -> None:
        """Integration test of /api/email REST endpoints with TestClient."""
        # 1. POST /api/email/draft
        create_res = self.client.post(
            "/api/email/draft",
            json={
                "workspace_id": str(self.workspace_id),
                "recipients": ["lecturer@hcmus.edu.vn"],
                "subject": "Sprint Review Request",
                "body": "We have completed Sprint 3 tasks.",
                "citations": ["Brief.pdf (Page 2)"],
            },
        )
        self.assertEqual(create_res.status_code, 200)
        draft_json = create_res.json()
        draft_id = draft_json["id"]
        self.assertEqual(draft_json["fsm_state"], "DRAFT")
        self.assertIsNone(draft_json["sha256_digest"])

        # 2. POST /api/email/{draft_id}/approve
        approve_res = self.client.post(
            f"/api/email/{draft_id}/approve",
            json={
                "recipients": "lecturer@hcmus.edu.vn",
                "subject": "Sprint Review Request",
                "body": "We have completed Sprint 3 tasks.",
                "user_confirmed": True,
            },
        )
        self.assertEqual(approve_res.status_code, 200)
        approved_json = approve_res.json()
        self.assertEqual(approved_json["fsm_state"], "APPROVED")
        self.assertIsNotNone(approved_json["sha256_digest"])

        # 3. GET /api/email/audit-log (PII-free)
        audit_res = self.client.get(f"/api/email/audit-log?workspace_id={self.workspace_id}")
        self.assertEqual(audit_res.status_code, 200)
        audit_log = audit_res.json()
        self.assertEqual(len(audit_log), 1)
        self.assertEqual(audit_log[0]["fsm_state"], "APPROVED")
        self.assertNotIn("lecturer@hcmus.edu.vn", str(audit_log))

        # 4. POST /api/email/{draft_id}/send
        send_res = self.client.post(f"/api/email/{draft_id}/send")
        self.assertEqual(send_res.status_code, 200)
        send_json = send_res.json()
        self.assertEqual(send_json["status"], "SENT")

        # 5. Duplicate send rejected -> 400 Bad Request
        dup_res = self.client.post(f"/api/email/{draft_id}/send")
        self.assertEqual(dup_res.status_code, 400)
        self.assertIn("already been sent", dup_res.json()["detail"])

        # 6. Non-existent draft -> 404 Not Found
        missing_res = self.client.post(f"/api/email/{uuid.uuid4()}/send")
        self.assertEqual(missing_res.status_code, 404)


if __name__ == "__main__":
    unittest.main()

