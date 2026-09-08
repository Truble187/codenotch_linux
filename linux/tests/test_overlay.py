"""Host geometry regressions; no desktop connection required."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codenotch.app import CodenotchApp


class OverlayGeometryTests(unittest.TestCase):
    def setUp(self):
        self.app = CodenotchApp.__new__(CodenotchApp)
        self.app.window = Mock()
        self.app.prefs = SimpleNamespace(notch_edge="right")
        self.app._using_layer_shell = False
        self.app._overlay_w = 371
        self.app._overlay_h = 487
        self.app._monitor_geometry = Mock(
            return_value=SimpleNamespace(x=1920, y=32, width=2560, height=1408)
        )

    def test_edges_on_monitor_with_nonzero_origin(self):
        for edge, position in {
            "right": (4109, 492),
            "left": (1920, 492),
            "top": (3014, 32),
            "bottom": (3014, 953),
        }.items():
            with self.subTest(edge=edge):
                self.app.prefs.notch_edge = edge
                self.app.position_window()
                self.app.window.move.assert_called_with(*position)
                self.app.window.set_size_request.assert_called_with(371, 487)
                self.app.window.resize.assert_called_with(371, 487)
        self.app.window.get_window.assert_not_called()

    def test_size_reports_do_not_accumulate_padding(self):
        self.app.position_window = Mock()
        for _ in range(10):
            self.app.resize_overlay(420, 600)
        self.assertEqual((self.app._overlay_w, self.app._overlay_h), (420, 600))
        self.app.position_window.assert_called_once()
        self.app.resize_overlay(371, 487)
        self.assertEqual((self.app._overlay_w, self.app._overlay_h), (371, 487))

    def test_size_is_limited_to_monitor(self):
        self.app.resize_overlay(3000, 2000)
        self.app.window.set_size_request.assert_called_with(2560, 1408)
        self.app.window.move.assert_called_with(1920, 32)

    def test_input_mask_uses_logical_coordinates_without_clipping_visuals(self):
        native = self.app.window.get_window.return_value
        native.get_scale_factor.return_value = 2
        self.app.apply_input_regions([{"x": 10.5, "y": 20.5, "w": 30, "h": 40}])
        region, x, y = native.input_shape_combine_region.call_args.args
        self.assertEqual((x, y), (0, 0))
        self.assertTrue(region.contains_point(10, 20))
        self.assertTrue(region.contains_point(40, 60))
        self.assertFalse(region.contains_point(41, 61))
        native.shape_combine_region.assert_not_called()

    def test_hidden_overlay_passes_all_input_through(self):
        self.app.apply_input_regions([])
        native = self.app.window.get_window.return_value
        region = native.input_shape_combine_region.call_args.args[0]
        self.assertTrue(region.is_empty())


if __name__ == "__main__":
    unittest.main()
