"""
Phase 2 — Pre-Filter (No API Cost)
Module: pre_filter.py

Applies fast, local keyword-based filtering on Google snippet data
(websiteTitle, title, description, displayedUrl) before any paid Apify actor calls.

Filters applied in exact order:
1. Filter 1: Remove female first names
2. Filter 2: Remove profiles targeting women / female audiences
3. Filter 3: Remove organization / institution / corporate pages
4. Filter 4: Remove low follower count (< 250) if visible in snippet
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger("Phase2_PreFilter")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# Comprehensive female names list (case-insensitive)
FEMALE_NAMES = {
    # Prompt specific list
    "jennifer", "jessica", "sarah", "sara", "ashley", "amanda", "stephanie", "nicole",
    "elizabeth", "megan", "rachel", "lauren", "samantha", "hannah", "emily", "emma",
    "olivia", "sophia", "isabella", "ava", "mia", "charlotte", "abigail", "madison",
    "brittany", "kayla", "amber", "danielle", "michelle", "lisa", "karen",
    "susan", "patricia", "linda", "barbara", "betty", "margaret", "dorothy", "sandra",
    "nancy", "carol", "ruth", "sharon", "angela", "cynthia", "kathleen", "amy",
    "shirley", "anna", "ann", "anne", "annie", "rebecca", "virginia", "katharine",
    "katherine", "catherine", "catharine", "kathryn", "kathy", "katie", "kate",
    "cathy", "christine", "christina", "janet", "deborah", "debra", "deb", "debbie",
    "maria", "gloria", "teresa", "theresa", "beverly", "frances", "martha", "diana",
    "marie", "julie", "joyce", "grace", "victoria", "vicki", "vicky", "vickie",
    "rose", "melissa", "donna", "brenda", "tiffany", "crystal", "vanessa", "heather",
    "cheryl", "natalie", "alexis", "aisha", "fatima", "priya", "neha", "pooja",
    "nisha", "anjali", "divya", "shreya", "meera", "sonia", "sonya", "kavya",
    "ananya", "zara", "layla", "nour", "hana", "yuki", "sakura", "min", "wei",
    "ling", "hui"
}

# Keywords indicating profiles targeting women
TARGETS_WOMEN_KEYWORDS = [
    "i help women",
    "helping women",
    "for women",
    "women entrepreneurs",
    "women in business",
    "female founders",
    "for moms",
    "for mothers",
    "ambitious moms",
    "working moms",
    "ladies",
    "girls",
    "sisterhood",
    "she/her",
    "her/she",
    "girls in business",
    "womens coach",
    "women's coach",
    "women leaders",
    "women in leadership",
    "empowering women",
    "female leaders",
]

# Keywords indicating organizations, institutions, or company entities
ORGANIZATION_KEYWORDS = [
    "university",
    "college",
    "academy",
    "school",
    "institute",
    "hospital",
    "clinic",
    "church",
    "ministry",
    "ministries",
    "pastor",
    "nonprofit",
    "non-profit",
    "foundation",
    "association",
    "chamber",
    "government",
    "department",
    "agency",
    "inc.",
    "llc",
    "ltd.",
    "corporation",
    "corp.",
    "media",
    "magazine",
    "news",
    "team",
    "group",
]


class PreFilterStats(BaseModel):
    """Statistics tracking removal counts per filter step."""
    total_input: int = 0
    removed_female_names: int = 0
    removed_targets_women: int = 0
    removed_organizations: int = 0
    removed_low_followers: int = 0
    total_passed: int = 0


def extract_first_name(website_title: str, title: str) -> Optional[str]:
    """
    Extracts the first name from websiteTitle or title.
    Examples:
      "LinkedIn · Glenn Smith, M.A." -> "Glenn"
      "LinkedIn · Katie B." -> "Katie"
      "John Doe - Executive Coach | LinkedIn" -> "John"
      "Dr. Robert Cialdini - Author..." -> "Robert"
    """
    candidate_str = ""

    # Primary source: websiteTitle (typically "LinkedIn · Full Name")
    if website_title:
        # Split on separators like '·', ':', '|', '-'
        parts = re.split(r'[·:|–-]', website_title)
        for part in parts:
            clean_part = part.strip()
            # Ignore "LinkedIn" word
            if clean_part.lower() != "linkedin" and len(clean_part) > 1:
                candidate_str = clean_part
                break

    # Secondary source: title if websiteTitle didn't yield a name
    if not candidate_str and title:
        parts = re.split(r'[·:|–-]', title)
        if parts:
            candidate_str = parts[0].strip()

    if not candidate_str:
        return None

    # Clean candidate string into words
    words = re.findall(r'[a-zA-Z]+', candidate_str)
    if not words:
        return None

    # Filter out common honorifics/prefixes
    prefixes = {"dr", "mr", "mrs", "ms", "prof", "coach", "rev", "pastor", "the"}
    first_name_idx = 0
    if words[0].lower() in prefixes and len(words) > 1:
        first_name_idx = 1

    first_name = words[first_name_idx].strip()
    return first_name if len(first_name) >= 2 else None


def parse_displayed_follower_count(displayed_url: str) -> Optional[int]:
    """
    Parses follower count from displayedUrl snippet if present.
    Examples:
      "3.8K+ followers" -> 3800
      "245 followers"   -> 245
      "1.2M followers"  -> 1200000
    Returns None if follower count is not visible.
    """
    if not displayed_url or not isinstance(displayed_url, str):
        return None

    match = re.search(r'([\d.,]+)\s*([kKmM]?)\+?\s*followers', displayed_url, flags=re.IGNORECASE)
    if not match:
        return None

    num_str = match.group(1).replace(',', '')
    multiplier_str = match.group(2).upper()

    try:
        val = float(num_str)
        if multiplier_str == 'K':
            return int(val * 1000)
        elif multiplier_str == 'M':
            return int(val * 1000000)
        else:
            return int(val)
    except ValueError:
        return None


class PreFilter:
    """Phase 2 Pre-Filter pipeline implementing all 4 zero-cost local filters."""

    def __init__(
        self,
        female_names: Optional[set] = None,
        targets_women_keywords: Optional[List[str]] = None,
        org_keywords: Optional[List[str]] = None,
    ):
        self.female_names = female_names or FEMALE_NAMES
        self.targets_women_keywords = targets_women_keywords or TARGETS_WOMEN_KEYWORDS
        self.org_keywords = org_keywords or ORGANIZATION_KEYWORDS

    def filter_lead(self, lead: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Evaluates a single lead snippet against the 4 filters in exact sequence.
        Returns:
          (is_kept: bool, rejection_reason: Optional[str])
        """
        title = lead.get("title", "") or ""
        website_title = lead.get("websiteTitle", "") or ""
        description = lead.get("description", "") or ""
        displayed_url = lead.get("displayedUrl", "") or ""

        combined_text = f"{title} {website_title} {description}".lower()

        # Filter 1: Check Female First Name
        first_name = extract_first_name(website_title, title)
        if first_name and first_name.lower() in self.female_names:
            return False, f"Female name detected: '{first_name}'"

        # Filter 2: Check Targets Women
        for kw in self.targets_women_keywords:
            # Word boundary regex for clean match
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, combined_text, flags=re.IGNORECASE):
                return False, f"Targets women keyword: '{kw}'"

        # Filter 3: Check Organization / Institutional Keywords
        for org_kw in self.org_keywords:
            pattern = r'\b' + re.escape(org_kw) + r'\b'
            if re.search(pattern, combined_text, flags=re.IGNORECASE):
                return False, f"Organization keyword: '{org_kw}'"

        # Filter 4: Check Low Follower Count (< 250) if visible in snippet
        followers = parse_displayed_follower_count(displayed_url)
        if followers is not None and followers < 250:
            return False, f"Follower count under 250: {followers}"

        # Passed all 4 filters
        return True, None

    def filter_leads(self, leads: List[Dict[str, Any]]) -> Tuple[List[str], PreFilterStats]:
        """
        Runs Pre-filter on a list of Phase 1 lead snippet dictionaries.
        Returns:
          - List of filtered clean LinkedIn URLs to pass to Phase 3.
          - PreFilterStats summary metrics.
        """
        stats = PreFilterStats(total_input=len(leads))
        filtered_urls: List[str] = []

        logger.info(f"Phase 2: Running pre-filter on {len(leads)} leads...")

        for lead in leads:
            url = lead.get("url", "")
            title = lead.get("title", "") or ""
            website_title = lead.get("websiteTitle", "") or ""
            description = lead.get("description", "") or ""
            displayed_url = lead.get("displayedUrl", "") or ""
            combined_text = f"{title} {website_title} {description}".lower()

            # Filter 1: Female Name
            first_name = extract_first_name(website_title, title)
            if first_name and first_name.lower() in self.female_names:
                stats.removed_female_names += 1
                logger.debug(f"  [Filter 1 REMOVED] {url} (Female name: '{first_name}')")
                continue

            # Filter 2: Targets Women
            targets_women_matched = False
            for kw in self.targets_women_keywords:
                pattern = r'\b' + re.escape(kw) + r'\b'
                if re.search(pattern, combined_text, flags=re.IGNORECASE):
                    stats.removed_targets_women += 1
                    targets_women_matched = True
                    logger.debug(f"  [Filter 2 REMOVED] {url} (Keyword: '{kw}')")
                    break
            if targets_women_matched:
                continue

            # Filter 3: Organization Keywords
            org_matched = False
            for org_kw in self.org_keywords:
                pattern = r'\b' + re.escape(org_kw) + r'\b'
                if re.search(pattern, combined_text, flags=re.IGNORECASE):
                    stats.removed_organizations += 1
                    org_matched = True
                    logger.debug(f"  [Filter 3 REMOVED] {url} (Org keyword: '{org_kw}')")
                    break
            if org_matched:
                continue

            # Filter 4: Low Followers (< 250)
            followers = parse_displayed_follower_count(displayed_url)
            if followers is not None and followers < 250:
                stats.removed_low_followers += 1
                logger.debug(f"  [Filter 4 REMOVED] {url} (Followers < 250: {followers})")
                continue

            # Kept
            filtered_urls.append(url)

        stats.total_passed = len(filtered_urls)
        total_removed = (
            stats.removed_female_names
            + stats.removed_targets_women
            + stats.removed_organizations
            + stats.removed_low_followers
        )

        logger.info(
            f"Phase 2 Pre-filter Complete: {stats.total_input} input -> {stats.total_passed} passed ({total_removed} removed).\n"
            f"  - Removed Female Names: {stats.removed_female_names}\n"
            f"  - Removed Targets Women: {stats.removed_targets_women}\n"
            f"  - Removed Organizations: {stats.removed_organizations}\n"
            f"  - Removed Low Followers (<250): {stats.removed_low_followers}"
        )

        return filtered_urls, stats


if __name__ == "__main__":
    # Quick standalone demonstration
    sample_leads = [
        {
            "url": "https://www.linkedin.com/in/houstonbusinesscoach",
            "title": "Glenn Smith, M.A. - Fractional Integrator",
            "websiteTitle": "LinkedIn · Glenn Smith, M.A.",
            "displayedUrl": "3.8K+ followers",
            "description": "Executive Coach; Non-Profit Coach; Leadership Coach.",
        },
        {
            "url": "https://www.linkedin.com/in/katherinesbaird",
            "title": "Katie B. - Executive Coach",
            "websiteTitle": "LinkedIn · Katie B.",
            "displayedUrl": "2.4K+ followers",
            "description": "Katie B. Executive Coach | 1,000+ Hours Coaching Fortune 500 Executives.",
        },
        {
            "url": "https://www.linkedin.com/in/women-empowerment-coach",
            "title": "Mark Johnson - Life Coach",
            "websiteTitle": "LinkedIn · Mark Johnson",
            "displayedUrl": "1.2K+ followers",
            "description": "I help women entrepreneurs scale their businesses to 6 figures.",
        },
        {
            "url": "https://www.linkedin.com/in/stanford-exec-coaching",
            "title": "Stanford Executive Leadership Institute",
            "websiteTitle": "LinkedIn · Stanford Institute",
            "displayedUrl": "15K+ followers",
            "description": "University academy and institute for executive training.",
        },
        {
            "url": "https://www.linkedin.com/in/low-follower-coach",
            "title": "David Miller - Leadership Coach",
            "websiteTitle": "LinkedIn · David Miller",
            "displayedUrl": "82 followers",
            "description": "Houston executive and leadership coach.",
        }
    ]

    filter_engine = PreFilter()
    passed_urls, filter_stats = filter_engine.filter_leads(sample_leads)
    print("\nPassed URLs:", passed_urls)
    print("Stats:", filter_stats.model_dump())
