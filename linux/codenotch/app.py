"""Codenotch Linux host — transparent edge overlay for GNOME (XWayland)."""

from __future__ import annotations

import json
import math
import os
import signal
import sys
import threading
import time
from pathlib import Path

# Select the backend before importing GTK: importing/probing layer-shell can
# already open the display. GNOME sessions often export GDK_BACKEND=wayland.
if "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "").upper().split(":"):
    os.environ["GDK_BACKEND"] = "x11"
else:
    os.environ.setdefault("GDK_BACKEND", "x11")

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("WebKit2", "4.1")

from gi.repository import Gdk, GLib, Gtk, WebKit2

try:
    import cairo
except ImportError:
    cairo = None  # type: ignore

from . import store
from .prefs import Preferences

ROOT = Path(__file__).resolve().parents[2]
UI_DIR = ROOT / "ui"

# Mutter (GNOME) does not implement wlr-layer-shell. Only use it when the
# compositor actually supports it (Sway/Hyprland/etc.).
HAS_LAYER_SHELL = False
GtkLayerShell = None  # type: ignore
try:
    gi.require_version("GtkLayerShell", "0.1")
    from gi.repository import GtkLayerShell as _GtkLayerShell

    if _GtkLayerShell.is_supported():
        GtkLayerShell = _GtkLayerShell
        HAS_LAYER_SHELL = True
except (ValueError, ImportError, AttributeError):
    pass

BRIDGE_JS = r"""
(function () {
  const pending = new Map();
  let seq = 0;
  function invoke(cmd, args) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, { resolve, reject });
      window.webkit.messageHandlers.codenotch.postMessage(JSON.stringify({ id, cmd, args: args || {} }));
    });
  }
  window.__codenotchResolve = function (id, ok, payload) {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    if (ok) p.resolve(payload);
    else p.reject(new Error(payload || 'error'));
  };
  window.__codenotchEvent = function (name, payload) {
    window.dispatchEvent(new CustomEvent('codenotch-event', { detail: { name, payload } }));
  };
  window.__TAURI__ = {
    core: { invoke },
    event: {
      listen: async function (name, handler) {
        const listener = (ev) => {
          if (ev.detail.name === name) handler({ payload: ev.detail.payload });
        };
        window.addEventListener('codenotch-event', listener);
        return () => window.removeEventListener('codenotch-event', listener);
      }
    }
  };
})();
"""


class Bridge:
    def __init__(self, app: "CodenotchApp"):
        self.app = app

    def handle(self, method: str, params: dict):
        if method == "get_snapshots":
            return self.app.usage.snapshots_json()
        if method == "get_preferences":
            return self.app.prefs.to_dict()
        if method == "set_preferences":
            prefs = Preferences.from_dict(params.get("prefs") or params)
            prefs.set_autostart(prefs.launch_at_login)
            prefs.save()
            self.app.prefs = prefs
            self.app.usage.set_prefs(prefs)
            GLib.idle_add(self.app.position_window)
            GLib.idle_add(self.app.emit_event, "preferences-changed", prefs.to_dict())
            return None
        if method == "refresh_all":
            self.app.usage.refresh_all()
            snaps = self.app.usage.snapshots_json()
            GLib.idle_add(self.app.emit_event, "snapshots-updated", snaps)
            return snaps
        if method == "refresh_provider":
            self.app.usage.refresh_one(params.get("id", ""))
            snaps = self.app.usage.snapshots_json()
            GLib.idle_add(self.app.emit_event, "snapshots-updated", snaps)
            return None
        if method == "open_settings":
            GLib.idle_add(self.app.open_settings)
            return None
        if method == "set_input_regions":
            GLib.idle_add(self.app.apply_input_regions, params.get("rects") or [])
            return None
        if method == "set_overlay_size":
            GLib.idle_add(
                self.app.resize_overlay,
                int(params.get("width") or 0),
                int(params.get("height") or 0),
            )
            return None
        raise ValueError(f"unknown method {method}")


class CodenotchApp:
    def __init__(self):
        self.demo = os.environ.get("CODENOTCH_DEMO") == "1"
        self.prefs = Preferences.load()
        self.usage = store.UsageStore(self.prefs, demo=self.demo)
        self.bridge = Bridge(self)
        self.settings_win = None
        self._views: list[WebKit2.WebView] = []
        self._using_layer_shell = False
        self._overlay_w = 420
        self._overlay_h = 720

        self.window = Gtk.Window(title="Codenotch")
        self.window.set_decorated(False)
        self.window.set_keep_above(True)
        self.window.set_skip_taskbar_hint(True)
        self.window.set_skip_pager_hint(True)
        self.window.set_app_paintable(True)
        self.window.set_accept_focus(False)
        self.window.set_resizable(False)
        self.window.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.window.connect("destroy", Gtk.main_quit)
        self.window.connect("map-event", self._on_mapped)
        self.window.connect("draw", self._on_draw)
        self.window.connect("screen-changed", self._on_screen_changed)

        self._set_rgba_visual(self.window.get_screen())

        # Transparent Gtk chrome around the WebView.
        css = Gtk.CssProvider()
        css.load_from_data(
            b"""
            window, * {
              background-color: transparent;
              background-image: none;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.webview = self._make_webview()
        self.window.add(self.webview)

        if HAS_LAYER_SHELL:
            self._init_layer_shell()
        else:
            self.position_window()

        self.window.show_all()
        self.webview.load_uri((UI_DIR / "index.html").as_uri())
        GLib.idle_add(self.position_window)
        GLib.timeout_add(250, self.position_window)
        GLib.timeout_add(800, self.position_window)

        threading.Thread(target=self._poll_loop, daemon=True).start()

    def _on_screen_changed(self, window, _previous_screen=None):
        self._set_rgba_visual(window.get_screen())

    def _set_rgba_visual(self, screen) -> None:
        if screen is None:
            return
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.window.set_visual(visual)

    def _on_draw(self, _widget, cr):
        # Clear to fully transparent — otherwise GTK paints an opaque black panel.
        if cairo is None:
            return False
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        return False

    def _init_layer_shell(self) -> None:
        assert GtkLayerShell is not None
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.TOP)
        GtkLayerShell.set_namespace(self.window, "codenotch")
        GtkLayerShell.set_exclusive_zone(self.window, 0)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.NONE)
        self._using_layer_shell = True
        self._apply_layer_anchors()

    def _apply_layer_anchors(self) -> None:
        if not self._using_layer_shell or GtkLayerShell is None:
            return
        edge = self.prefs.notch_edge
        for e in (
            GtkLayerShell.Edge.LEFT,
            GtkLayerShell.Edge.RIGHT,
            GtkLayerShell.Edge.TOP,
            GtkLayerShell.Edge.BOTTOM,
        ):
            GtkLayerShell.set_anchor(self.window, e, False)
        if edge == "right":
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.RIGHT, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.BOTTOM, True)
            self.window.set_size_request(self._overlay_w, -1)
        elif edge == "left":
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.BOTTOM, True)
            self.window.set_size_request(self._overlay_w, -1)
        elif edge == "top":
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.TOP, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.RIGHT, True)
            self.window.set_size_request(-1, self._overlay_h)
        else:
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.LEFT, True)
            GtkLayerShell.set_anchor(self.window, GtkLayerShell.Edge.RIGHT, True)
            self.window.set_size_request(-1, self._overlay_h)

    def _make_webview(self) -> WebKit2.WebView:
        webview = WebKit2.WebView()
        settings = webview.get_settings()
        settings.set_enable_developer_extras(True)
        settings.set_allow_file_access_from_file_urls(True)
        settings.set_allow_universal_access_from_file_urls(True)
        # Helps some WebKitGTK builds keep pages transparent.
        try:
            settings.set_property("enable-back-forward-navigation-gestures", False)
        except Exception:
            pass
        transparent = Gdk.RGBA(red=0, green=0, blue=0, alpha=0)
        webview.set_background_color(transparent)
        webview.set_app_paintable(True)
        self._inject_bridge(webview)
        manager = webview.get_user_content_manager()
        manager.connect("script-message-received::codenotch", self._on_script_message, webview)
        manager.register_script_message_handler("codenotch")
        self._views.append(webview)
        return webview

    def _inject_bridge(self, webview: WebKit2.WebView) -> None:
        script = WebKit2.UserScript.new(
            BRIDGE_JS,
            WebKit2.UserContentInjectedFrames.TOP_FRAME,
            WebKit2.UserScriptInjectionTime.START,
            None,
            None,
        )
        webview.get_user_content_manager().add_script(script)

    def _on_script_message(self, _manager, result, webview):
        # Unlike navigation URLs, messages sent in the same frame cannot cancel
        # each other (layout sends both the size and the input region).
        try:
            msg = json.loads(result.get_js_value().to_string())
        except Exception as exc:
            print("bad bridge payload", exc, file=sys.stderr)
            return

        def work():
            try:
                result = self.bridge.handle(msg["cmd"], msg.get("args") or {})
                payload = json.dumps(result)
                ok = "true"
            except Exception as exc:
                payload = json.dumps(str(exc))
                ok = "false"
            script = f"window.__codenotchResolve({msg['id']}, {ok}, {payload});"
            GLib.idle_add(webview.run_javascript, script, None, None, None)

        threading.Thread(target=work, daemon=True).start()

    def emit_event(self, name, payload):
        script = f"window.__codenotchEvent({json.dumps(name)}, {json.dumps(payload)});"
        for view in self._views:
            try:
                view.run_javascript(script, None, None, None)
            except Exception:
                pass
        return False

    def _on_mapped(self, *_args):
        self.position_window()
        return False

    def _monitor_geometry(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        try:
            return monitor.get_workarea()
        except Exception:
            return monitor.get_geometry()

    def resize_overlay(self, width: int, height: int) -> bool:
        if width > 40 and height > 40:
            if (width, height) != (self._overlay_w, self._overlay_h):
                self._overlay_w = width
                self._overlay_h = height
                self.position_window()
        return False

    def position_window(self):
        if self._using_layer_shell:
            self._apply_layer_anchors()
            return False

        geo = self._monitor_geometry()
        edge = self.prefs.notch_edge
        w = min(self._overlay_w, geo.width)
        h = min(self._overlay_h, geo.height)

        if edge == "right":
            x = geo.x + geo.width - w
            y = geo.y + max(0, (geo.height - h) // 2)
        elif edge == "left":
            x = geo.x
            y = geo.y + max(0, (geo.height - h) // 2)
        elif edge == "top":
            x = geo.x + max(0, (geo.width - w) // 2)
            y = geo.y
        else:
            x = geo.x + max(0, (geo.width - w) // 2)
            y = geo.y + geo.height - h

        self.window.set_gravity(Gdk.Gravity.NORTH_WEST)
        # A non-resizable GtkWindow takes its size from the widget requisition.
        # Keep GTK's allocation in sync instead of resizing its GdkWindow below it.
        self.window.set_size_request(w, h)
        self.window.resize(w, h)
        self.window.move(x, y)
        return False

    def apply_input_regions(self, rects: list) -> bool:
        if cairo is None:
            return False
        gdk_win = self.window.get_window()
        if gdk_win is None:
            return False
        # DOM and GDK both use logical pixels; GDK applies the display scale.
        region = cairo.Region()
        for r in rects:
            x, y = math.floor(r["x"]), math.floor(r["y"])
            right, bottom = math.ceil(r["x"] + r["w"]), math.ceil(r["y"] + r["h"])
            if right > x and bottom > y:
                region.union(cairo.RectangleInt(x, y, right - x, bottom - y))
        gdk_win.input_shape_combine_region(region, 0, 0)
        # The alpha channel defines the visible shape. A visual mask here would
        # clip the background/shadows and retain stale bounds during animations.
        return False

    def open_settings(self):
        if self.settings_win:
            self.settings_win.present()
            return False
        win = Gtk.Window(title="Codenotch Settings")
        win.set_default_size(420, 560)
        view = self._make_webview()
        win.add(view)
        win.connect(
            "destroy",
            lambda *_: (
                self._views.remove(view) if view in self._views else None,
                setattr(self, "settings_win", None),
            ),
        )
        view.load_uri((UI_DIR / "settings.html").as_uri())
        win.show_all()
        self.settings_win = win
        return False

    def _poll_loop(self):
        self.usage.refresh_all()
        GLib.idle_add(self.emit_event, "snapshots-updated", self.usage.snapshots_json())
        while True:
            time.sleep(60)
            self.usage.refresh_all()
            GLib.idle_add(self.emit_event, "snapshots-updated", self.usage.snapshots_json())


def main():
    # Reduce WebKitGTK opaque compositing glitches on transparent windows.
    os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")

    Gtk.init(sys.argv)

    def _quit(*_args):
        Gtk.main_quit()
        return GLib.SOURCE_REMOVE

    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, _quit)
    try:
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, _quit)
    except Exception:
        pass

    if not HAS_LAYER_SHELL:
        print(
            "Codenotch: GNOME/Mutter hat kein Layer Shell — nutze XWayland-Overlay.",
            file=sys.stderr,
        )

    CodenotchApp()
    try:
        Gtk.main()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
