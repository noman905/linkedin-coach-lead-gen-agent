"""
LinkedIn Lead Generation Agent — Pipeline Orchestrator
Module: run_agent.py

Executes the 5-Phase LinkedIn Lead Generation Pipeline:
Phase 1: Google Search Scraper (Discovers profile URLs via Google)
Phase 2: Pre-filter (Local 0-cost keyword filtering on Google snippet)
Phase 3: Posts Scraper (Checks activity within 14 days, $1.50/1k)
Phase 4: Profile Scraper & Full Qualification ($4.00/1k)
Phase 5: Google Sheets Writer (Deduplication and persistence)

Includes robust Apify credit exhaustion detection that immediately halts
all remaining jobs and sends a single alert notification.
"""

import sys
import time
import logging
import argparse
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from apify_client_wrapper import ApifyClientWrapper, ApifyCreditsExhaustedError
from google_linkedin_scraper import GoogleLinkedInScraper
from pre_filter import PreFilter
from posts_checker import PostsChecker
from linkedin_profile_scraper import LinkedInProfileScraper
from linkedin_qualifier import LinkedInQualifier
from sheets_writer_linkedin import LinkedInSheetsWriter
from email_notifier import EmailNotifier

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("LinkedInAgent")


class LinkedInPipelineRunner:
    """Master orchestrator for executing the 5-phase lead generation pipeline."""

    def __init__(self):
        self.apify_wrapper = ApifyClientWrapper()
        self.phase1_scraper = GoogleLinkedInScraper(apify_wrapper=self.apify_wrapper)
        self.phase2_pre_filter = PreFilter()
        self.phase3_posts_checker = PostsChecker(apify_wrapper=self.apify_wrapper)
        self.phase4_qualifier = LinkedInQualifier()
        self.phase4_profile_scraper = LinkedInProfileScraper(
            apify_wrapper=self.apify_wrapper,
            qualifier=self.phase4_qualifier,
        )
        self.sheets_writer = LinkedInSheetsWriter()
        self.email_notifier = EmailNotifier()

    def get_remaining_apify_credits(self) -> Optional[float]:
        """Queries remaining Apify credits for the current billing cycle if available."""
        try:
            client = self.apify_wrapper.get_client()
            user_info = client.user("me").get()
            monthly_credits = 5.0
            if user_info and hasattr(user_info, "plan") and user_info.plan:
                monthly_credits = getattr(user_info.plan, "monthly_usage_credits_usd", 5.0) or 5.0

            usage_info = client.user("me").monthly_usage()
            used_credits = 0.0
            if usage_info:
                used_credits = getattr(usage_info, "total_usage_credits_usd_after_volume_discount", 0.0) or 0.0

            remaining = max(0.0, monthly_credits - used_credits)
            return round(remaining, 2)
        except Exception as e:
            logger.debug(f"Could not retrieve remaining Apify credits: {e}")
            return None

    def calculate_estimated_cost(
        self,
        phase1_pages: int,
        phase3_profiles_checked: int,
        phase4_profiles_scraped: int,
    ) -> float:
        """
        Estimates total Apify cost in USD for a single pipeline run.
        - Google Search: ~$0.002 per page
        - Posts Scraper: $1.50 per 1,000 profiles ($0.0015/profile)
        - Profile Scraper: $4.00 per 1,000 profiles ($0.004/profile)
        """
        cost_p1 = phase1_pages * 0.002
        cost_p3 = phase3_profiles_checked * 0.0015
        cost_p4 = phase4_profiles_scraped * 0.004
        return round(cost_p1 + cost_p3 + cost_p4, 4)

    def _is_credit_exhaustion(self, e: Exception) -> bool:
        """Detects if an error is due to Apify credit exhaustion."""
        if isinstance(e, ApifyCreditsExhaustedError):
            return True
        err_msg = str(e).lower()
        return "by launching this job you will exceed your remaining usage" in err_msg or "exceed your remaining usage" in err_msg

    def _handle_credit_exhaustion(
        self,
        row_index: Optional[int],
        niche: str,
        city: str,
        phase_name: str,
        pages: int = 0,
    ) -> None:
        """Handles credit exhaustion by updating the sheet, logging error/run, sending ONE email alert, and raising exception."""
        remaining_credits = self.get_remaining_apify_credits() or 0.0
        status_val = "Failed — Credits Exhausted"
        notes_val = f"Apify credits too low to run. Remaining credit: ${remaining_credits:.2f}. Refills on 1st of next month."

        logger.error(f"\n[CREDIT EXHAUSTION DETECTED in {phase_name}] {notes_val}")

        if row_index:
            try:
                self.sheets_writer.update_control_row(row_index, status_val, notes_val)
            except Exception as se:
                logger.error(f"Failed to update Control row for credit exhaustion: {se}")

        # Log to Error Log & Run Log
        self.sheets_writer.log_error(
            niche=niche,
            city=city,
            failed_phase=phase_name,
            error_message=status_val,
            details=notes_val,
        )
        self.sheets_writer.log_run(
            niche=niche,
            city=city,
            pages=pages,
            status=status_val,
            notes=notes_val,
        )

        self.email_notifier.send_job_notification(
            niche=niche,
            city=city,
            status=status_val,
            failed_phase=phase_name,
            error_message=notes_val,
        )

        raise ApifyCreditsExhaustedError(notes_val)

    def process_job(self, job: Dict[str, Any]) -> bool:
        """
        Processes a single Control Tab row through all 5 phases sequentially.
        Job format: {'row_index': 2, 'niche': 'Executive Coach', 'city': 'Houston', 'pages': 8}
        """
        row_index = job.get("row_index")
        niche = job.get("niche", "").strip()
        city = job.get("city", "").strip()
        pages = job.get("pages", 8)

        logger.info(f"\n{'='*70}\n[STARTING JOB] Row {row_index}: Niche='{niche}' | City='{city}' | Pages={pages}\n{'='*70}")

        # -------------------------------------------------------------
        # Phase 1: Google Search Discovery
        # -------------------------------------------------------------
        logger.info(">>> Phase 1: Discovering LinkedIn profile URLs via Google Search...")
        try:
            discovered_leads = self.phase1_scraper.scrape_leads(
                niche=niche,
                city=city,
                total_pages=pages,
            )
        except Exception as e:
            if self._is_credit_exhaustion(e):
                self._handle_credit_exhaustion(row_index, niche, city, "Phase 1 (Google Search)", pages=pages)
            
            err_msg = f"Phase 1 error: {e}"
            logger.error(err_msg)
            if row_index:
                self.sheets_writer.update_control_row(row_index, "Failed", f"Google search error: {e}")
            self.sheets_writer.log_error(
                niche=niche,
                city=city,
                failed_phase="Phase 1 (Google Search)",
                error_message="Google search error",
                details=str(e),
            )
            self.sheets_writer.log_run(
                niche=niche,
                city=city,
                pages=pages,
                status="Failed",
                notes=f"Google search error: {e}",
            )
            self.email_notifier.send_job_notification(
                niche=niche,
                city=city,
                status="Failed",
                failed_phase="Phase 1 (Google Search)",
                error_message=str(e),
            )
            return False

        if not discovered_leads:
            msg = f"Google returned 0 results for '{niche}' '{city}'"
            logger.warning(msg)
            if row_index:
                self.sheets_writer.update_control_row(row_index, "Failed", msg)
            self.sheets_writer.log_error(
                niche=niche,
                city=city,
                failed_phase="Phase 1 (Google Search)",
                error_message=msg,
                details="Google search returned 0 profile URLs for queries.",
            )
            self.sheets_writer.log_run(
                niche=niche,
                city=city,
                pages=pages,
                phase1_found=0,
                status="Failed",
                notes=msg,
            )
            self.email_notifier.send_job_notification(
                niche=niche,
                city=city,
                status="Failed",
                failed_phase="Phase 1 (Google Search)",
                error_message=msg,
            )
            return False

        # -------------------------------------------------------------
        # Phase 2: Pre-Filter (Local Snippet Filtering)
        # -------------------------------------------------------------
        logger.info(">>> Phase 2: Running local zero-cost pre-filter...")
        filtered_urls, p2_stats = self.phase2_pre_filter.filter_leads(discovered_leads)

        if not filtered_urls:
            msg = f"All {p2_stats.total_input} profiles removed in pre-filter"
            logger.warning(msg)
            if row_index:
                self.sheets_writer.update_control_row(row_index, "Failed", msg)
            self.sheets_writer.log_error(
                niche=niche,
                city=city,
                failed_phase="Phase 2 (Pre-Filter)",
                error_message=msg,
                details=f"All {p2_stats.total_input} candidates filtered out locally (female name, targets women, org, low followers).",
            )
            self.sheets_writer.log_run(
                niche=niche,
                city=city,
                pages=pages,
                phase1_found=len(discovered_leads),
                phase2_passed=0,
                status="Failed",
                notes=msg,
            )
            self.email_notifier.send_job_notification(
                niche=niche,
                city=city,
                status="Failed",
                phase1_found=len(discovered_leads),
                phase2_removed=p2_stats.total_input,
                failed_phase="Phase 2 (Pre-Filter)",
                error_message=msg,
            )
            return False

        # -------------------------------------------------------------
        # Phase 3: Posts Scraper (Activity Check)
        # -------------------------------------------------------------
        logger.info(">>> Phase 3: Checking recent activity (14-day threshold)...")
        try:
            active_leads = self.phase3_posts_checker.check_activity(filtered_urls)
        except Exception as e:
            if self._is_credit_exhaustion(e):
                self._handle_credit_exhaustion(row_index, niche, city, "Phase 3 (Posts Activity Check)", pages=pages)

            err_msg = f"Phase 3 error: {e}"
            logger.error(err_msg)
            if row_index:
                self.sheets_writer.update_control_row(row_index, "Failed", f"Posts activity error: {e}")
            self.sheets_writer.log_error(
                niche=niche,
                city=city,
                failed_phase="Phase 3 (Posts Activity Check)",
                error_message="Posts activity check error",
                details=str(e),
            )
            self.sheets_writer.log_run(
                niche=niche,
                city=city,
                pages=pages,
                phase1_found=len(discovered_leads),
                phase2_passed=p2_stats.total_passed,
                status="Failed",
                notes=f"Posts activity error: {e}",
                estimated_cost=self.calculate_estimated_cost(pages, 0, 0),
            )
            self.email_notifier.send_job_notification(
                niche=niche,
                city=city,
                status="Failed",
                phase1_found=len(discovered_leads),
                phase2_removed=p2_stats.total_input - p2_stats.total_passed,
                phase2_remaining=p2_stats.total_passed,
                failed_phase="Phase 3 (Posts Activity Check)",
                error_message=str(e),
            )
            return False

        if not active_leads:
            msg = f"No active profiles found in last 14 days ({len(filtered_urls)} checked)"
            logger.warning(msg)
            if row_index:
                self.sheets_writer.update_control_row(row_index, "Failed", msg)
            self.sheets_writer.log_error(
                niche=niche,
                city=city,
                failed_phase="Phase 3 (Posts Activity Check)",
                error_message=msg,
                details=f"Checked {len(filtered_urls)} profiles; 0 had posted on LinkedIn within the last 14 days.",
            )
            self.sheets_writer.log_run(
                niche=niche,
                city=city,
                pages=pages,
                phase1_found=len(discovered_leads),
                phase2_passed=p2_stats.total_passed,
                phase3_active=0,
                status="Failed",
                notes=msg,
                estimated_cost=self.calculate_estimated_cost(pages, len(filtered_urls), 0),
            )
            self.email_notifier.send_job_notification(
                niche=niche,
                city=city,
                status="Failed",
                phase1_found=len(discovered_leads),
                phase2_removed=p2_stats.total_input - p2_stats.total_passed,
                phase2_remaining=p2_stats.total_passed,
                phase3_inactive_removed=len(filtered_urls),
                failed_phase="Phase 3 (Posts Activity Check)",
                error_message=msg,
            )
            return False

        # -------------------------------------------------------------
        # Phase 4: Profile Scraper & Full Qualification
        # -------------------------------------------------------------
        logger.info(">>> Phase 4: Scraping full profile data and running qualification...")
        try:
            qualified_leads, p4_stats = self.phase4_profile_scraper.scrape_and_qualify(active_leads)
        except Exception as e:
            if self._is_credit_exhaustion(e):
                self._handle_credit_exhaustion(row_index, niche, city, "Phase 4 (Profile Scraper)", pages=pages)

            err_msg = f"Phase 4 error: {e}"
            logger.error(err_msg)
            if row_index:
                self.sheets_writer.update_control_row(row_index, "Failed", f"Profile scraper error: {e}")
            self.sheets_writer.log_error(
                niche=niche,
                city=city,
                failed_phase="Phase 4 (Profile Scraper)",
                error_message="Profile scraper error",
                details=str(e),
            )
            self.sheets_writer.log_run(
                niche=niche,
                city=city,
                pages=pages,
                phase1_found=len(discovered_leads),
                phase2_passed=p2_stats.total_passed,
                phase3_active=len(active_leads),
                status="Failed",
                notes=f"Profile scraper error: {e}",
                estimated_cost=self.calculate_estimated_cost(pages, len(filtered_urls), 0),
            )
            self.email_notifier.send_job_notification(
                niche=niche,
                city=city,
                status="Failed",
                phase1_found=len(discovered_leads),
                phase2_removed=p2_stats.total_input - p2_stats.total_passed,
                phase2_remaining=p2_stats.total_passed,
                phase3_inactive_removed=len(filtered_urls) - len(active_leads),
                phase3_remaining=len(active_leads),
                failed_phase="Phase 4 (Profile Scraper)",
                error_message=str(e),
            )
            return False

        if not qualified_leads:
            msg = f"No qualified profiles after full filter ({p4_stats.total_input} checked)"
            logger.warning(msg)
            if row_index:
                self.sheets_writer.update_control_row(row_index, "Failed", msg)
            self.sheets_writer.log_error(
                niche=niche,
                city=city,
                failed_phase="Phase 4 (Profile Qualifier)",
                error_message=msg,
                details=f"{p4_stats.total_input} active profile(s) checked, none satisfied full qualification rules (followers, gender, client service, or openToWork).",
            )
            self.sheets_writer.log_run(
                niche=niche,
                city=city,
                pages=pages,
                phase1_found=len(discovered_leads),
                phase2_passed=p2_stats.total_passed,
                phase3_active=len(active_leads),
                phase4_qualified=0,
                status="Failed",
                notes=msg,
                estimated_cost=self.calculate_estimated_cost(pages, len(filtered_urls), len(active_leads)),
            )
            self.email_notifier.send_job_notification(
                niche=niche,
                city=city,
                status="Failed",
                phase1_found=len(discovered_leads),
                phase2_removed=p2_stats.total_input - p2_stats.total_passed,
                phase2_remaining=p2_stats.total_passed,
                phase3_inactive_removed=len(filtered_urls) - len(active_leads),
                phase3_remaining=len(active_leads),
                phase4_unqualified_removed=p4_stats.total_input,
                failed_phase="Phase 4 (Profile Qualifier)",
                error_message=msg,
            )
            return False

        # -------------------------------------------------------------
        # Phase 5: Google Sheets Writer
        # -------------------------------------------------------------
        logger.info(">>> Phase 5: Saving qualified leads to Google Sheets...")
        try:
            new_saved, duplicates_skipped = self.sheets_writer.write_leads(qualified_leads)
        except Exception as e:
            err_msg = f"Phase 5 error: {e}"
            logger.error(err_msg)
            if row_index:
                self.sheets_writer.update_control_row(row_index, "Failed", f"Sheets write error: {e}")
            self.sheets_writer.log_error(
                niche=niche,
                city=city,
                failed_phase="Phase 5 (Sheets Writer)",
                error_message="Sheets write error",
                details=str(e),
            )
            self.sheets_writer.log_run(
                niche=niche,
                city=city,
                pages=pages,
                phase1_found=len(discovered_leads),
                phase2_passed=p2_stats.total_passed,
                phase3_active=len(active_leads),
                phase4_qualified=p4_stats.total_qualified,
                status="Failed",
                notes=f"Sheets write error: {e}",
                estimated_cost=self.calculate_estimated_cost(pages, len(filtered_urls), len(active_leads)),
            )
            self.email_notifier.send_job_notification(
                niche=niche,
                city=city,
                status="Failed",
                phase1_found=len(discovered_leads),
                phase2_removed=p2_stats.total_input - p2_stats.total_passed,
                phase2_remaining=p2_stats.total_passed,
                phase3_inactive_removed=len(filtered_urls) - len(active_leads),
                phase3_remaining=len(active_leads),
                phase4_unqualified_removed=p4_stats.total_input - p4_stats.total_qualified,
                phase4_qualified=p4_stats.total_qualified,
                failed_phase="Phase 5 (Sheets Writer)",
                error_message=str(e),
            )
            return False

        # Calculate estimated credits used & check remaining
        estimated_cost = self.calculate_estimated_cost(
            phase1_pages=pages,
            phase3_profiles_checked=len(filtered_urls),
            phase4_profiles_scraped=len(active_leads),
        )
        remaining_credits = self.get_remaining_apify_credits()

        # Build final summary notes
        if new_saved == 0 and duplicates_skipped > 0:
            status_result = "Done"
            summary_notes = f"All {duplicates_skipped} leads already exist in sheet. Credits: ~${estimated_cost:.2f}"
            logger.info(f"All leads already exist in sheet for '{niche}' '{city}'. Marked as Done.")
        else:
            status_result = "Done"
            summary_notes = f"{new_saved} new leads added. {duplicates_skipped} duplicates skipped. Credits: ~${estimated_cost:.2f}"

        if row_index:
            self.sheets_writer.update_control_row(row_index, status_result, summary_notes)

        # Log successful run to Run Log tab
        self.sheets_writer.log_run(
            niche=niche,
            city=city,
            pages=pages,
            phase1_found=len(discovered_leads),
            phase2_passed=p2_stats.total_passed,
            phase3_active=len(active_leads),
            phase4_qualified=p4_stats.total_qualified,
            new_leads_saved=new_saved,
            duplicates_skipped=duplicates_skipped,
            status=status_result,
            notes=summary_notes,
            estimated_cost=estimated_cost,
        )

        # Log complete pipeline run summary
        logger.info(f"\n{'-'*60}")
        logger.info(f"PIPELINE RUN SUMMARY FOR: {niche} in {city}")
        logger.info(f"  Phase 1 — Google Search:  {len(discovered_leads)} URLs found")
        logger.info(f"  Phase 2 — Pre-filter:     {p2_stats.total_input - p2_stats.total_passed} removed, {p2_stats.total_passed} remaining")
        logger.info(f"  Phase 3 — Posts Check:    {len(filtered_urls) - len(active_leads)} inactive removed, {len(active_leads)} remaining")
        logger.info(f"  Phase 4 — Profile Scraper:{p4_stats.total_input - p4_stats.total_qualified} removed by filter, {p4_stats.total_qualified} qualified")
        logger.info(f"  Phase 5 — Sheets:         {new_saved} new leads saved ({duplicates_skipped} duplicates skipped)")
        logger.info(f"  Credits used this run:    approximately ${estimated_cost:.2f}")
        logger.info(f"  Control Tab row:          {status_result}")
        logger.info(f"{'-'*60}\n")

        # Send email notification
        self.email_notifier.send_job_notification(
            niche=niche,
            city=city,
            status=status_result,
            phase1_found=len(discovered_leads),
            phase2_removed=p2_stats.total_input - p2_stats.total_passed,
            phase2_remaining=p2_stats.total_passed,
            phase3_inactive_removed=len(filtered_urls) - len(active_leads),
            phase3_remaining=len(active_leads),
            phase4_unqualified_removed=p4_stats.total_input - p4_stats.total_qualified,
            phase4_qualified=p4_stats.total_qualified,
            new_leads_saved=new_saved,
            duplicates_skipped=duplicates_skipped,
            estimated_credits_usd=estimated_cost,
            remaining_credits_usd=remaining_credits,
        )

        return True

    def run(self) -> None:
        """Reads Control Tab for all Pending rows and executes them sequentially."""
        logger.info("Initializing Google Sheets connection...")
        self.sheets_writer.initialize_sheets()

        logger.info("Reading pending jobs from Control Tab...")
        pending_jobs = self.sheets_writer.read_pending_jobs()

        if not pending_jobs:
            logger.info("No pending jobs found. Control tab is empty or all jobs are Done.")
            return

        logger.info(f"Found {len(pending_jobs)} pending jobs to process.")
        
        for idx, job in enumerate(pending_jobs, 1):
            logger.info(f"\nProcessing job {idx}/{len(pending_jobs)}: {job.get('niche')} in {job.get('city')}...")
            try:
                self.process_job(job)
            except ApifyCreditsExhaustedError as ce:
                logger.error(f"\n{'!'*70}\nSTOPPING PIPELINE IMMEDIATELY: {ce}\n{'!'*70}")
                logger.error("Halted all remaining jobs to avoid repeated failures and email spam.")
                break  # Immediately stop processing all remaining rows
            except Exception as e:
                logger.error(f"Unexpected error processing job {job}: {e}")
                self.sheets_writer.log_error(
                    niche=job.get("niche", ""),
                    city=job.get("city", ""),
                    failed_phase="General / Pipeline Loop",
                    error_message="Unexpected error processing job",
                    details=str(e),
                )
                # Continue with next job for regular non-credit errors

        logger.info("Pipeline execution cycle completed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LinkedIn Lead Generation Agent Runner")
    parser.add_argument("--niche", type=str, help="Run ad-hoc job with target niche")
    parser.add_argument("--city", type=str, help="Run ad-hoc job with target city or state")
    parser.add_argument("--pages", type=int, default=2, help="Pages to scrape for ad-hoc job")
    args = parser.parse_args()

    runner = LinkedInPipelineRunner()

    if args.niche and args.city:
        # Run ad-hoc job without Control tab dependency
        adhoc_job = {
            "row_index": None,
            "niche": args.niche,
            "city": args.city,
            "pages": args.pages,
        }
        try:
            runner.process_job(adhoc_job)
        except ApifyCreditsExhaustedError:
            logger.error("Ad-hoc job stopped due to Apify credit exhaustion.")
    else:
        # Default: Process from Control Tab
        runner.run()
