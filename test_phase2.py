"""
Unit Tests for Phase 2: pre_filter.py
"""

import unittest
from pre_filter import (
    extract_first_name,
    parse_displayed_follower_count,
    PreFilter,
    PreFilterStats,
)


class TestPhase2PreFilter(unittest.TestCase):

    def test_extract_first_name(self):
        self.assertEqual(extract_first_name("LinkedIn · Glenn Smith, M.A.", ""), "Glenn")
        self.assertEqual(extract_first_name("LinkedIn · Katie B.", ""), "Katie")
        self.assertEqual(extract_first_name("LinkedIn: Dr. Robert Cialdini", ""), "Robert")
        self.assertEqual(extract_first_name("", "Sarah Connor - Executive Coach | LinkedIn"), "Sarah")
        self.assertEqual(extract_first_name("LinkedIn · Jennifer", ""), "Jennifer")

    def test_parse_displayed_follower_count(self):
        self.assertEqual(parse_displayed_follower_count("3.8K+ followers"), 3800)
        self.assertEqual(parse_displayed_follower_count("2.4k followers"), 2400)
        self.assertEqual(parse_displayed_follower_count("245 followers"), 245)
        self.assertEqual(parse_displayed_follower_count("150 followers"), 150)
        self.assertEqual(parse_displayed_follower_count("1.2M followers"), 1200000)
        self.assertEqual(parse_displayed_follower_count("500+ followers"), 500)
        self.assertIsNone(parse_displayed_follower_count("linkedin.com/in/houstonbusinesscoach"))
        self.assertIsNone(parse_displayed_follower_count(""))

    def test_filter_1_female_names(self):
        pre_filter = PreFilter()

        # Female name -> remove
        lead_female = {
            "url": "https://www.linkedin.com/in/katie-baird",
            "title": "Katie B. - Executive Coach",
            "websiteTitle": "LinkedIn · Katie B.",
            "displayedUrl": "2.4K+ followers",
            "description": "Executive Coach for Fortune 500",
        }
        kept, reason = pre_filter.filter_lead(lead_female)
        self.assertFalse(kept)
        self.assertIn("Female name", reason)

        # Male name -> keep
        lead_male = {
            "url": "https://www.linkedin.com/in/glenn-smith",
            "title": "Glenn Smith - Executive Coach",
            "websiteTitle": "LinkedIn · Glenn Smith",
            "displayedUrl": "2.4K+ followers",
            "description": "Executive Coach for Fortune 500",
        }
        kept, reason = pre_filter.filter_lead(lead_male)
        self.assertTrue(kept)
        self.assertIsNone(reason)

    def test_filter_2_targets_women(self):
        pre_filter = PreFilter()

        lead_targeting_women = {
            "url": "https://www.linkedin.com/in/mark-johnson",
            "title": "Mark Johnson - Business Coach",
            "websiteTitle": "LinkedIn · Mark Johnson",
            "displayedUrl": "1.5K+ followers",
            "description": "I help women entrepreneurs scale their business to 7 figures.",
        }
        kept, reason = pre_filter.filter_lead(lead_targeting_women)
        self.assertFalse(kept)
        self.assertIn("Targets women", reason)

    def test_filter_3_organizations(self):
        pre_filter = PreFilter()

        lead_org = {
            "url": "https://www.linkedin.com/in/leadership-institute",
            "title": "Houston Leadership Institute",
            "websiteTitle": "LinkedIn · Leadership Institute",
            "displayedUrl": "5K+ followers",
            "description": "Executive training academy and non-profit organization.",
        }
        kept, reason = pre_filter.filter_lead(lead_org)
        self.assertFalse(kept)
        self.assertIn("Organization keyword", reason)

    def test_filter_4_low_followers(self):
        pre_filter = PreFilter()

        lead_low_followers = {
            "url": "https://www.linkedin.com/in/david-miller",
            "title": "David Miller - Leadership Coach",
            "websiteTitle": "LinkedIn · David Miller",
            "displayedUrl": "120 followers",
            "description": "Houston executive coach.",
        }
        kept, reason = pre_filter.filter_lead(lead_low_followers)
        self.assertFalse(kept)
        self.assertIn("Follower count under 250", reason)

        # No follower count visible -> keep for Phase 4
        lead_no_follower_snippet = {
            "url": "https://www.linkedin.com/in/david-miller-2",
            "title": "David Miller - Leadership Coach",
            "websiteTitle": "LinkedIn · David Miller",
            "displayedUrl": "linkedin.com/in/david-miller-2",
            "description": "Houston executive coach.",
        }
        kept, reason = pre_filter.filter_lead(lead_no_follower_snippet)
        self.assertTrue(kept)

    def test_batch_filtering_and_stats(self):
        leads = [
            # 1. Valid male lead
            {
                "url": "https://www.linkedin.com/in/glennsmith",
                "title": "Glenn Smith - Executive Coach",
                "websiteTitle": "LinkedIn · Glenn Smith",
                "displayedUrl": "3.8K+ followers",
                "description": "Executive coach for CEOs.",
            },
            # 2. Female name (Filter 1)
            {
                "url": "https://www.linkedin.com/in/jennifer-taylor",
                "title": "Jennifer Taylor - Executive Coach",
                "websiteTitle": "LinkedIn · Jennifer Taylor",
                "displayedUrl": "2K+ followers",
                "description": "Leadership coaching.",
            },
            # 3. Targets women (Filter 2)
            {
                "url": "https://www.linkedin.com/in/tom-harris",
                "title": "Tom Harris - Career Coach",
                "websiteTitle": "LinkedIn · Tom Harris",
                "displayedUrl": "1.8K+ followers",
                "description": "Career acceleration for ambitious moms and female founders.",
            },
            # 4. Organization (Filter 3)
            {
                "url": "https://www.linkedin.com/in/stanford-exec-coaching",
                "title": "Stanford Executive Leadership Institute",
                "websiteTitle": "LinkedIn · Stanford University",
                "displayedUrl": "15K+ followers",
                "description": "University research and training center.",
            },
            # 5. Low followers (Filter 4)
            {
                "url": "https://www.linkedin.com/in/alex-stone",
                "title": "Alex Stone - Executive Coach",
                "websiteTitle": "LinkedIn · Alex Stone",
                "displayedUrl": "95 followers",
                "description": "Executive coach.",
            },
        ]

        filter_engine = PreFilter()
        passed_urls, stats = filter_engine.filter_leads(leads)

        self.assertEqual(stats.total_input, 5)
        self.assertEqual(stats.removed_female_names, 1)
        self.assertEqual(stats.removed_targets_women, 1)
        self.assertEqual(stats.removed_organizations, 1)
        self.assertEqual(stats.removed_low_followers, 1)
        self.assertEqual(stats.total_passed, 1)
        self.assertEqual(passed_urls, ["https://www.linkedin.com/in/glennsmith"])


if __name__ == "__main__":
    unittest.main()
