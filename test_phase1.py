"""
Unit & Integration Tests for Phase 1: google_linkedin_scraper.py
"""

import unittest
from unittest.mock import MagicMock
from google_linkedin_scraper import (
    generate_query_variations,
    distribute_pages,
    clean_and_validate_linkedin_url,
    GoogleLinkedInScraper,
)


class TestPhase1GoogleLinkedInScraper(unittest.TestCase):

    def test_generate_query_variations(self):
        # Case 1: Executive Coach in Houston
        queries = generate_query_variations("Executive Coach", "Houston")
        self.assertEqual(len(queries), 4)
        self.assertEqual(queries[0], 'site:linkedin.com/in/ "Executive Coach" "Houston"')
        self.assertEqual(queries[1], 'site:linkedin.com/in/ "Executive Coaching" "Houston"')
        self.assertEqual(queries[2], 'linkedin.com "Executive Coach" "Houston" coach')
        self.assertEqual(queries[3], 'site:linkedin.com "Executive Coach" "Houston" consultant')

        # Case 2: Business Consultant in Miami
        queries2 = generate_query_variations("Business Consultant", "Miami")
        self.assertEqual(queries2[1], 'site:linkedin.com/in/ "Business Consulting" "Miami"')

        # Case 3: Leadership Trainer in Dallas
        queries3 = generate_query_variations("Leadership Trainer", "Dallas")
        self.assertEqual(queries3[1], 'site:linkedin.com/in/ "Leadership Training" "Dallas"')

    def test_distribute_pages(self):
        # 10 pages -> [3, 3, 2, 2]
        p10 = distribute_pages(10, 4)
        self.assertEqual(p10, [3, 3, 2, 2])
        self.assertEqual(sum(p10), 10)

        # 8 pages -> [2, 2, 2, 2]
        p8 = distribute_pages(8, 4)
        self.assertEqual(p8, [2, 2, 2, 2])
        self.assertEqual(sum(p8), 8)

        # 5 pages -> [2, 1, 1, 1]
        p5 = distribute_pages(5, 4)
        self.assertEqual(p5, [2, 1, 1, 1])
        self.assertEqual(sum(p5), 5)

        # 3 pages -> [1, 1, 1, 0]
        p3 = distribute_pages(3, 4)
        self.assertEqual(p3, [1, 1, 1, 0])
        self.assertEqual(sum(p3), 3)

        # 1 page -> [1, 0, 0, 0]
        p1 = distribute_pages(1, 4)
        self.assertEqual(p1, [1, 0, 0, 0])
        self.assertEqual(sum(p1), 1)

    def test_clean_and_validate_linkedin_url(self):
        # Valid profile URLs
        self.assertEqual(
            clean_and_validate_linkedin_url("https://www.linkedin.com/in/glenn-smith-12345/"),
            "https://www.linkedin.com/in/glenn-smith-12345",
        )
        self.assertEqual(
            clean_and_validate_linkedin_url("https://linkedin.com/in/johndoe?trk=public_profile&locale=en"),
            "https://www.linkedin.com/in/johndoe",
        )
        self.assertEqual(
            clean_and_validate_linkedin_url("http://www.linkedin.com/in/jane_doe_99/"),
            "https://www.linkedin.com/in/jane_doe_99",
        )

        # Invalid non-profile URLs
        self.assertIsNone(clean_and_validate_linkedin_url("https://www.linkedin.com/company/microsoft"))
        self.assertIsNone(clean_and_validate_linkedin_url("https://www.linkedin.com/jobs/view/12345678"))
        self.assertIsNone(clean_and_validate_linkedin_url("https://www.linkedin.com/school/stanford-university/"))
        self.assertIsNone(clean_and_validate_linkedin_url("https://www.linkedin.com/pulse/leadership-trends-2026/"))
        self.assertIsNone(clean_and_validate_linkedin_url("https://www.linkedin.com/feed/"))
        self.assertIsNone(clean_and_validate_linkedin_url("https://www.linkedin.com/groups/987654"))
        self.assertIsNone(clean_and_validate_linkedin_url("https://www.google.com/search?q=linkedin"))
        self.assertIsNone(clean_and_validate_linkedin_url(""))

    def test_scraper_mock_execution(self):
        mock_wrapper = MagicMock()
        mock_wrapper.run_actor.return_value = [
            {
                "organicResults": [
                    {
                        "title": "Glenn Smith, M.A. - Executive Coach & Leadership Consultant",
                        "websiteTitle": "LinkedIn · Glenn Smith",
                        "url": "https://www.linkedin.com/in/houstonbusinesscoach?trk=org",
                        "displayedUrl": "3.8K+ followers",
                        "description": "Executive coach serving Houston leaders, CEOs, and business owners.",
                        "emphasizedKeywords": ["Executive", "Coach", "Houston"],
                    },
                    {
                        "title": "Acme Corp - Leadership Consulting",
                        "websiteTitle": "LinkedIn · Acme Corp",
                        "url": "https://www.linkedin.com/company/acme-corp",
                        "displayedUrl": "linkedin.com/company/acme-corp",
                        "description": "Leading organizational consulting firm.",
                        "emphasizedKeywords": [],
                    },
                    {
                        "title": "Glenn Smith, M.A. - Duplicate Entry",
                        "websiteTitle": "LinkedIn · Glenn Smith",
                        "url": "https://www.linkedin.com/in/houstonbusinesscoach/",
                        "displayedUrl": "3.8K+ followers",
                        "description": "Duplicate result should be deduplicated.",
                        "emphasizedKeywords": [],
                    },
                ]
            }
        ]

        scraper = GoogleLinkedInScraper(apify_wrapper=mock_wrapper)
        leads = scraper.scrape_leads(niche="Executive Coach", city="Houston", total_pages=2)

        # Expected: Exactly 1 valid unique lead (company excluded, duplicate excluded)
        self.assertEqual(len(leads), 1)
        lead = leads[0]
        self.assertEqual(lead["url"], "https://www.linkedin.com/in/houstonbusinesscoach")
        self.assertEqual(lead["websiteTitle"], "LinkedIn · Glenn Smith")
        self.assertEqual(lead["displayedUrl"], "3.8K+ followers")
        self.assertIn("Houston", lead["description"])


if __name__ == "__main__":
    unittest.main()
