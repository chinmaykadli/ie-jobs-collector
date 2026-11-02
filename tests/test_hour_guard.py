import datetime as dt
import unittest
from scripts.hour_guard import already_published


class HourGuardTest(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 2, 23, 37, tzinfo=dt.timezone.utc)

    def test_same_hour_skips(self):
        self.assertTrue(already_published({'checked_at': '2026-11-02T23:01:00+00:00'}, self.now))

    def test_previous_hour_collects(self):
        self.assertFalse(already_published({'checked_at': '2026-11-02T22:59:59Z'}, self.now))

    def test_offset_normalized(self):
        self.assertTrue(already_published({'checked_at': '2026-11-03T00:05:00+01:00'}, self.now))

    def test_previous_day_collects(self):
        self.assertFalse(already_published({'checked_at': '2026-11-01T23:37:00Z'}, self.now))

    def test_future_hour_does_not_suppress(self):
        self.assertFalse(already_published({'checked_at': '2026-11-03T00:00:00Z'}, self.now))

    def test_bad_or_missing_metadata_collects(self):
        for data in ({}, {'checked_at': 'bad'}, {'checked_at': None}, {'checked_at': '2026-11-02T23:01:00'}):
            with self.subTest(data=data):
                self.assertFalse(already_published(data, self.now))
