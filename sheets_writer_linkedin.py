"""
Phase 5 — Google Sheets Writer
Module: sheets_writer_linkedin.py

Manages read/write operations with Google Sheets:
1. Reads pending jobs from the Control Tab (Niche, City, Pages, Status).
2. Deduplicates incoming qualified leads against existing LinkedIn URLs in the Leads Tab.
3. Appends new qualified leads with full metadata to the Leads Tab.
4. Updates Control Tab job status to Done (or Failed) with summary notes.
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Set, Tuple, Optional
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

from google_linkedin_scraper import clean_and_validate_linkedin_url

# Load environment
load_dotenv()

logger = logging.getLogger("Phase5_SheetsWriter")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Standard Column Headers
CONTROL_HEADERS = ["Niche", "City", "Pages", "Status", "Notes"]
LEADS_HEADERS = [
    "LinkedIn URL",
    "First Name",
    "Last Name",
    "Headline",
    "Follower Count",
    "Location City",
    "Location State",
    "Location Country",
    "Current Company",
    "Last Post Date",
    "Date Added",
    "Status",
]
RUN_LOG_HEADERS = [
    "Timestamp (UTC)",
    "Niche",
    "City",
    "Pages",
    "Phase 1 Found",
    "Phase 2 Passed",
    "Phase 3 Active",
    "Phase 4 Qualified",
    "New Leads Saved",
    "Duplicates Skipped",
    "Status",
    "Notes / Summary",
    "Estimated Cost ($)",
]
ERROR_LOG_HEADERS = [
    "Timestamp (UTC)",
    "Niche",
    "City",
    "Failed Phase",
    "Error Message / Reason",
    "Details / Exception",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class LinkedInSheetsWriter:
    """Manages Google Sheets operations for the 5-phase LinkedIn pipeline."""

    def __init__(
        self,
        service_account_file: Optional[str] = None,
        spreadsheet_id: Optional[str] = None,
        control_tab_name: Optional[str] = None,
        leads_tab_name: Optional[str] = None,
        run_log_tab_name: Optional[str] = None,
        error_log_tab_name: Optional[str] = None,
    ):
        self.service_account_source = (
            service_account_file
            or os.getenv("GOOGLE_SHEETS_CREDENTIALS")
            or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "credentials.json")
        )
        self.spreadsheet_id = (
            spreadsheet_id
            or os.getenv("SPREADSHEET_ID")
            or os.getenv("GOOGLE_SHEET_ID", "")
        )
        self.control_tab_name = control_tab_name or os.getenv("CONTROL_TAB_NAME", "Control")
        self.leads_tab_name = leads_tab_name or os.getenv("LEADS_TAB_NAME", "Leads")
        self.run_log_tab_name = run_log_tab_name or os.getenv("RUN_LOG_TAB_NAME", "Run Log")
        self.error_log_tab_name = error_log_tab_name or os.getenv("ERROR_LOG_TAB_NAME", "Error Log")

        self.gc: Optional[gspread.Client] = None
        self.sh: Optional[gspread.Spreadsheet] = None
        self._existing_urls_cache: Optional[Set[str]] = None

    def _get_spreadsheet(self) -> gspread.Spreadsheet:
        """Initializes and authenticates gspread client supporting JSON string or file path."""
        if self.sh:
            return self.sh

        if not self.spreadsheet_id:
            raise ValueError("SPREADSHEET_ID or GOOGLE_SHEET_ID is missing in environment variables.")

        if not self.service_account_source:
            raise ValueError("GOOGLE_SHEETS_CREDENTIALS or GOOGLE_SERVICE_ACCOUNT_FILE is missing.")

        source_str = self.service_account_source.strip()

        # Case 1: Inline JSON String (from GitHub Secrets)
        if source_str.startswith("{") and source_str.endswith("}"):
            try:
                creds_info = json.loads(source_str)
                creds = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
            except Exception as e:
                raise ValueError(f"Failed to parse GOOGLE_SHEETS_CREDENTIALS JSON string: {e}")
        # Case 2: File path on disk
        elif os.path.exists(source_str):
            creds = Credentials.from_service_account_file(source_str, scopes=SCOPES)
        else:
            raise FileNotFoundError(f"Service account file or JSON credential '{source_str}' not found.")

        self.gc = gspread.authorize(creds)
        self.sh = self.gc.open_by_key(self.spreadsheet_id)
        return self.sh

    def _get_or_create_worksheet(self, title: str, default_headers: List[str]) -> gspread.Worksheet:
        """Gets a worksheet by title, or creates it with default headers if it doesn't exist."""
        sh = self._get_spreadsheet()
        try:
            ws = sh.worksheet(title)
        except gspread.WorksheetNotFound:
            logger.info(f"Worksheet '{title}' not found. Creating new worksheet...")
            ws = sh.add_worksheet(title=title, rows=1000, cols=len(default_headers) + 5)
            ws.append_row(default_headers)
            return ws

        # Ensure headers exist
        existing_values = ws.get_all_values()
        if not existing_values or not existing_values[0] or existing_values[0] != default_headers:
            if not existing_values or not existing_values[0]:
                logger.info(f"Setting default headers on empty worksheet '{title}'...")
                ws.append_row(default_headers)
            else:
                # Update row 1 with standard headers
                logger.info(f"Updating headers on worksheet '{title}'...")
                ws.update("A1", [default_headers])

        return ws

    def initialize_sheets(self) -> None:
        """Initializes Control, Leads, Run Log, and Error Log worksheets with standard headers."""
        self._get_or_create_worksheet(self.control_tab_name, CONTROL_HEADERS)
        self._get_or_create_worksheet(self.leads_tab_name, LEADS_HEADERS)
        self._get_or_create_worksheet(self.run_log_tab_name, RUN_LOG_HEADERS)
        self._get_or_create_worksheet(self.error_log_tab_name, ERROR_LOG_HEADERS)
        logger.info("Worksheets initialized successfully.")

    def get_existing_lead_urls(self, force_refresh: bool = False) -> Set[str]:
        """
        Fetches all existing LinkedIn URLs from the Leads tab to prevent duplicates.
        Cached in-memory to avoid redundant API queries.
        """
        if self._existing_urls_cache is not None and not force_refresh:
            return self._existing_urls_cache

        ws = self._get_or_create_worksheet(self.leads_tab_name, LEADS_HEADERS)
        records = ws.get_all_values()

        existing_urls: Set[str] = set()
        if len(records) > 1:
            for row in records[1:]:
                if row and row[0]:
                    cleaned = clean_and_validate_linkedin_url(row[0].strip())
                    if cleaned:
                        existing_urls.add(cleaned)

        self._existing_urls_cache = existing_urls
        logger.info(f"Loaded {len(existing_urls)} existing lead URLs from '{self.leads_tab_name}' sheet.")
        return self._existing_urls_cache

    def write_leads(
        self,
        qualified_leads: List[Dict[str, Any]],
        today_date_str: Optional[str] = None,
    ) -> Tuple[int, int]:
        """
        Writes qualified leads to the Leads tab, skipping duplicates.
        Returns:
          (new_leads_saved: int, duplicates_skipped: int)
        """
        if not qualified_leads:
            logger.info("Phase 5: No leads to write.")
            return 0, 0

        ws = self._get_or_create_worksheet(self.leads_tab_name, LEADS_HEADERS)
        existing_urls = self.get_existing_lead_urls()

        date_added = today_date_str or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        rows_to_append: List[List[Any]] = []
        duplicates_skipped = 0

        for lead in qualified_leads:
            raw_url = lead.get("linkedinUrl") or lead.get("url") or ""
            clean_url = clean_and_validate_linkedin_url(raw_url)

            if not clean_url:
                continue

            if clean_url in existing_urls:
                duplicates_skipped += 1
                logger.debug(f"  [DUPLICATE SKIPPED] {clean_url}")
                continue

            # Construct row adhering to exact LEADS_HEADERS order
            first_name = lead.get("firstName", "") or ""
            last_name = lead.get("lastName", "") or ""
            headline = lead.get("headline", "") or ""
            follower_count = lead.get("followerCount", 0) or 0
            city = lead.get("locationCity", "") or ""
            state = lead.get("locationState", "") or ""
            country = lead.get("locationCountry", "") or ""
            current_company = lead.get("currentCompany", "") or ""
            last_post_date = lead.get("lastPostDate", "") or ""
            status = ""  # Left blank for manual outreach use

            row_data = [
                clean_url,
                first_name,
                last_name,
                headline,
                follower_count,
                city,
                state,
                country,
                current_company,
                last_post_date,
                date_added,
                status,
            ]
            rows_to_append.append(row_data)
            existing_urls.add(clean_url)

        if rows_to_append:
            logger.info(f"Writing {len(rows_to_append)} new leads to '{self.leads_tab_name}' tab...")
            ws.append_rows(rows_to_append, value_input_option="USER_ENTERED")

        logger.info(
            f"Phase 5 Complete: {len(rows_to_append)} new leads saved, "
            f"{duplicates_skipped} duplicates skipped."
        )

        return len(rows_to_append), duplicates_skipped

    def read_pending_jobs(self) -> List[Dict[str, Any]]:
        """
        Reads all rows with Status == 'Pending' from the Control tab.
        Returns a list of job dictionaries with 1-based row indexes:
          [{'row_index': 2, 'niche': 'Executive Coach', 'city': 'Houston', 'pages': 10, 'status': 'Pending'}]
        """
        ws = self._get_or_create_worksheet(self.control_tab_name, CONTROL_HEADERS)
        all_rows = ws.get_all_values()

        if len(all_rows) <= 1:
            logger.info("Control tab has no data rows.")
            return []

        header = [h.strip().lower() for h in all_rows[0]]
        
        # Determine column indexes
        niche_idx = header.index("niche") if "niche" in header else 0
        city_idx = header.index("city") if "city" in header else 1
        pages_idx = header.index("pages") if "pages" in header else 2
        status_idx = header.index("status") if "status" in header else 3

        pending_jobs: List[Dict[str, Any]] = []

        for row_num, row in enumerate(all_rows[1:], start=2):
            if not row or len(row) <= status_idx:
                continue

            niche = row[niche_idx].strip() if len(row) > niche_idx else ""
            city = row[city_idx].strip() if len(row) > city_idx else ""
            pages_raw = row[pages_idx].strip() if len(row) > pages_idx else "8"
            status = row[status_idx].strip() if len(row) > status_idx else ""

            if status.lower() == "pending" and niche and city:
                try:
                    pages = int(pages_raw)
                except ValueError:
                    pages = 8

                pending_jobs.append({
                    "row_index": row_num,
                    "niche": niche,
                    "city": city,
                    "pages": pages,
                    "status": status,
                })

        logger.info(f"Control Tab: Found {len(pending_jobs)} pending jobs.")
        return pending_jobs

    def update_control_row(
        self,
        row_index: int,
        status: str,
        notes: str = "",
    ) -> None:
        """
        Updates the Status (col D) and Notes (col E) for a given row in the Control tab.
        """
        ws = self._get_or_create_worksheet(self.control_tab_name, CONTROL_HEADERS)
        status_cell = f"D{row_index}"
        notes_cell = f"E{row_index}"

        try:
            ws.update(range_name=status_cell, values=[[status]])
            if notes:
                ws.update(range_name=notes_cell, values=[[notes]])
            logger.info(f"Updated Control row {row_index}: Status='{status}', Notes='{notes}'")
        except Exception as e:
            logger.error(f"Failed to update Control row {row_index}: {e}")

    def log_run(
        self,
        niche: str,
        city: str,
        pages: int,
        phase1_found: int = 0,
        phase2_passed: int = 0,
        phase3_active: int = 0,
        phase4_qualified: int = 0,
        new_leads_saved: int = 0,
        duplicates_skipped: int = 0,
        status: str = "Done",
        notes: str = "",
        estimated_cost: float = 0.0,
        timestamp_str: Optional[str] = None,
    ) -> None:
        """
        Appends a summary row to the Run Log tab for tracking funnel drop-offs and costs.
        """
        try:
            ws = self._get_or_create_worksheet(self.run_log_tab_name, RUN_LOG_HEADERS)
            ts = timestamp_str or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            cost_str = f"${estimated_cost:.4f}" if estimated_cost > 0 else "$0.0000"
            row_data = [
                ts,
                niche,
                city,
                pages,
                phase1_found,
                phase2_passed,
                phase3_active,
                phase4_qualified,
                new_leads_saved,
                duplicates_skipped,
                status,
                notes,
                cost_str,
            ]
            ws.append_row(row_data, value_input_option="USER_ENTERED")
            logger.info(f"Logged run to '{self.run_log_tab_name}': {niche} in {city} [{status}]")
        except Exception as e:
            logger.error(f"Failed to log run to '{self.run_log_tab_name}': {e}")

    def log_error(
        self,
        niche: str,
        city: str,
        failed_phase: str,
        error_message: str,
        details: str = "",
        timestamp_str: Optional[str] = None,
    ) -> None:
        """
        Appends an error diagnostics row to the Error Log tab.
        """
        try:
            ws = self._get_or_create_worksheet(self.error_log_tab_name, ERROR_LOG_HEADERS)
            ts = timestamp_str or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            row_data = [
                ts,
                niche,
                city,
                failed_phase,
                error_message,
                details,
            ]
            ws.append_row(row_data, value_input_option="USER_ENTERED")
            logger.info(f"Logged error to '{self.error_log_tab_name}': {niche} in {city} [{failed_phase}]")
        except Exception as e:
            logger.error(f"Failed to log error to '{self.error_log_tab_name}': {e}")


if __name__ == "__main__":
    writer = LinkedInSheetsWriter()
    writer.initialize_sheets()
    pending = writer.read_pending_jobs()
    print("Pending jobs:", pending)
