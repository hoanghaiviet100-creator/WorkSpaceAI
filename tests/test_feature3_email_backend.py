# tests/test_feature3_email_backend.py
import unittest
from unittest import mock
from backend.services.email_service import EmailService
from backend.core.config import settings

class TestFeature3EmailBackend(unittest.TestCase):
    """Kiểm tra toàn bộ luồng FSM (draft → approve → send)"""

    def setUp(self):
        # Đảm bảo chế độ mock để không gọi SMTP thực trong các test mặc định
        settings.EMAIL_DISPATCH_MODE = "mock"

    def test_01_create_draft(self):
        draft = EmailService().create_draft(
            workspace_id="11111111-1111-1111-1111-111111111111",
            recipients=["alice@example.com"],
            subject="Test draft",
            body="Nội dung draft",
            citations=[]
        )
        self.assertEqual(draft.fsm_state, "DRAFT")
        self.assertIsNone(draft.sha256_digest)

    def test_02_approve_draft_generates_hash(self):
        draft = EmailService().create_draft(
            workspace_id="11111111-1111-1111-1111-111111111111",
            recipients=["alice@example.com"],
            subject="Test approve",
            body="Nội dung để duyệt",
            citations=[]
        )
        approved = EmailService().approve_draft_snapshot(
            draft_id=draft.id,
            recipients="alice@example.com",
            subject="Test approve (Approved)",
            body="Nội dung đã duyệt",
            user_confirmed=True,
        )
        self.assertEqual(approved.fsm_state, "APPROVED")
        self.assertIsNotNone(approved.sha256_digest)

    @mock.patch("smtplib.SMTP")
    def test_03_send_successful(self, mock_smtp):
        # Mock SMTP để luôn trả về thành công
        mock_instance = mock_smtp.return_value.__enter__.return_value
        mock_instance.sendmail.return_value = {}

        draft = EmailService().create_draft(
            workspace_id="11111111-1111-1111-1111-111111111111",
            recipients=["alice@example.com"],
            subject="Test send",
            body="Email gửi",
            citations=[]
        )
        EmailService().approve_draft_snapshot(
            draft_id=draft.id,
            recipients="alice@example.com",
            subject="Test send (Approved)",
            body="Email đã duyệt",
            user_confirmed=True,
        )
        result = EmailService().dispatch_email(draft.id)
        self.assertEqual(result["status"], "SENT")
        self.assertEqual(result["fsm_state"], "SENT")

    @mock.patch("smtplib.SMTP")
    def test_04_duplicate_send_error(self, mock_smtp):
        mock_instance = mock_smtp.return_value.__enter__.return_value
        mock_instance.sendmail.return_value = {}

        # Tạo và gửi lần đầu
        draft = EmailService().create_draft(
            workspace_id="11111111-1111-1111-1111-111111111111",
            recipients=["bob@example.com"],
            subject="Dup send",
            body="Thử gửi 2 lần",
            citations=[]
        )
        EmailService().approve_draft_snapshot(
            draft_id=draft.id,
            recipients="bob@example.com",
            subject="Dup send (Approved)",
            body="Thử gửi 2 lần",
            user_confirmed=True,
        )
        EmailService().dispatch_email(draft.id)          # lần 1 → SENT

        # Lần 2 → phải ném FSMStateError
        with self.assertRaises(Exception) as ctx:
            EmailService().dispatch_email(draft.id)
        self.assertIn("duplicate dispatch blocked", str(ctx.exception).lower())

if __name__ == "__main__":
    unittest.main()