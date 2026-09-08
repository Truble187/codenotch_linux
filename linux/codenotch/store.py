from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import providers
from .prefs import Preferences


def band_color(used_fraction: float) -> str:
    if used_fraction < 0.50:
        return "#00FF88"
    if used_fraction < 0.70:
        return "#F2FF00"
    return "#FF3F00"


def reset_copy(resets_at: datetime | None, now: datetime | None = None) -> str | None:
    if not resets_at:
        return None
    now = now or datetime.now(timezone.utc)
    if resets_at.tzinfo is None:
        resets_at = resets_at.replace(tzinfo=timezone.utc)
    seconds = (resets_at - now).total_seconds()
    if seconds <= 0:
        return "Resetting…"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"Resets in {max(1, minutes)} min"
    days = (resets_at.date() - now.date()).days
    if days >= 7:
        return f"Resets {resets_at.strftime('%b %-d')}"
    return f"Resets {resets_at.strftime('%a %-I:%M %p')}"


def enrich(snapshot: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    windows = []
    for w in snapshot.get("windows") or []:
        frac = w.get("usedFraction")
        item = dict(w)
        if frac is not None:
            used = round(frac * 100)
            item["summary"] = f"{used}% Used · {max(0, 100 - used)}% left"
            item["bandColor"] = band_color(frac)
        else:
            item["summary"] = w.get("summary") or "No reading"
        resets = w.get("resetsAt")
        if isinstance(resets, str):
            try:
                resets_dt = datetime.fromisoformat(resets.replace("Z", "+00:00"))
            except ValueError:
                resets_dt = None
        elif isinstance(resets, datetime):
            resets_dt = resets
        else:
            resets_dt = None
        item["resetCopy"] = reset_copy(resets_dt, now)
        windows.append(item)

    headline_id = snapshot.get("headlineId")
    headline = None
    if headline_id:
        headline = next((w for w in windows if w.get("id") == headline_id), None)
    if headline is None and windows:
        headline = windows[0]

    used = headline.get("usedFraction") if headline else None
    if used is not None:
        headline_text = f"{round(used * 100)}%"
    else:
        headline_text = "—"

    status = snapshot.get("status") or {"kind": "ok"}
    return {
        "id": snapshot["id"],
        "displayName": snapshot["displayName"],
        "glyph": snapshot["glyph"],
        "fidelity": snapshot.get("fidelity", "official"),
        "status": status,
        "windows": windows,
        "headlineId": headline_id,
        "headlineText": headline_text,
        "usedFraction": used,
        "bandColor": band_color(used) if used is not None else "#303030",
        "hasReading": bool(windows),
        "stale": status.get("kind") == "stale",
    }


class UsageStore:
    def __init__(self, prefs: Preferences, demo: bool = False):
        self.prefs = prefs
        self.demo = demo
        self.snapshots: list[dict[str, Any]] = providers.fixtures() if demo else []

    def set_prefs(self, prefs: Preferences) -> None:
        self.prefs = prefs

    def snapshots_json(self) -> list[dict[str, Any]]:
        return [enrich(s) for s in self.snapshots]

    def refresh_all(self) -> None:
        if self.demo:
            self.snapshots = providers.fixtures()
            return
        next_snaps: list[dict[str, Any]] = []
        for provider_id in ("claude", "cursor", "codex"):
            if not self.prefs.is_connected(provider_id):
                continue
            try:
                next_snaps.append(providers.fetch(provider_id))
            except providers.NeedsAuth:
                next_snaps.append(providers.needs_auth_stub(provider_id))
            except Exception as exc:
                next_snaps.append(
                    {
                        "id": provider_id,
                        "displayName": providers.display_name(provider_id),
                        "glyph": providers.glyph(provider_id),
                        "fidelity": "official",
                        "status": {"kind": "error", "message": str(exc)},
                        "windows": [],
                        "headlineId": None,
                    }
                )
        self.snapshots = next_snaps

    def refresh_one(self, provider_id: str) -> None:
        if self.demo or not self.prefs.is_connected(provider_id):
            return
        try:
            snap = providers.fetch(provider_id)
        except Exception:
            return
        for i, existing in enumerate(self.snapshots):
            if existing["id"] == provider_id:
                self.snapshots[i] = snap
                return
        self.snapshots.append(snap)
