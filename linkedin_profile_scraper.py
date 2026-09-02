"""
Phase 4 — Profile Scraper (Full Data + Qualification)
Module: linkedin_profile_scraper.py

Calls harvestapi/linkedin-profile-scraper ($4.00/1k) ONLY on profiles confirmed
active in Phase 3. Parses enriched profile fields, applies full qualification
filter via LinkedInQualifier, and outputs verified qualified leads.
"""

import time
import logging
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

from apify_client_wrapper import ApifyClientWrapper, ApifyCreditsExhaustedError
from google_linkedin_scraper import clean_and_validate_linkedin_url
from linkedin_qualifier import LinkedInQualifier, QualificationStats

logger = logging.getLogger("Phase4_LinkedInProfileScraper")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class QualifiedLinkedInLead(BaseModel):
    """Enriched and qualified LinkedIn Lead model ready for Phase 5 Google Sheets."""
    linkedinUrl: str = Field(..., description="Canonical LinkedIn profile URL")
    firstName: str = Field(default="", description="First name")
    lastName: str = Field(default="", description="Last name")
    headline: str = Field(default="", description="Professional headline")
    followerCount: int = Field(default=0, description="Total verified followers")
    openToWork: bool = Field(default=False, description="Open to work flag")
    locationCity: str = Field(default="", description="City")
    locationState: str = Field(default="", description="State")
    locationCountry: str = Field(default="", description="Country")
    currentCompany: str = Field(default="", description="Current organization or practice")
    about: str = Field(default="", description="Profile summary / about section")
    lastPostDate: str = Field(default="", description="Most recent post timestamp from Phase 3")


def parse_location_fields(raw_loc: Any) -> Tuple[str, str, str]:
    """
    Parses location dict or string into (city, state, country).
    Handles harvestapi structure:
      {'linkedinText': 'Greater Houston', 'parsed': {'city': 'Houston', 'state': 'Texas', 'country': 'United States'}}
    """
    city, state, country = "", "", ""
    if not raw_loc:
        return city, state, country

    if isinstance(raw_loc, dict):
        parsed = raw_loc.get("parsed")
        if isinstance(parsed, dict):
            city = parsed.get("city") or ""
            state = parsed.get("state") or parsed.get("regionCode") or ""
            country = parsed.get("country") or parsed.get("countryFull") or ""
        
        if not city:
            city = raw_loc.get("city") or ""
        if not state:
            state = raw_loc.get("state") or raw_loc.get("region") or ""
        if not country:
            country = raw_loc.get("country") or ""

        if not city and not state and not country:
            text_val = raw_loc.get("linkedinText") or raw_loc.get("text") or raw_loc.get("name") or ""
            if text_val:
                raw_loc = text_val

    if isinstance(raw_loc, str) and (not city or not state or not country):
        parts = [p.strip() for p in raw_loc.split(",") if p.strip()]
        if len(parts) == 3:
            city, state, country = parts[0], parts[1], parts[2]
        elif len(parts) == 2:
            city, state = parts[0], parts[1]
        elif len(parts) == 1:
            city = parts[0]

    return city, state, country


def extract_current_company(item: Dict[str, Any]) -> str:
    """Extracts current company name from various actor response fields."""
    if item.get("currentCompany"):
        return str(item["currentCompany"])
    if item.get("companyName"):
        return str(item["companyName"])
    if item.get("company"):
        comp = item["company"]
        return comp.get("name", "") if isinstance(comp, dict) else str(comp)

    # Check experience array
    exp_list = item.get("experience") or item.get("positions") or []
    if isinstance(exp_list, list) and exp_list:
        first_exp = exp_list[0]
        if isinstance(first_exp, dict):
            return first_exp.get("companyName") or first_exp.get("company") or ""

    return ""


class LinkedInProfileScraper:
    """Phase 4 Pipeline executing harvestapi/linkedin-profile-scraper and full qualification."""

    def __init__(
        self,
        apify_wrapper: Optional[ApifyClientWrapper] = None,
        qualifier: Optional[LinkedInQualifier] = None,
    ):
        self.apify_wrapper = apify_wrapper or ApifyClientWrapper()
        self.qualifier = qualifier or LinkedInQualifier()
        self.actor_id = "harvestapi/linkedin-profile-scraper"
        self.batch_size = 50
        self.delay_between_batches = 30

    def scrape_and_qualify(
        self,
        active_leads: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], QualificationStats]:
        """
        Executes Phase 4:
        1. Takes active leads from Phase 3.
        2. Batches profile URLs in chunks of <= 50.
        3. Calls harvestapi/linkedin-profile-scraper.
        4. Maps returned fields into normalized structures.
        5. Preserves last_post_date from Phase 3.
        6. Runs LinkedInQualifier to filter leads.
        7. Returns list of fully qualified lead dictionaries.
        """
        if not active_leads:
            logger.info("Phase 4: No active leads provided for full profile scraping.")
            return [], QualificationStats()

        # Map clean URL -> last_post_date
        url_to_post_date: Dict[str, str] = {}
        target_urls: List[str] = []

        for lead in active_leads:
            raw_url = lead.get("url") if isinstance(lead, dict) else getattr(lead, "url", "")
            last_date = lead.get("last_post_date", "") if isinstance(lead, dict) else getattr(lead, "last_post_date", "")
            clean_url = clean_and_validate_linkedin_url(raw_url)
            if clean_url and clean_url not in target_urls:
                target_urls.append(clean_url)
                url_to_post_date[clean_url] = last_date

        total_input = len(target_urls)
        logger.info(f"Phase 4: Scraping full profile data for {total_input} active profiles...")

        raw_profile_items: List[Dict[str, Any]] = []
        total_batches = (total_input + self.batch_size - 1) // self.batch_size

        for i in range(0, total_input, self.batch_size):
            batch_num = (i // self.batch_size) + 1
            batch_urls = target_urls[i : i + self.batch_size]
            logger.info(f"  Calling {self.actor_id} (Batch {batch_num}/{total_batches}, {len(batch_urls)} URLs)...")

            # harvestapi accepts both targetUrls and urls keys
            run_input = {
                "targetUrls": batch_urls,
                "urls": [{"url": u} for u in batch_urls],
            }

            try:
                items = self.apify_wrapper.run_actor(
                    actor_id=self.actor_id,
                    run_input=run_input,
                )
                raw_profile_items.extend(items)
            except ApifyCreditsExhaustedError:
                logger.error("Apify credits exhausted during Phase 4 profile scraper.")
                raise
            except Exception as e:
                logger.error(f"Error scraping profile batch {batch_num}: {e}")

            if i + self.batch_size < total_input:
                logger.info(f"Waiting {self.delay_between_batches}s before next batch to respect rate limits...")
                time.sleep(self.delay_between_batches)

        # Normalize and enrich profile data
        enriched_profiles: List[Dict[str, Any]] = []

        for item in raw_profile_items:
            url_raw = (
                item.get("url")
                or item.get("profileUrl")
                or item.get("linkedinUrl")
                or item.get("targetUrl")
            )
            clean_url = clean_and_validate_linkedin_url(url_raw) if url_raw else None
            
            # If actor didn't return URL directly in item and only 1 was queried
            if not clean_url and len(target_urls) == 1:
                clean_url = target_urls[0]

            first_name = (item.get("firstName") or item.get("first_name") or "").strip()
            last_name = (item.get("lastName") or item.get("last_name") or "").strip()
            headline = (item.get("headline") or item.get("occupation") or "").strip()
            
            # Follower count
            follower_count_val = (
                item.get("followerCount")
                or item.get("followersCount")
                or item.get("connectionsCount")
                or 0
            )
            try:
                follower_count = int(follower_count_val)
            except (ValueError, TypeError):
                follower_count = 0

            open_to_work = bool(item.get("openToWork") or item.get("isOpenToWork") or False)
            city, state, country = parse_location_fields(item.get("location"))
            current_comp = extract_current_company(item)
            about_text = (item.get("about") or item.get("summary") or "").strip()
            last_post = url_to_post_date.get(clean_url or "", "")

            profile_obj = {
                "linkedinUrl": clean_url or "",
                "url": clean_url or "",
                "firstName": first_name,
                "lastName": last_name,
                "headline": headline,
                "followerCount": follower_count,
                "openToWork": open_to_work,
                "locationCity": city,
                "locationState": state,
                "locationCountry": country,
                "currentCompany": current_comp,
                "about": about_text,
                "lastPostDate": last_post,
            }
            enriched_profiles.append(profile_obj)

        # Run qualification filter
        qualified_leads, stats = self.qualifier.qualify_profiles(enriched_profiles)

        return qualified_leads, stats


if __name__ == "__main__":
    import json

    # Standalone demo
    sample_active_leads = [
        {
            "url": "https://www.linkedin.com/in/houstonbusinesscoach",
            "last_post_date": "2026-08-26T18:46:26.312000+00:00",
        }
    ]

    scraper = LinkedInProfileScraper()
    qualified, q_stats = scraper.scrape_and_qualify(sample_active_leads)
    print(f"\n--- Phase 4 Results: {len(qualified)} Qualified Leads ---")
    print(json.dumps(qualified, indent=2))
    print("Qualification Stats:", q_stats.model_dump())
