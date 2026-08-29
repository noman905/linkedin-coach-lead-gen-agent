"""
Phase 1 — Google Search Scraper for LinkedIn Profiles
Module: google_linkedin_scraper.py

Discovers LinkedIn profile URLs by constructing targeted search queries
and running the apify/google-search-scraper actor. Divides page counts,
validates profile URLs, deduplicates, and preserves Google snippet metadata.
"""

import re
import urllib.parse
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from apify_client_wrapper import ApifyClientWrapper, ApifyCreditsExhaustedError

logger = logging.getLogger("Phase1_GoogleLinkedInScraper")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class GoogleLinkedInLeadSnippet(BaseModel):
    """Data model representing a discovered lead with Google snippet information."""
    url: str = Field(..., description="Clean LinkedIn profile URL")
    title: str = Field(default="", description="Search result title containing name and partial headline")
    websiteTitle: str = Field(default="", description="Typically 'LinkedIn · Full Name'")
    displayedUrl: str = Field(default="", description="Displayed URL snippet, may contain follower count")
    description: str = Field(default="", description="1-2 sentence snippet from profile about or experience")
    emphasizedKeywords: List[str] = Field(default_factory=list, description="Keywords Google matched")


def generate_query_variations(niche: str, city: str) -> List[str]:
    """
    Generates 4 targeted query variations for Google Search.
    
    Q1: site:linkedin.com/in/ "[Niche]" "[City]" (exact match with site operator)
    Q2: site:linkedin.com/in/ "[Niche]ing" "[City]" (coaching/service variant)
    Q3: linkedin.com "[Niche]" "[City]" coach (broad match)
    Q4: site:linkedin.com "[Niche]" "[City]" consultant (consultant variant)
    """
    niche_clean = niche.strip()
    city_clean = city.strip()

    # Formulate Q2 variant (e.g., Coach -> Coaching, Consultant -> Consulting)
    q2_niche = niche_clean
    if re.search(r'\bcoach\b', q2_niche, flags=re.IGNORECASE):
        q2_niche = re.sub(r'\bcoach\b', 'Coaching', q2_niche, flags=re.IGNORECASE)
    elif re.search(r'\bconsultant\b', q2_niche, flags=re.IGNORECASE):
        q2_niche = re.sub(r'\bconsultant\b', 'Consulting', q2_niche, flags=re.IGNORECASE)
    elif re.search(r'\btrainer\b', q2_niche, flags=re.IGNORECASE):
        q2_niche = re.sub(r'\btrainer\b', 'Training', q2_niche, flags=re.IGNORECASE)
    elif re.search(r'\badvisor\b|\badviser\b', q2_niche, flags=re.IGNORECASE):
        q2_niche = re.sub(r'\badvisor\b|\badviser\b', 'Advising', q2_niche, flags=re.IGNORECASE)
    elif not q2_niche.lower().endswith("ing"):
        q2_niche = f"{q2_niche}ing"

    q1 = f'site:linkedin.com/in/ "{niche_clean}" "{city_clean}"'
    q2 = f'site:linkedin.com/in/ "{q2_niche}" "{city_clean}"'
    q3 = f'linkedin.com "{niche_clean}" "{city_clean}" coach'
    q4 = f'site:linkedin.com "{niche_clean}" "{city_clean}" consultant'

    return [q1, q2, q3, q4]


def distribute_pages(total_pages: int, num_queries: int = 4) -> List[int]:
    """
    Distributes total pages as evenly as possible across queries.
    Example:
      total_pages=10, num_queries=4 -> [3, 3, 2, 2] (sum=10)
      total_pages=8, num_queries=4  -> [2, 2, 2, 2] (sum=8)
      total_pages=5, num_queries=4  -> [2, 1, 1, 1] (sum=5)
      total_pages=3, num_queries=4  -> [1, 1, 1, 0] (top 3 get 1 page)
      total_pages=1, num_queries=4  -> [1, 0, 0, 0]
    """
    if total_pages <= 0:
        return [0] * num_queries

    base = total_pages // num_queries
    remainder = total_pages % num_queries

    allocation = []
    for i in range(num_queries):
        pages_for_this = base + (1 if i < remainder else 0)
        allocation.append(pages_for_this)

    return allocation


def clean_and_validate_linkedin_url(raw_url: str) -> Optional[str]:
    """
    Validates and normalizes LinkedIn profile URLs.
    Must match: https://www.linkedin.com/in/[username]
    
    Rejects:
      - /company/
      - /jobs/
      - /school/
      - /pulse/
      - /feed/
      - /groups/
      - Any URL without /in/ immediately after linkedin.com domain
    """
    if not raw_url or not isinstance(raw_url, str):
        return None

    url = raw_url.strip()
    
    # Check invalid path segments
    invalid_patterns = [
        r'/company/',
        r'/jobs/',
        r'/school/',
        r'/pulse/',
        r'/feed/',
        r'/groups/',
        r'/posts/',
        r'/detail/',
    ]
    for pattern in invalid_patterns:
        if re.search(pattern, url, flags=re.IGNORECASE):
            return None

    # Parse and clean URL
    parsed = urllib.parse.urlparse(url)
    
    # Domain check
    domain = parsed.netloc.lower()
    if not re.search(r'linkedin\.com$', domain):
        return None

    # Path check: must have /in/ followed by a username
    # Format: /in/username or /in/username/
    path = parsed.path
    match = re.search(r'^/in/([a-zA-Z0-9\-_%]+)', path)
    if not match:
        return None

    username = match.group(1).rstrip('/')
    if not username:
        return None

    # Return standard clean canonical URL
    clean_url = f"https://www.linkedin.com/in/{username}"
    return clean_url


class GoogleLinkedInScraper:
    """Phase 1 Scraper implementing Google Search discovery for LinkedIn Leads."""

    def __init__(self, apify_wrapper: Optional[ApifyClientWrapper] = None):
        self.apify_wrapper = apify_wrapper or ApifyClientWrapper()
        self.actor_id = "apify/google-search-scraper"

    def scrape_leads(
        self,
        niche: str,
        city: str,
        total_pages: int,
    ) -> List[Dict[str, Any]]:
        """
        Executes Phase 1:
        1. Generates 4 query variations.
        2. Distributes total_pages across queries.
        3. Calls apify/google-search-scraper.
        4. Validates URLs and filters non-personal pages.
        5. Deduplicates by clean LinkedIn URL.
        6. Returns list of lead snippet dictionaries.
        """
        logger.info(f"Phase 1: Starting Google search discovery for Niche='{niche}', City='{city}', Pages={total_pages}")
        
        queries = generate_query_variations(niche, city)
        page_allocations = distribute_pages(total_pages, len(queries))

        # Build query jobs with assigned page counts (> 0)
        query_jobs = []
        for q, pages in zip(queries, page_allocations):
            if pages > 0:
                query_jobs.append((q, pages))
                logger.info(f"  Query variant [{pages} pages]: {q}")

        if not query_jobs:
            logger.warning("No queries to execute (total_pages is 0).")
            return []

        raw_results = []

        # Run scraper per query to strictly respect maxPagesPerQuery
        for query_str, pages_to_scrape in query_jobs:
            run_input = {
                "queries": query_str,
                "maxPagesPerQuery": pages_to_scrape,
                "resultsPerPage": 10,
                "countryCode": "us",
                "languageCode": "en",
                "mobileResults": False,
                "csvFriendlyOutput": False,
            }

            try:
                dataset_items = self.apify_wrapper.run_actor(
                    actor_id=self.actor_id,
                    run_input=run_input,
                )
                raw_results.extend(dataset_items)
            except ApifyCreditsExhaustedError:
                logger.error("Apify credits exhausted during Phase 1 Google search scraper.")
                raise
            except Exception as e:
                logger.error(f"Error scraping query '{query_str}': {e}")
                # Continue with other queries if one errors

        # Process and extract results
        leads_by_url: Dict[str, Dict[str, Any]] = {}
        total_organic_found = 0
        invalid_url_count = 0

        for item in raw_results:
            # Check if item contains organicResults array or is flat
            organic_results = item.get("organicResults", [])
            if not organic_results and "url" in item:
                organic_results = [item]

            for org in organic_results:
                total_organic_found += 1
                raw_url = org.get("url", "")
                clean_url = clean_and_validate_linkedin_url(raw_url)

                if not clean_url:
                    invalid_url_count += 1
                    continue

                if clean_url in leads_by_url:
                    # Already captured (deduplicated)
                    continue

                title = org.get("title", "") or ""
                website_title = org.get("websiteTitle", "") or ""
                displayed_url = org.get("displayedUrl", "") or ""
                description = org.get("description", "") or ""
                emphasized_keywords = org.get("emphasizedKeywords", []) or []

                lead_snippet = GoogleLinkedInLeadSnippet(
                    url=clean_url,
                    title=title,
                    websiteTitle=website_title,
                    displayedUrl=displayed_url,
                    description=description,
                    emphasizedKeywords=emphasized_keywords,
                )
                leads_by_url[clean_url] = lead_snippet.model_dump()

        unique_leads = list(leads_by_url.values())
        logger.info(
            f"Phase 1 Complete: {total_organic_found} raw results parsed, "
            f"{invalid_url_count} non-profile URLs filtered, "
            f"{len(unique_leads)} unique validated LinkedIn profile URLs found."
        )

        return unique_leads


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Run Phase 1 Google LinkedIn Scraper")
    parser.add_argument("--niche", type=str, default="Executive Coach", help="Target niche")
    parser.add_argument("--city", type=str, default="Houston", help="Target city or state")
    parser.add_argument("--pages", type=int, default=8, help="Total pages to scrape")
    args = parser.parse_args()

    scraper = GoogleLinkedInScraper()
    try:
        results = scraper.scrape_leads(args.niche, args.city, args.pages)
        print(f"\n--- Phase 1 Results: {len(results)} Profiles Discovered ---")
        print(json.dumps(results[:3], indent=2))
        if len(results) > 3:
            print(f"... and {len(results) - 3} more profiles.")
    except Exception as e:
        print(f"Error during Phase 1 run: {e}")
