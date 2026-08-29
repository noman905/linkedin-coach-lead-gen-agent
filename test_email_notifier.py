"""
Unit Tests for email_notifier.py
"""

import unittest
from unittest.mock import patch, MagicMock
from email_notifier import EmailNotifier


class TestEmailNotifier(unittest.TestCase):

    def test_pakistan_time_format(self):
        pkt_time = EmailNotifier.get_pakistan_time()
        self.assertIn("PKT", pkt_time)
        self.assertTrue(len(pkt_time) > 10)

    def test_configuration_check(self):
        # Incomplete config
        n1 = EmailNotifier(smtp_user="", smtp_password="", recipient_email="")
        self.assertFalse(n1.is_configured())

        # Complete config
        n2 = EmailNotifier(smtp_user="user@gmail.com", smtp_password="pwd", recipient_email="to@gmail.com")
        self.assertTrue(n2.is_configured())

    @patch("smtplib.SMTP")
    def test_send_success_notification(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        notifier = EmailNotifier(
            smtp_user="sender@gmail.com",
            smtp_password="test_password",
            recipient_email="receiver@gmail.com",
        )

        sent = notifier.send_job_notification(
            niche="Executive Coach",
            city="Houston",
            status="Done",
            phase1_found=30,
            phase2_removed=15,
            phase2_remaining=15,
            phase3_inactive_removed=10,
            phase3_remaining=5,
            phase4_unqualified_removed=2,
            phase4_qualified=3,
            new_leads_saved=3,
            duplicates_skipped=0,
            estimated_credits_usd=0.05,
            remaining_credits_usd=4.95,
        )

        self.assertTrue(sent)
        mock_server.sendmail.assert_called_once()
        sent_args = mock_server.sendmail.call_args[0]
        self.assertEqual(sent_args[0], "sender@gmail.com")
        self.assertEqual(sent_args[1], ["receiver@gmail.com"])
        self.assertIn("Executive_Coach_Houston", sent_args[2])

    @patch("smtplib.SMTP")
    def test_send_failure_notification(self, mock_smtp):
        mock_server = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_server

        notifier = EmailNotifier(
            smtp_user="sender@gmail.com",
            smtp_password="test_password",
            recipient_email="receiver@gmail.com",
        )

        sent = notifier.send_job_notification(
            niche="Executive Coach",
            city="Houston",
            status="Failed",
            failed_phase="Phase 3 (Posts Check)",
            error_message="No active profiles found in last 14 days",
        )

        self.assertTrue(sent)
        mock_server.sendmail.assert_called_once()
        sent_args = mock_server.sendmail.call_args[0]
        self.assertIn("Executive_Coach_Houston", sent_args[2])

    @patch("smtplib.SMTP")
    def test_safe_exception_handling(self, mock_smtp):
        # Simulate network error on SMTP
        mock_smtp.side_effect = Exception("Network timeout")

        notifier = EmailNotifier(
            smtp_user="sender@gmail.com",
            smtp_password="test_password",
            recipient_email="receiver@gmail.com",
        )

        # Must return False and not crash
        sent = notifier.send_job_notification(
            niche="Executive Coach",
            city="Houston",
            status="Done",
        )
        self.assertFalse(sent)


if __name__ == "__main__":
    unittest.main()
