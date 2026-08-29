"""
Unit Tests for Phase 3: posts_checker.py
"""

import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from posts_checker import (
    parse_post_date,
    extract_profile_url_from_post,
    PostsChecker,
)


class TestPhase3PostsChecker(unittest.TestCase):

    def test_parse_post_date(self):
        # ISO string with Z
        dt1 = parse_post_date("2026-08-15T18:11:59.821Z")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 8)
        self.assertEqual(dt1.day, 15)

        # Dict with 'date'
        dt2 = parse_post_date({"date": "2026-08-20T10:00:00Z"})
        self.assertIsNotNone(dt2)
        self.assertEqual(dt2.day, 20)

        # Millisecond timestamp
        dt3 = parse_post_date(1787000000000)
        self.assertIsNotNone(dt3)

        # Invalid formats
        self.assertIsNone(parse_post_date(None))
        self.assertIsNone(parse_post_date(""))
        self.assertIsNone(parse_post_date("invalid-date-string"))

    def test_extract_profile_url_from_post(self):
        item1 = {"targetUrl": "https://www.linkedin.com/in/glennsmith/"}
        self.assertEqual(extract_profile_url_from_post(item1), "https://www.linkedin.com/in/glennsmith")

        item2 = {"author": {"profileUrl": "https://linkedin.com/in/johndoe?trk=post"}}
        self.assertEqual(extract_profile_url_from_post(item2), "https://www.linkedin.com/in/johndoe")

        item3 = {"author": {"url": "https://www.linkedin.com/company/somecorp"}}
        self.assertIsNone(extract_profile_url_from_post(item3))

    def test_activity_threshold_filtering(self):
        now = datetime(2026, 8, 28, 12, 0, 0, tzinfo=timezone.utc)
        mock_wrapper = MagicMock()

        # Mock posts dataset:
        # Profile 1: active post 2 days ago (2026-08-26) -> KEEP
        # Profile 2: active post 10 days ago (2026-08-18) -> KEEP
        # Profile 3: old post 20 days ago (2026-08-08) -> REMOVE
        # Profile 4: no posts in dataset -> REMOVE
        mock_wrapper.run_actor.return_value = [
            {
                "targetUrl": "https://www.linkedin.com/in/active-coach-1",
                "postedAt": {"date": "2026-08-26T12:00:00Z"},
            },
            {
                "targetUrl": "https://www.linkedin.com/in/active-coach-2",
                "postedAt": {"date": "2026-08-18T10:00:00Z"},
            },
            {
                "targetUrl": "https://www.linkedin.com/in/inactive-coach-3",
                "postedAt": {"date": "2026-08-08T08:00:00Z"},
            },
        ]

        urls_to_check = [
            "https://www.linkedin.com/in/active-coach-1",
            "https://www.linkedin.com/in/active-coach-2",
            "https://www.linkedin.com/in/inactive-coach-3",
            "https://www.linkedin.com/in/no-posts-coach-4",
        ]

        checker = PostsChecker(apify_wrapper=mock_wrapper)
        active_results = checker.check_activity(urls_to_check, now_dt=now)

        self.assertEqual(len(active_results), 2)
        urls_active = [r["url"] for r in active_results]
        self.assertIn("https://www.linkedin.com/in/active-coach-1", urls_active)
        self.assertIn("https://www.linkedin.com/in/active-coach-2", urls_active)
        self.assertNotIn("https://www.linkedin.com/in/inactive-coach-3", urls_active)
        self.assertNotIn("https://www.linkedin.com/in/no-posts-coach-4", urls_active)


if __name__ == "__main__":
    unittest.main()
