"""
Unit Tests for Phase 5: sheets_writer_linkedin.py
"""

import unittest
from unittest.mock import MagicMock, patch
from sheets_writer_linkedin import LinkedInSheetsWriter, LEADS_HEADERS, CONTROL_HEADERS


class TestPhase5SheetsWriter(unittest.TestCase):

    def setUp(self):
        self.writer = LinkedInSheetsWriter(
            service_account_file="mock_creds.json",
            spreadsheet_id="mock_sheet_id",
        )

    def test_duplicate_skipping_and_row_format(self):
        mock_ws = MagicMock()
        # Mock existing leads sheet: row 1 is header, row 2 is existing lead
        mock_ws.get_all_values.return_value = [
            LEADS_HEADERS,
            [
                "https://www.linkedin.com/in/existing-lead",
                "Existing",
                "Lead",
                "Coach",
                "1000",
                "Houston",
                "TX",
                "US",
                "Company",
                "2026-08-20",
                "2026-08-28",
                "",
            ]
        ]

        self.writer._get_or_create_worksheet = MagicMock(return_value=mock_ws)

        incoming_leads = [
            # Lead 1: Duplicate of existing
            {
                "linkedinUrl": "https://www.linkedin.com/in/existing-lead/",
                "firstName": "Existing",
                "lastName": "Lead",
                "headline": "Coach",
                "followerCount": 1000,
                "locationCity": "Houston",
                "locationState": "TX",
                "locationCountry": "US",
                "currentCompany": "Company",
                "lastPostDate": "2026-08-20",
            },
            # Lead 2: New qualified lead
            {
                "linkedinUrl": "https://www.linkedin.com/in/new-coach-123",
                "firstName": "Glenn",
                "lastName": "Smith",
                "headline": "Executive Coach",
                "followerCount": 3800,
                "locationCity": "Houston",
                "locationState": "Texas",
                "locationCountry": "United States",
                "currentCompany": "Glenn Smith Coaching",
                "lastPostDate": "2026-08-26",
            }
        ]

        saved, skipped = self.writer.write_leads(incoming_leads, today_date_str="2026-08-28")

        self.assertEqual(saved, 1)
        self.assertEqual(skipped, 1)
        
        # Verify append_rows was called with the new lead
        mock_ws.append_rows.assert_called_once()
        appended_rows = mock_ws.append_rows.call_args[0][0]
        self.assertEqual(len(appended_rows), 1)
        new_row = appended_rows[0]
        self.assertEqual(new_row[0], "https://www.linkedin.com/in/new-coach-123")
        self.assertEqual(new_row[1], "Glenn")
        self.assertEqual(new_row[2], "Smith")
        self.assertEqual(new_row[4], 3800)
        self.assertEqual(new_row[10], "2026-08-28")

    def test_read_pending_jobs(self):
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [
            CONTROL_HEADERS,
            ["Executive Coach", "Houston", "10", "Pending", ""],
            ["Business Coach", "Dallas", "8", "Done", "Previous run"],
            ["Leadership Coach", "Austin", "8", "Pending", ""],
        ]

        self.writer._get_or_create_worksheet = MagicMock(return_value=mock_ws)
        pending = self.writer.read_pending_jobs()

        self.assertEqual(len(pending), 2)
        self.assertEqual(pending[0]["niche"], "Executive Coach")
        self.assertEqual(pending[0]["city"], "Houston")
        self.assertEqual(pending[0]["pages"], 10)
        self.assertEqual(pending[0]["row_index"], 2)

        self.assertEqual(pending[1]["niche"], "Leadership Coach")
        self.assertEqual(pending[1]["city"], "Austin")
        self.assertEqual(pending[1]["row_index"], 4)

    def test_update_control_row(self):
        mock_ws = MagicMock()
        self.writer._get_or_create_worksheet = MagicMock(return_value=mock_ws)

        self.writer.update_control_row(row_index=2, status="Done", notes="12 new leads added")
        mock_ws.update.assert_any_call(range_name="D2", values=[["Done"]])
        mock_ws.update.assert_any_call(range_name="E2", values=[["12 new leads added"]])


if __name__ == "__main__":
    unittest.main()
