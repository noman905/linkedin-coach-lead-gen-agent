"""
Unit Tests for Phase 4: linkedin_qualifier.py and linkedin_profile_scraper.py
"""

import unittest
from unittest.mock import MagicMock
from linkedin_qualifier import LinkedInQualifier, QualificationStats
from linkedin_profile_scraper import (
    parse_location_fields,
    extract_current_company,
    LinkedInProfileScraper,
)


class TestPhase4Qualification(unittest.TestCase):

    def setUp(self):
        self.qualifier = LinkedInQualifier()

    def test_gender_qualification(self):
        # 1. Male coach -> Keep
        male_profile = {
            "firstName": "Glenn",
            "lastName": "Smith",
            "headline": "Executive Coach & Business Consultant",
            "followerCount": 3800,
            "openToWork": False,
            "about": "Helping executives scale their leadership.",
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(male_profile)
        self.assertTrue(is_valid)

        # 2. Female coach -> Remove
        female_profile = {
            "firstName": "Sarah",
            "lastName": "Connor",
            "headline": "Executive Coach",
            "followerCount": 3800,
            "openToWork": False,
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(female_profile)
        self.assertFalse(is_valid)
        self.assertEqual(cat, "female")

        # 3. Pronouns she/her in about -> Remove
        pronoun_profile = {
            "firstName": "Alex",
            "lastName": "Taylor",
            "headline": "Leadership Coach",
            "followerCount": 2000,
            "openToWork": False,
            "about": "Alex is a certified coach (she/her) helping managers.",
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(pronoun_profile)
        self.assertFalse(is_valid)
        self.assertEqual(cat, "female")

        # 4. Gender unclear -> Keep (per rule: never remove solely due to uncertainty)
        unclear_profile = {
            "firstName": "Morgan",
            "lastName": "Sterling",
            "headline": "Executive Leadership Coach & Strategist",
            "followerCount": 2000,
            "openToWork": False,
            "about": "Passionate about helping C-suite executives.",
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(unclear_profile)
        self.assertTrue(is_valid)

    def test_targets_women_qualification(self):
        profile = {
            "firstName": "David",
            "lastName": "Miller",
            "headline": "Business Coach | I help women entrepreneurs succeed",
            "followerCount": 1500,
            "openToWork": False,
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(profile)
        self.assertFalse(is_valid)
        self.assertEqual(cat, "targets_women")

    def test_follower_bounds(self):
        # Under 250 -> Remove
        low_f = {
            "firstName": "David",
            "lastName": "Miller",
            "headline": "Executive Coach",
            "followerCount": 249,
            "openToWork": False,
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(low_f)
        self.assertFalse(is_valid)
        self.assertEqual(cat, "follower_bounds")

        # Over 31,000 -> Remove
        high_f = {
            "firstName": "David",
            "lastName": "Miller",
            "headline": "Executive Coach",
            "followerCount": 31001,
            "openToWork": False,
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(high_f)
        self.assertFalse(is_valid)
        self.assertEqual(cat, "follower_bounds")

        # Exactly 250 -> Keep
        bound_low = {
            "firstName": "David",
            "lastName": "Miller",
            "headline": "Executive Coach",
            "followerCount": 250,
            "openToWork": False,
        }
        is_valid, _, _ = self.qualifier.qualify_profile(bound_low)
        self.assertTrue(is_valid)

        # Exactly 31,000 -> Keep
        bound_high = {
            "firstName": "David",
            "lastName": "Miller",
            "headline": "Executive Coach",
            "followerCount": 31000,
            "openToWork": False,
        }
        is_valid, _, _ = self.qualifier.qualify_profile(bound_high)
        self.assertTrue(is_valid)

    def test_open_to_work(self):
        otw_profile = {
            "firstName": "Robert",
            "lastName": "Brown",
            "headline": "Executive Coach",
            "followerCount": 1200,
            "openToWork": True,
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(otw_profile)
        self.assertFalse(is_valid)
        self.assertEqual(cat, "open_to_work")

    def test_employee_only_vs_service_provider(self):
        # Pure employee with no coaching -> Remove
        employee_profile = {
            "firstName": "Mark",
            "lastName": "Davis",
            "headline": "Software Engineer at Google",
            "followerCount": 1200,
            "openToWork": False,
            "about": "Building scalable backend microservices.",
        }
        is_valid, cat, _ = self.qualifier.qualify_profile(employee_profile)
        self.assertFalse(is_valid)
        self.assertEqual(cat, "employee_only")

        # Executive Coach & Founder -> Keep
        coach_profile = {
            "firstName": "Mark",
            "lastName": "Davis",
            "headline": "Executive Coach | Founder at Davis Consulting",
            "followerCount": 1200,
            "openToWork": False,
            "about": "Coaching tech leaders to scale.",
        }
        is_valid, _, _ = self.qualifier.qualify_profile(coach_profile)
        self.assertTrue(is_valid)

    def test_location_and_company_parsers(self):
        # Location dict
        city, state, country = parse_location_fields({"city": "Houston", "state": "Texas", "country": "United States"})
        self.assertEqual(city, "Houston")
        self.assertEqual(state, "Texas")
        self.assertEqual(country, "United States")

        # Location string
        c2, s2, cnt2 = parse_location_fields("Austin, Texas, United States")
        self.assertEqual(c2, "Austin")
        self.assertEqual(s2, "Texas")
        self.assertEqual(cnt2, "United States")

        # Company parser
        comp1 = extract_current_company({"companyName": "Acme Coaching"})
        self.assertEqual(comp1, "Acme Coaching")
        comp2 = extract_current_company({"experience": [{"company": "Alpha Advisory"}]})
        self.assertEqual(comp2, "Alpha Advisory")


if __name__ == "__main__":
    unittest.main()
