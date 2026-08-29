"""
Email Notifier Module
Module: email_notifier.py

Sends Gmail SMTP notifications after each LinkedIn agent job completes (Done or Failed).
Wraps all email operations in try/except blocks so failures never crash the agent pipeline.
"""

import os
import smtplib
import logging
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional

logger = logging.getLogger("EmailNotifier")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class EmailNotifier:
    """Sends job completion email notifications via Gmail SMTP."""

    def __init__(
        self,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        recipient_email: Optional[str] = None,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
    ):
        self.smtp_user = (
            smtp_user
            if smtp_user is not None
            else (os.getenv("NOTIFY_EMAIL_ADDRESS") or os.getenv("SMTP_SENDER_EMAIL") or "")
        )
        self.smtp_password = (
            smtp_password
            if smtp_password is not None
            else (os.getenv("NOTIFY_EMAIL_PASSWORD") or os.getenv("SMTP_SENDER_PASSWORD") or "")
        )
        self.recipient_email = (
            recipient_email
            if recipient_email is not None
            else (os.getenv("NOTIFY_EMAIL_TO") or os.getenv("ALERT_RECIPIENT_EMAIL") or self.smtp_user)
        )
        self.smtp_host = smtp_host or os.getenv("SMTP_HOST", "smtp.gmail.com")
        
        port_env = os.getenv("SMTP_PORT", "587")
        try:
            self.smtp_port = smtp_port or int(port_env)
        except ValueError:
            self.smtp_port = 587

    @staticmethod
    def get_pakistan_time() -> str:
        """Returns the current timestamp in Pakistan Time (PKT, UTC+5)."""
        pkt_timezone = timezone(timedelta(hours=5))
        now_pkt = datetime.now(pkt_timezone)
        return now_pkt.strftime("%Y-%m-%d %I:%M:%S %p PKT")

    def is_configured(self) -> bool:
        """Checks if required email credentials are provided."""
        return bool(self.smtp_user and self.smtp_password and self.recipient_email)

    def send_job_notification(
        self,
        niche: str,
        city: str,
        status: str,
        phase1_found: int = 0,
        phase2_removed: int = 0,
        phase2_remaining: int = 0,
        phase3_inactive_removed: int = 0,
        phase3_remaining: int = 0,
        phase4_unqualified_removed: int = 0,
        phase4_qualified: int = 0,
        new_leads_saved: int = 0,
        duplicates_skipped: int = 0,
        estimated_credits_usd: float = 0.0,
        remaining_credits_usd: Optional[float] = None,
        failed_phase: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Constructs and sends an email report for a single completed Control Tab job.
        Never raises exceptions; logs warnings on errors.
        """
        if not self.is_configured():
            logger.info("Email notification skipped: NOTIFY_EMAIL_ADDRESS or NOTIFY_EMAIL_PASSWORD not configured.")
            return False

        completion_time_pkt = self.get_pakistan_time()
        is_success = (status.lower() == "done")
        subject_status = "Done" if is_success else "Failed"
        subject = f"LinkedIn Agent — [{subject_status}] — {niche} {city}"

        # Build Plaintext and HTML message body
        if is_success:
            remaining_str = f"${remaining_credits_usd:.2f}" if remaining_credits_usd is not None else "N/A"
            text_body = f"""LinkedIn Lead Generation Agent — Run Report

Status: DONE
Target: {niche} in {city}
Completed At: {completion_time_pkt}

RESULTS SUMMARY:
--------------------------------------------------
• New Leads Saved:        {new_leads_saved}
• Duplicates Skipped:     {duplicates_skipped}
• Estimated Cost:         ~${estimated_credits_usd:.4f}
• Apify Remaining Credit: {remaining_str}

PHASE FUNNEL BREAKDOWN:
--------------------------------------------------
• Phase 1 (Google Search):   {phase1_found} URLs found
• Phase 2 (Pre-Filter):      {phase2_removed} removed | {phase2_remaining} remaining
• Phase 3 (Posts Check):     {phase3_inactive_removed} inactive removed | {phase3_remaining} remaining
• Phase 4 (Profile Scraper): {phase4_unqualified_removed} filtered | {phase4_qualified} qualified
• Phase 5 (Google Sheets):   {new_leads_saved} written to Leads tab
"""
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #0A66C2; color: #ffffff; padding: 20px; text-align: center;">
                    <h2 style="margin: 0; font-size: 22px;">LinkedIn Agent — Run Completed</h2>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">Status: <strong style="color: #4cd137;">DONE</strong></p>
                </div>
                <div style="padding: 20px; color: #333333; line-height: 1.6;">
                    <table style="width: 100%; margin-bottom: 20px; border-collapse: collapse;">
                        <tr><td style="padding: 6px 0; color: #777;">Target Niche:</td><td><strong>{niche}</strong></td></tr>
                        <tr><td style="padding: 6px 0; color: #777;">Target City / State:</td><td><strong>{city}</strong></td></tr>
                        <tr><td style="padding: 6px 0; color: #777;">Completion Time:</td><td><strong>{completion_time_pkt}</strong></td></tr>
                        <tr><td style="padding: 6px 0; color: #777;">New Leads Saved:</td><td><strong style="color: #0A66C2; font-size: 16px;">{new_leads_saved}</strong></td></tr>
                        <tr><td style="padding: 6px 0; color: #777;">Duplicates Skipped:</td><td><strong>{duplicates_skipped}</strong></td></tr>
                        <tr><td style="padding: 6px 0; color: #777;">Estimated Cost:</td><td><strong>~${estimated_credits_usd:.4f}</strong></td></tr>
                    </table>
                    
                    <h3 style="font-size: 16px; border-bottom: 2px solid #f0f0f0; padding-bottom: 8px; margin-top: 20px;">Funnel Breakdown</h3>
                    <ul style="padding-left: 20px; color: #555;">
                        <li><strong>Phase 1 (Google Search):</strong> {phase1_found} URLs found</li>
                        <li><strong>Phase 2 (Pre-Filter):</strong> {phase2_removed} removed, {phase2_remaining} passed</li>
                        <li><strong>Phase 3 (Posts Check):</strong> {phase3_inactive_removed} inactive removed, {phase3_remaining} active passed</li>
                        <li><strong>Phase 4 (Profile Qualifier):</strong> {phase4_unqualified_removed} removed by filter, {phase4_qualified} fully qualified</li>
                        <li><strong>Phase 5 (Google Sheets):</strong> {new_leads_saved} saved ({duplicates_skipped} duplicates skipped)</li>
                    </ul>
                </div>
                <div style="background-color: #f9f9f9; padding: 12px 20px; font-size: 12px; color: #888; text-align: center;">
                    Automated report from LinkedIn Lead Generation Agent Pipeline
                </div>
            </div>
            """
        else:
            text_body = f"""LinkedIn Lead Generation Agent — Run Report

Status: FAILED
Target: {niche} in {city}
Completed At: {completion_time_pkt}

ERROR DETAILS:
--------------------------------------------------
• Failed Phase:   {failed_phase or 'Pipeline Processing'}
• Error Message:  {error_message or 'Unknown error occurred'}
"""
            html_body = f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
                <div style="background-color: #d63031; color: #ffffff; padding: 20px; text-align: center;">
                    <h2 style="margin: 0; font-size: 22px;">LinkedIn Agent — Run Failed</h2>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">Status: <strong style="color: #ffffff;">FAILED</strong></p>
                </div>
                <div style="padding: 20px; color: #333333; line-height: 1.6;">
                    <table style="width: 100%; margin-bottom: 20px; border-collapse: collapse;">
                        <tr><td style="padding: 6px 0; color: #777;">Target Niche:</td><td><strong>{niche}</strong></td></tr>
                        <tr><td style="padding: 6px 0; color: #777;">Target City / State:</td><td><strong>{city}</strong></td></tr>
                        <tr><td style="padding: 6px 0; color: #777;">Completion Time:</td><td><strong>{completion_time_pkt}</strong></td></tr>
                        <tr><td style="padding: 6px 0; color: #777;">Failed Phase:</td><td><strong style="color: #d63031;">{failed_phase or 'General'}</strong></td></tr>
                    </table>
                    
                    <h3 style="font-size: 16px; border-bottom: 2px solid #f0f0f0; padding-bottom: 8px; color: #d63031;">Error Message</h3>
                    <div style="background-color: #ffeaa7; padding: 12px; border-radius: 4px; font-family: monospace; font-size: 13px; color: #2d3436;">
                        {error_message or 'No specific error details provided.'}
                    </div>
                </div>
                <div style="background-color: #f9f9f9; padding: 12px 20px; font-size: 12px; color: #888; text-align: center;">
                    Automated report from LinkedIn Lead Generation Agent Pipeline
                </div>
            </div>
            """

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = self.smtp_user
            msg["To"] = self.recipient_email

            msg.attach(MIMEText(text_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))

            logger.info(f"Sending email notification to '{self.recipient_email}' via {self.smtp_host}:{self.smtp_port}...")

            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, [self.recipient_email], msg.as_string())

            logger.info(f"Email notification successfully sent to {self.recipient_email} for '{niche}' '{city}' [{subject_status}].")
            return True

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            # Never raise; keep agent running
            return False
