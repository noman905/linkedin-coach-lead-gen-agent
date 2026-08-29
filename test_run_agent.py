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

        # Verify log_error and log_run were called
        mock_writer_instance.log_error.assert_called_once_with(
            niche="Executive Coach",
            city="Houston",
            failed_phase="Phase 1 (Google Search)",
            error_message="Failed — Credits Exhausted",
            details="Apify credits too low to run. Remaining credit: $0.00. Refills on 1st of next month.",
        )
        mock_writer_instance.log_run.assert_called_once_with(
            niche="Executive Coach",
            city="Houston",
            pages=8,
            status="Failed — Credits Exhausted",
            notes="Apify credits too low to run. Remaining credit: $0.00. Refills on 1st of next month.",
        )

        # Crucial: verify that scrape_leads was called ONLY once (not for row 3 or 4)
        self.assertEqual(mock_p1_instance.scrape_leads.call_count, 1)

    @patch("run_agent.LinkedInSheetsWriter")
    @patch("run_agent.EmailNotifier")
    @patch("run_agent.GoogleLinkedInScraper")
    @patch("run_agent.PreFilter")
    @patch("run_agent.PostsChecker")
    @patch("run_agent.LinkedInProfileScraper")
    def test_successful_job_logs_to_run_log(self, mock_p4, mock_p3, mock_p2, mock_p1, mock_email, mock_writer):
        runner = LinkedInPipelineRunner()

        mock_p1_instance = mock_p1.return_value
        mock_p1_instance.scrape_leads.return_value = [{"url": "https://www.linkedin.com/in/coach1"}]
        runner.phase1_scraper = mock_p1_instance

        mock_p2_instance = mock_p2.return_value
        p2_stats = MagicMock()
        p2_stats.total_input = 1
        p2_stats.total_passed = 1
        mock_p2_instance.filter_leads.return_value = (["https://www.linkedin.com/in/coach1"], p2_stats)
        runner.phase2_pre_filter = mock_p2_instance

        mock_p3_instance = mock_p3.return_value
        mock_p3_instance.check_activity.return_value = ["https://www.linkedin.com/in/coach1"]
        runner.phase3_posts_checker = mock_p3_instance

        mock_p4_instance = mock_p4.return_value
        p4_stats = MagicMock()
        p4_stats.total_input = 1
        p4_stats.total_qualified = 1
        mock_p4_instance.scrape_and_qualify.return_value = ([{"linkedinUrl": "https://www.linkedin.com/in/coach1"}], p4_stats)
        runner.phase4_profile_scraper = mock_p4_instance

        mock_writer_instance = mock_writer.return_value
        mock_writer_instance.write_leads.return_value = (1, 0)
        mock_writer_instance.read_pending_jobs.return_value = [
            {"row_index": 2, "niche": "Business Coach", "city": "Dallas", "pages": 8}
        ]
        runner.sheets_writer = mock_writer_instance
        runner.get_remaining_apify_credits = MagicMock(return_value=4.50)

        runner.run()

        mock_writer_instance.log_run.assert_called_once()
        run_call_kwargs = mock_writer_instance.log_run.call_args[1]
        self.assertEqual(run_call_kwargs["niche"], "Business Coach")
        self.assertEqual(run_call_kwargs["city"], "Dallas")
        self.assertEqual(run_call_kwargs["status"], "Done")
        self.assertEqual(run_call_kwargs["new_leads_saved"], 1)


if __name__ == "__main__":
    unittest.main()
