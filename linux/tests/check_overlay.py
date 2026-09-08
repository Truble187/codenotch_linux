"""Desktop integration check: python3 linux/tests/check_overlay.py [--scale 2].

Starts a demo overlay, checks real GTK/WebKit allocations, then closes it.
Preferences and provider credentials are neither read nor changed.
"""

import argparse
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--scale", type=int, default=1)
args = parser.parse_args()
os.environ["GDK_SCALE"] = str(args.scale)
os.environ["CODENOTCH_DEMO"] = "1"
os.environ["WEBKIT_DISABLE_COMPOSITING_MODE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codenotch.app import CodenotchApp, Gdk, GLib, Gtk, WebKit2
from codenotch.prefs import Preferences


def settle(milliseconds=700):
    loop = GLib.MainLoop()
    GLib.timeout_add(milliseconds, lambda: (loop.quit(), False)[1])
    loop.run()


def evaluate(view, script):
    loop = GLib.MainLoop()
    result = []
    errors = []

    def done(webview, task, *_):
        try:
            result.append(json.loads(webview.evaluate_javascript_finish(task).to_string()))
        except Exception as exc:
            errors.append(exc)
        finally:
            loop.quit()

    timeout = GLib.timeout_add(5000, lambda: (loop.quit(), False)[1])
    view.evaluate_javascript(script, -1, None, None, None, done, None)
    loop.run()
    if errors:
        GLib.source_remove(timeout)
        raise errors[0]
    if not result:
        raise AssertionError("WebKit did not return a measurement")
    GLib.source_remove(timeout)
    return result[0]


MEASURE = """JSON.stringify({
  viewport: [innerWidth, innerHeight],
  expanded: document.getElementById('app').dataset.expanded,
  rects: Object.fromEntries(['notch-wrap', 'orb', 'tooltip'].map(id =>
    [id, document.getElementById(id).getBoundingClientRect().toJSON()])),
  cells: [...document.querySelectorAll('.cell')].map(el => el.getBoundingClientRect().toJSON()),
  path: (() => { const r = document.getElementById('notch-path').getBBox();
    return { x:r.x, y:r.y, width:r.width, height:r.height }; })(),
  tooltipHidden: document.getElementById('tooltip').hidden
})"""


def inside(rect, width, height):
    assert rect["left"] >= -1 and rect["top"] >= -1, rect
    assert rect["right"] <= width + 1 and rect["bottom"] <= height + 1, rect


Gtk.init([])
with patch.object(Preferences, "load", return_value=Preferences()):
    app = CodenotchApp()

# Observe the actual IPC commands, including the final input region after a
# transition. This also catches dropped concurrent bridge calls.
regions = []
sizes = []
apply_regions = app.apply_input_regions
resize_overlay = app.resize_overlay


def capture_regions(rects):
    regions.append(rects)
    return apply_regions(rects)


def capture_size(width, height):
    sizes.append((width, height))
    return resize_overlay(width, height)


app.apply_input_regions = capture_regions
app.resize_overlay = capture_size

try:
    settle(1800)
    assert "X11" in Gdk.Display.get_default().__class__.__name__
    fixtures = app.usage.snapshots_json()
    for edge in ("right", "left", "top", "bottom"):
        app.prefs = Preferences(notch_edge=edge, notch_visibility="alwaysShow")
        app.position_window()
        app.emit_event("preferences-changed", app.prefs.to_dict())
        settle()
        measured = evaluate(app.webview, MEASURE)
        width, height = measured["viewport"]
        assert (width, height) == tuple(app.window.get_size())
        geo = app._monitor_geometry()
        x, y = app.window.get_position()
        notch = measured["rects"]["notch-wrap"]
        if edge == "right":
            assert abs(x + notch["right"] - (geo.x + geo.width)) <= 1
        elif edge == "left":
            assert abs(x + notch["left"] - geo.x) <= 1
        elif edge == "top":
            assert abs(y + notch["top"] - geo.y) <= 1
        else:
            assert abs(y + notch["bottom"] - (geo.y + geo.height)) <= 1
        inside(notch, width, height)
        inside(measured["rects"]["orb"], width, height)
        for cell in measured["cells"]:
            inside(cell, width, height)
        assert regions and sizes, "Layout IPC messages were lost"
        size_count = len(sizes)
        evaluate(app.webview, "window.dispatchEvent(new Event('resize')); JSON.stringify(true)")
        settle(100)
        assert len(sizes) == size_count, "Resize feedback loop"

        evaluate(app.webview, "document.querySelector('.cell').dispatchEvent(new PointerEvent('pointerenter')); JSON.stringify(true)")
        settle()
        tooltip = evaluate(app.webview, MEASURE)
        assert not tooltip["tooltipHidden"]
        inside(tooltip["rects"]["tooltip"], *tooltip["viewport"])

        app.prefs.notch_visibility = "onHover"
        app.emit_event("preferences-changed", app.prefs.to_dict())
        evaluate(app.webview, "document.getElementById('notch-wrap').dispatchEvent(new PointerEvent('pointerleave')); JSON.stringify(true)")
        settle(1100)
        folded = evaluate(app.webview, MEASURE)
        assert folded["expanded"] == "false"
        path = folded["path"]
        assert path["x"] >= -1 and path["width"] < 11, path
        evaluate(app.webview, "document.getElementById('edge-hotzone').dispatchEvent(new PointerEvent('pointerenter')); JSON.stringify(true)")
        settle()
        assert evaluate(app.webview, MEASURE)["expanded"] == "true"

        app.prefs.notch_visibility = "hidden"
        app.emit_event("preferences-changed", app.prefs.to_dict())
        settle()
        assert regions[-1] == [], "Hidden overlay intercepts clicks"
        print(f"PASS {edge}: placement, content, tooltip, fold/expand, hidden (scale {args.scale})", flush=True)

    app.prefs = Preferences(notch_edge="right", notch_visibility="alwaysShow")
    app.position_window()
    app.emit_event("preferences-changed", app.prefs.to_dict())
    for count in (1, 3, 2):
        app.emit_event("snapshots-updated", fixtures[:count])
        settle()
        measured = evaluate(app.webview, MEASURE)
        assert len(measured["cells"]) == count
        for cell in measured["cells"]:
            inside(cell, *measured["viewport"])
    print(f"PASS changing provider counts (scale {args.scale})", flush=True)
finally:
    GLib.idle_add(lambda: (app.window.destroy(), False)[1])
    Gtk.main()
