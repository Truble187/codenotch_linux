"""Scale preferences remain compatible with existing configuration files."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codenotch import prefs


class ScalePreferencesTests(unittest.TestCase):
    def test_existing_settings_keep_original_size(self):
        settings = prefs.Preferences.from_dict({"notchEdge": "left"})
        self.assertEqual(settings.notch_scale, 1)
        self.assertEqual(settings.notch_edge, "left")

    def test_scale_survives_save_and_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(prefs, "CONFIG_DIR", root), patch.object(
                prefs, "PREFS_PATH", root / "preferences.json"
            ):
                prefs.Preferences(notch_scale=1.25).save()
                self.assertEqual(prefs.Preferences.load().notch_scale, 1.25)

    def test_invalid_and_out_of_range_values(self):
        for value, expected in [(None, 1), ("bad", 1), (float("nan"), 1),
                                (float("inf"), 1), (0, .75), (10, 1.5)]:
            with self.subTest(value=value):
                self.assertEqual(
                    prefs.Preferences.from_dict({"notchScale": value}).notch_scale,
                    expected,
                )
