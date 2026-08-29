"""
Phase 4 Qualifier Module
Module: linkedin_qualifier.py

Standalone qualification logic for LinkedIn profiles enriched by Phase 4.
Evaluates:
- Gender (female check with unclear fallback)
- Follower count bounds (250 - 31,000)
- Open to work flag (must be False)
- Client service / coaching / consulting / mentoring offer check
- Organization / institution exclusion
- Employee-only exclusion
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel, Field

from pre_filter import FEMALE_NAMES, TARGETS_WOMEN_KEYWORDS, ORGANIZATION_KEYWORDS

logger = logging.getLogger("Phase4_LinkedInQualifier")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# Service & helping keywords indicating personal client service, coaching, consulting, or practice
CLIENT_SERVICE_KEYWORDS = [
    "coach",
    "coaching",
    "consultant",
    "consulting",
    "mentor",
    "mentoring",
    "advisor",
    "adviser",
    "advising",
    "advisory",
    "trainer",
    "training",
    "speaker",
    "speaking",
    "educator",
    "guiding",
    "guide",
    "healer",
    "healing",
    "strategist",
    "fractional",
    "founder",
    "co-founder",
    "owner",
    "principal",
    "president",
    "managing director",
    "ceo",
    "partner",
    "therapist",
    "counselor",
    "facilitator",
    "author",
]

# Employee-only keywords when NO coaching/consulting or leadership/ownership is indicated
EMPLOYEE_ONLY_PATTERNS = [
    r'\bsoftware engineer\b',
    r'\bdeveloper\b',
    r'\bqa engineer\b',
    r'\bsales representative\b|\bsales rep\b|\baccount executive\b',
    r'\baccount manager\b',
    r'\bproject manager\b',
    r'\bproduct manager\b',
    r'\bdata analyst\b|\bdata scientist\b',
    r'\bhr specialist\b|\brecruiter\b|\btalent acquisition\b',
    r'\bclerk\b|\bassociate\b|\banalyst\b|\btechnician\b',
    r'\boperations coordinator\b|\badmin assistant\b',
]


class QualificationStats(BaseModel):
    """Drop-off statistics for Phase 4 full profile qualification."""
    total_input: int = 0
    removed_female: int = 0
    removed_targets_women: int = 0
    removed_follower_bounds: int = 0
    removed_open_to_work: int = 0
    removed_organization: int = 0
    removed_employee_only: int = 0
    total_qualified: int = 0


class LinkedInQualifier:
    """Evaluates enriched profile data against all full qualification rules."""

    def __init__(
        self,
        min_followers: int = 250,
        max_followers: int = 31000,
        female_names: Optional[set] = None,
        targets_women_keywords: Optional[List[str]] = None,
        org_keywords: Optional[List[str]] = None,
    ):
        self.min_followers = min_followers
        self.max_followers = max_followers
        self.female_names = female_names or FEMALE_NAMES
        self.targets_women_keywords = targets_women_keywords or TARGETS_WOMEN_KEYWORDS
        self.org_keywords = org_keywords or ORGANIZATION_KEYWORDS

    def check_gender_female(self, profile: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Returns (True, reason) if clearly female.
        If gender is genuinely unclear, returns (False, None) to keep profile.
        """
        first_name = (profile.get("firstName") or "").strip()
        last_name = (profile.get("lastName") or "").strip()
        headline = (profile.get("headline") or "").lower()
        about = (profile.get("about") or profile.get("summary") or "").lower()

        # Check first name
        if first_name:
            # First word in case of compound name
            clean_first = re.findall(r'[a-zA-Z]+', first_name)
            if clean_first and clean_first[0].lower() in self.female_names:
                return True, f"Female first name: '{clean_first[0]}'"

        # Check pronouns in headline or about
        pronoun_patterns = [r'\bshe/her\b', r'\bher/she\b', r'\bshe / her\b', r'\bher/hers\b', r'\b(she/her/hers)\b']
        combined = f"{headline} {about}"
        for pat in pronoun_patterns:
            if re.search(pat, combined, flags=re.IGNORECASE):
                return True, "Female pronouns (she/her) detected"

        # Female gendered self-descriptions
        female_terms = [r'\bmother of\b', r'\bmom of\b', r'\bwife\b', r'\bwoman in\b', r'\bfemale founder\b', r'\bgirl boss\b']
        for term in female_terms:
            if re.search(term, combined, flags=re.IGNORECASE):
                return True, f"Female descriptor detected: '{term}'"

        return False, None

    def check_targets_women(self, profile: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        headline = (profile.get("headline") or "").lower()
        about = (profile.get("about") or profile.get("summary") or "").lower()
        combined = f"{headline} {about}"

        for kw in self.targets_women_keywords:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, combined, flags=re.IGNORECASE):
                return True, f"Targets women keyword: '{kw}'"

        return False, None

    def check_follower_count(self, profile: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Ensures 250 <= followerCount <= 31,000 inclusive.
        """
        raw_val = profile.get("followerCount")
        if raw_val is None:
            raw_val = profile.get("followersCount") or profile.get("connectionsCount") or profile.get("followers")

        if raw_val is None:
            # If follower count is completely missing from actor, allow or check connections
            return True, None

        try:
            followers = int(raw_val)
        except (ValueError, TypeError):
            return True, None

        if followers < self.min_followers:
            return False, f"Followers ({followers}) < {self.min_followers}"
        if followers > self.max_followers:
            return False, f"Followers ({followers}) > {self.max_followers}"

        return True, None

    def check_open_to_work(self, profile: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        openToWork must be False.
        """
        open_to_work = profile.get("openToWork")
        if open_to_work is True:
            return False, "Profile is marked Open To Work (openToWork=True)"
        
        # Check headline/about for open to work phrases
        headline = (profile.get("headline") or "").lower()
        if "#opentowork" in headline or "open to work" in headline or "seeking new opportunities" in headline:
            return False, "Open to work keywords in headline"

        return True, None

    def check_organization(self, profile: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Removes organization, company, school, or non-personal profiles.
        """
        first_name = profile.get("firstName") or ""
        last_name = profile.get("lastName") or ""
        headline = profile.get("headline") or ""
        combined = f"{first_name} {last_name} {headline}".lower()

        # If name is clearly an entity (e.g. "Houston Executive Coaching LLC")
        for org_kw in self.org_keywords:
            pat = r'\b' + re.escape(org_kw) + r'\b'
            if re.search(pat, f"{first_name} {last_name}".lower()):
                return False, f"Name contains organization keyword: '{org_kw}'"

        return True, None

    def check_business_type_and_employee(self, profile: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Ensures the person personally offers client service / coaching / consulting / training.
        Removes pure employees with zero client service or coaching offering.
        """
        headline = (profile.get("headline") or "").lower()
        about = (profile.get("about") or profile.get("summary") or "").lower()
        current_pos = (profile.get("currentPosition") or profile.get("currentCompany") or "").lower()
        combined = f"{headline} {about} {current_pos}"

        # 1. Check if person has any coaching, consulting, advisory, or client service indicators
        has_service_offering = False
        for kw in CLIENT_SERVICE_KEYWORDS:
            pat = r'\b' + re.escape(kw) + r'\b'
            if re.search(pat, combined):
                has_service_offering = True
                break

        if not has_service_offering:
            return False, "No client service, coaching, consulting, or advisory offering found"

        # 2. Check if headline is purely an employee title at a company with no coaching mention
        # Example: "Software Engineer at Google", "Sales Representative at Amazon"
        for pat in EMPLOYEE_ONLY_PATTERNS:
            if re.search(pat, headline):
                # If they also have "coach" or "consultant" in headline, allow it
                coaching_in_headline = any(
                    re.search(r'\b' + re.escape(c) + r'\b', headline)
                    for c in ["coach", "coaching", "consultant", "consulting", "advisor", "founder", "owner"]
                )
                if not coaching_in_headline:
                    return False, f"Employee-only role with no coaching service in headline: '{headline}'"

        return True, None

    def qualify_profile(self, profile: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Qualifies a single profile against all rules.
        Returns:
          (is_qualified: bool, filter_category: Optional[str], failure_reason: Optional[str])
        """
        # Rule 1: Gender (Female)
        is_female, reason = self.check_gender_female(profile)
        if is_female:
            return False, "female", reason

        # Rule 2: Targets Women
        targets_w, reason = self.check_targets_women(profile)
        if targets_w:
            return False, "targets_women", reason

        # Rule 3: Follower count (250 - 31,000)
        valid_followers, reason = self.check_follower_count(profile)
        if not valid_followers:
            return False, "follower_bounds", reason

        # Rule 4: Open to work
        not_open_to_work, reason = self.check_open_to_work(profile)
        if not not_open_to_work:
            return False, "open_to_work", reason

        # Rule 5: Organization check
        not_org, reason = self.check_organization(profile)
        if not not_org:
            return False, "organization", reason

        # Rule 6: Client service & employee-only check
        valid_service, reason = self.check_business_type_and_employee(profile)
        if not valid_service:
            return False, "employee_only", reason

        return True, None, None

    def qualify_profiles(self, profiles: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], QualificationStats]:
        """
        Filters and qualifies an entire batch of enriched profiles.
        Returns:
          - Qualified profile list
          - QualificationStats breakdown
        """
        stats = QualificationStats(total_input=len(profiles))
        qualified: List[Dict[str, Any]] = []

        logger.info(f"Phase 4 Qualifier: Evaluating {len(profiles)} enriched profiles...")

        for profile in profiles:
            url = profile.get("url") or profile.get("profileUrl") or ""
            is_valid, category, reason = self.qualify_profile(profile)

            if is_valid:
                qualified.append(profile)
                logger.debug(f"  [QUALIFIED] {url} ({profile.get('firstName')} {profile.get('lastName')} - {profile.get('headline')})")
            else:
                logger.debug(f"  [REMOVED by {category}] {url} Reason: {reason}")
                if category == "female":
                    stats.removed_female += 1
                elif category == "targets_women":
                    stats.removed_targets_women += 1
                elif category == "follower_bounds":
                    stats.removed_follower_bounds += 1
                elif category == "open_to_work":
                    stats.removed_open_to_work += 1
                elif category == "organization":
                    stats.removed_organization += 1
                elif category == "employee_only":
                    stats.removed_employee_only += 1

        stats.total_qualified = len(qualified)
        total_removed = stats.total_input - stats.total_qualified

        logger.info(
            f"Phase 4 Qualification Complete: {stats.total_input} input -> {stats.total_qualified} qualified ({total_removed} removed).\n"
            f"  - Removed Female: {stats.removed_female}\n"
            f"  - Removed Targets Women: {stats.removed_targets_women}\n"
            f"  - Removed Follower Bounds (<250 or >31k): {stats.removed_follower_bounds}\n"
            f"  - Removed Open to Work: {stats.removed_open_to_work}\n"
            f"  - Removed Organization Entities: {stats.removed_organization}\n"
            f"  - Removed Employee Only / No Service: {stats.removed_employee_only}"
        )

        return qualified, stats
