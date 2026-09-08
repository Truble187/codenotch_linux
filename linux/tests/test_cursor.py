"""Cursor dashboard pool selection and display regressions."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codenotch.providers import _cursor_snapshot
from codenotch.store import enrich


class CursorUsageTests(unittest.TestCase):
    def snapshot(self, plan):
        return enrich(_cursor_snapshot({
            "billingCycleEnd": "2026-09-11T07:45:00Z",
            "individualUsage": {"plan": plan},
        }))

    def test_live_pool_values_match_dashboard(self):
        result = self.snapshot({
            "autoPercentUsed": 6.886666666666668,
            "apiPercentUsed": 0,
            "totalPercentUsed": 6.260606060606061,
        })
        self.assertEqual(result["headlineText"], "7%")
        cursor, other = result["windows"]
        self.assertEqual(cursor["label"], "Cursor Models")
        self.assertEqual(cursor["summary"], "7% Used · 93% left")
        self.assertEqual(other["label"], "Other Models")
        self.assertEqual(other["summary"], "0% Used · 100% left")
        self.assertEqual(other["resetsAt"], cursor["resetsAt"])

    def test_zero_cursor_pool_does_not_fall_back_to_total(self):
        result = self.snapshot({"autoPercentUsed": 0, "totalPercentUsed": 19})
        self.assertEqual(result["headlineText"], "0%")

    def test_legacy_total_and_missing_other_pool(self):
        result = self.snapshot({"totalPercentUsed": 9.5})
        self.assertEqual(result["headlineText"], "10%")
        self.assertEqual(len(result["windows"]), 1)
        self.assertEqual(result["windows"][0]["label"], "Included usage")

    def test_half_percent_rounds_up_in_headline_and_tooltip(self):
        result = self.snapshot({"autoPercentUsed": 6.5, "apiPercentUsed": 2.5})
        self.assertEqual(result["headlineText"], "7%")
        self.assertEqual(result["windows"][0]["summary"], "7% Used · 93% left")
        self.assertEqual(result["windows"][1]["summary"], "3% Used · 97% left")


if __name__ == "__main__":
    unittest.main()
