"""
Unit Tests for run_agent.py Credit Exhaustion & Halting Behavior
"""

import unittest
from unittest.mock import patch, MagicMock
from apify_client_wrapper import ApifyCreditsExhaustedError
from run_agent import LinkedInPipelineRunner


class TestRunAgentCreditExhaustion(unittest.TestCase):

    @patch("run_agent.LinkedInSheetsWriter")
    @patch("run_agent.EmailNotifier")
    @patch("run_agent.GoogleLinkedInScraper")
    def test_credit_exhaustion_halts_loop_and_updates_sheet(self, mock_p1, mock_email, mock_writer):
        runner = LinkedInPipelineRunner()
        
        # Simulate Phase 1 raising ApifyCreditsExhaustedError with the exact text
        mock_p1_instance = mock_p1.return_value
        mock_p1_instance.scrape_leads.side_effect = ApifyCreditsExhaustedError(
            "By launching this job you will exceed your remaining usage"
        )
        runner.phase1_scraper = mock_p1_instance

        mock_writer_instance = mock_writer.return_value
        mock_writer_instance.read_pending_jobs.return_value = [
            {"row_index": 2, "niche": "Executive Coach", "city": "Houston", "pages": 8},
            {"row_index": 3, "niche": "Business Coach", "city": "Dallas", "pages": 8},
            {"row_index": 4, "niche": "Leadership Coach", "city": "Miami", "pages": 8},
        ]
        runner.sheets_writer = mock_writer_instance

        mock_email_instance = mock_email.return_value
        runner.email_notifier = mock_email_instance

        runner.get_remaining_apify_credits = MagicMock(return_value=0.00)

        # Run the agent
        runner.run()

        # Check that row 2 was updated with exact status and notes
        mock_writer_instance.update_control_row.assert_called_once_with(
            2,
            "Failed — Credits Exhausted",
            "Apify credits too low to run. Remaining credit: $0.00. Refills on 1st of next month."
        )

        # Exactly ONE email was sent
        mock_email_instance.send_job_notification.assert_called_once()
        email_kwargs = mock_email_instance.send_job_notification.call_args[1]
        self.assertEqual(email_kwargs["niche"], "Executive Coach")
        self.assertEqual(email_kwargs["status"], "Failed — Credits Exhausted")

        # Crucial: verify that scrape_leads was called ONLY once (not for row 3 or 4)
        self.assertEqual(mock_p1_instance.scrape_leads.call_count, 1)


if __name__ == "__main__":
    unittest.main()
