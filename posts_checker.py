"""
Phase 3 — Posts Scraper (Activity Check)
Module: posts_checker.py

Runs the cheap harvestapi/linkedin-profile-posts actor ($1.50/1k) BEFORE the
expensive profile scraper ($4.00/1k). Filters out inactive profiles, ensuring
we only pay for full profile data on leads confirmed active in the last 14 days.
"""

import time
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from apify_client_wrapper import ApifyClientWrapper, ApifyCreditsExhaustedError
from google_linkedin_scraper import clean_and_validate_linkedin_url

logger = logging.getLogger("Phase3_PostsChecker")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class ActiveLinkedInProfile(BaseModel):
    """Lead confirmed active with last post timestamp."""
    url: str
    last_post_date: str = Field(..., description="ISO 8601 timestamp of most recent post")
    days_since_last_post: float = Field(..., description="Days between now and most recent post")


def parse_post_date(date_val: Any) -> Optional[datetime]:
    """
    Parses various date formats returned by Apify harvestapi actor into UTC datetime.
    Format example: '2026-08-15T18:11:59.821Z' or {'date': '2026-08-15T18:11:59.821Z'}
    """
    if not date_val:
        return None

    raw_str = ""
    if isinstance(date_val, dict):
        raw_str = date_val.get("date") or date_val.get("timestamp") or ""
    elif isinstance(date_val, str):
        raw_str = date_val
    elif isinstance(date_val, (int, float)):
        # Epoch seconds or milliseconds
        try:
            if date_val > 1e11:  # milliseconds
                date_val = date_val / 1000.0
            return datetime.fromtimestamp(date_val, tz=timezone.utc)
        except Exception:
            return None

    if not raw_str:
        return None

    raw_str = raw_str.strip()
    try:
        # Standard ISO replacement for Z -> +00:00
        if raw_str.endswith("Z"):
            raw_str = raw_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.debug(f"Failed to parse date string '{raw_str}': {e}")
        return None


def extract_profile_url_from_post(item: Dict[str, Any]) -> Optional[str]:
    """
    Extracts and canonicalizes profile URL from a post item.
    Checks multiple common response keys from harvestapi/linkedin-profile-posts:
    - query.targetUrl
    - author.linkedinUrl / author.profileUrl
    - targetUrl / profileUrl
    """
    if not isinstance(item, dict):
        return None

    # 1. Check query object
    query_obj = item.get("query")
    if isinstance(query_obj, dict) and query_obj.get("targetUrl"):
        cand = clean_and_validate_linkedin_url(query_obj["targetUrl"])
        if cand:
            return cand
    elif isinstance(query_obj, str):
        cand = clean_and_validate_linkedin_url(query_obj)
        if cand:
            return cand

    # 2. Check author object
    author_obj = item.get("author")
    if isinstance(author_obj, dict):
        cand_author = (
            author_obj.get("linkedinUrl")
            or author_obj.get("profileUrl")
            or author_obj.get("url")
        )
        if cand_author:
            cand = clean_and_validate_linkedin_url(cand_author)
            if cand:
                return cand

    # 3. Direct fields
    candidates = [
        item.get("targetUrl"),
        item.get("profileUrl"),
        item.get("authorProfileUrl"),
        item.get("authorUrl"),
    ]
    for c in candidates:
        if c:
            cand = clean_and_validate_linkedin_url(c)
            if cand:
                return cand

    return None


class PostsChecker:
    """Phase 3 Activity Checker using harvestapi/linkedin-profile-posts."""

    def __init__(self, apify_wrapper: Optional[ApifyClientWrapper] = None):
        self.apify_wrapper = apify_wrapper or ApifyClientWrapper()
        self.actor_id = "harvestapi/linkedin-profile-posts"
        self.activity_threshold_days = 14
        self.batch_size = 50
        self.delay_between_batches = 30

    def check_activity(
        self,
        profile_urls: List[str],
        now_dt: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """
        Executes Phase 3:
        1. Takes filtered profile URLs.
        2. Batches them in chunks of <= 50.
        3. Calls harvestapi/linkedin-profile-posts with:
           - maxPosts: 8
           - postedLimit: "month"
           - scrapeReactions: false
           - scrapeComments: false
        4. Identifies most recent post per profile.
        5. Keeps profiles with posts within last 14 days.
        6. Returns list of active profile dictionaries with last_post_date.
        """
        if not profile_urls:
            logger.info("Phase 3: No profile URLs provided to check.")
            return []

        # Canonicalize target URLs
        clean_urls = []
        for u in profile_urls:
            cleaned = clean_and_validate_linkedin_url(u)
            if cleaned and cleaned not in clean_urls:
                clean_urls.append(cleaned)

        total_input = len(clean_urls)
        logger.info(f"Phase 3: Checking activity for {total_input} LinkedIn profiles (threshold: {self.activity_threshold_days} days)...")

        now = now_dt or datetime.now(timezone.utc)
        threshold_dt = now - timedelta(days=self.activity_threshold_days)

        # Mapping of clean_url -> latest post datetime
        latest_posts: Dict[str, datetime] = {}

        # Process in batches of 50
        total_batches = (total_input + self.batch_size - 1) // self.batch_size

        for i in range(0, total_input, self.batch_size):
            batch_num = (i // self.batch_size) + 1
            batch_urls = clean_urls[i : i + self.batch_size]
            logger.info(f"  Calling {self.actor_id} (Batch {batch_num}/{total_batches}, {len(batch_urls)} URLs)...")

            run_input = {
                "targetUrls": batch_urls,
                "maxPosts": 8,
                "postedLimit": "month",
                "scrapeReactions": False,
                "scrapeComments": False,
            }

            try:
                items = self.apify_wrapper.run_actor(
                    actor_id=self.actor_id,
                    run_input=run_input,
                )
            except ApifyCreditsExhaustedError:
                logger.error("Apify credits exhausted during Phase 3 posts scraper.")
                raise
            except Exception as e:
                logger.error(f"Error checking posts batch {batch_num}: {e}")
                items = []

            # Parse dataset items returned for this batch
            for item in items:
                # Identify URL
                prof_url = extract_profile_url_from_post(item)
                
                # If actor returned a flat structure without explicit author URL, check if single target was requested
                if not prof_url and len(batch_urls) == 1:
                    prof_url = batch_urls[0]

                if not prof_url:
                    continue

                # Extract post date
                posted_at_raw = item.get("postedAt") or item.get("date") or item.get("createdAt") or item.get("publishedAt")
                post_dt = parse_post_date(posted_at_raw)

                if post_dt:
                    if prof_url not in latest_posts or post_dt > latest_posts[prof_url]:
                        latest_posts[prof_url] = post_dt

            # Rate limit delay between batches (if more batches remain)
            if i + self.batch_size < total_input:
                logger.info(f"Waiting {self.delay_between_batches}s before next batch to respect rate limits...")
                time.sleep(self.delay_between_batches)

        # Filter active profiles
        active_leads: List[Dict[str, Any]] = []
        inactive_count = 0

        for url in clean_urls:
            post_dt = latest_posts.get(url)
            if post_dt and post_dt >= threshold_dt:
                days_ago = (now - post_dt).total_seconds() / 86400.0
                active_profile = ActiveLinkedInProfile(
                    url=url,
                    last_post_date=post_dt.isoformat(),
                    days_since_last_post=round(days_ago, 2),
                )
                active_leads.append(active_profile.model_dump())
            else:
                inactive_count += 1
                reason = f"Last post {post_dt.isoformat()}" if post_dt else "No recent posts found / private profile"
                logger.debug(f"  [Inactive REMOVED] {url} ({reason})")

        logger.info(
            f"Phase 3 Posts Check Complete: {total_input} input -> {len(active_leads)} active ({inactive_count} removed as inactive)."
        )

        return active_leads


if __name__ == "__main__":
    import json

    # Quick test demonstration
    test_urls = [
        "https://www.linkedin.com/in/houstonbusinesscoach",
        "https://www.linkedin.com/in/johncfarrell",
    ]

    checker = PostsChecker()
    results = checker.check_activity(test_urls)
    print(f"\n--- Phase 3 Results: {len(results)} Active Profiles Confirmed ---")
    print(json.dumps(results, indent=2))
