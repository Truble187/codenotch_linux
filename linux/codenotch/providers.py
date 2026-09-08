from __future__ import annotations

import base64
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class NeedsAuth(Exception):
    pass


def display_name(provider_id: str) -> str:
    return {"claude": "Claude", "cursor": "Cursor", "codex": "Codex"}.get(
        provider_id, provider_id
    )


def glyph(provider_id: str) -> str:
    return {"claude": "claude", "cursor": "cursor", "codex": "openai"}.get(
        provider_id, "third"
    )


def needs_auth_stub(provider_id: str) -> dict[str, Any]:
    return {
        "id": provider_id,
        "displayName": display_name(provider_id),
        "glyph": glyph(provider_id),
        "fidelity": "official",
        "status": {"kind": "needsAuth"},
        "windows": [],
        "headlineId": None,
    }


def fixtures() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return [
        {
            "id": "claude",
            "displayName": "Claude",
            "glyph": "claude",
            "fidelity": "derived",
            "status": {"kind": "ok"},
            "headlineId": "claude.session",
            "windows": [
                {
                    "id": "claude.session",
                    "label": "Current session",
                    "usedFraction": 0.73,
                    "resetsAt": (now + timedelta(minutes=51)).isoformat(),
                },
                {
                    "id": "claude.all",
                    "label": "All models",
                    "usedFraction": 0.07,
                    "resetsAt": midnight.isoformat(),
                },
            ],
        },
        {
            "id": "codex",
            "displayName": "Codex",
            "glyph": "openai",
            "fidelity": "manual",
            "status": {"kind": "ok"},
            "headlineId": "openai.session",
            "windows": [
                {
                    "id": "openai.session",
                    "label": "Current session",
                    "usedFraction": 0.21,
                    "resetsAt": (now + timedelta(hours=3)).isoformat(),
                }
            ],
        },
        {
            "id": "cursor",
            "displayName": "Cursor",
            "glyph": "cursor",
            "fidelity": "manual",
            "status": {"kind": "ok"},
            "headlineId": "third.daily",
            "windows": [
                {
                    "id": "third.daily",
                    "label": "Included usage",
                    "usedFraction": 0.52,
                    "resetsAt": midnight.isoformat(),
                }
            ],
        },
    ]


def fetch(provider_id: str) -> dict[str, Any]:
    if provider_id == "claude":
        return fetch_claude()
    if provider_id == "cursor":
        return fetch_cursor()
    if provider_id == "codex":
        return fetch_codex()
    raise ValueError(f"unknown provider {provider_id}")


def _http_json(url: str, headers: dict[str, str]) -> Any:
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.status
            body = resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise NeedsAuth() from exc
        raise RuntimeError(f"bad response ({exc.code})") from exc
    if status in (401, 403):
        raise NeedsAuth()
    if not (200 <= status < 300):
        raise RuntimeError(f"bad response ({status})")
    return json.loads(body.decode("utf-8"))


def fetch_cursor() -> dict[str, Any]:
    path = Path.home() / ".config/Cursor/User/globalStorage/state.vscdb"
    if not path.exists():
        raise NeedsAuth()
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        def value(key: str) -> str | None:
            row = conn.execute(
                "SELECT value FROM ItemTable WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None

        token = value("cursorAuth/accessToken")
        account = value("cursorAuth/stripeMembershipAuthId")
    finally:
        conn.close()
    if not token or not account:
        raise NeedsAuth()

    cookie = f"WorkosCursorSessionToken={account}::{token}"
    root = _http_json(
        "https://cursor.com/api/usage-summary",
        {"Cookie": cookie, "Accept": "application/json"},
    )
    resets = root.get("billingCycleEnd")
    plan = (root.get("individualUsage") or {}).get("plan") or {}
    windows = []
    total = plan.get("totalPercentUsed")
    if total is not None:
        windows.append(
            {
                "id": "included",
                "label": "Included usage",
                "usedFraction": float(total) / 100.0,
                "resetsAt": resets,
            }
        )
    api = plan.get("apiPercentUsed")
    if api is not None and float(api) > 0:
        windows.append(
            {
                "id": "api",
                "label": "API usage",
                "usedFraction": float(api) / 100.0,
                "resetsAt": resets,
            }
        )
    if not windows:
        raise NeedsAuth() if root.get("membershipType") is None else RuntimeError(
            "nothing metered"
        )
    return {
        "id": "cursor",
        "displayName": "Cursor",
        "glyph": "cursor",
        "fidelity": "official",
        "status": {"kind": "ok"},
        "windows": windows,
        "headlineId": "included",
    }


def _jwt_exp(token: str) -> float | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    payload = payload.replace("-", "+").replace("_", "/")
    try:
        data = json.loads(base64.b64decode(payload))
        return float(data.get("exp"))
    except Exception:
        return None


def fetch_codex() -> dict[str, Any]:
    path = Path.home() / ".codex/auth.json"
    if not path.exists():
        raise NeedsAuth()
    auth = json.loads(path.read_text())
    tokens = auth.get("tokens") or {}
    access = tokens.get("access_token") or ""
    account = tokens.get("account_id") or ""
    if not access.strip() or not account.strip():
        raise NeedsAuth()
    exp = _jwt_exp(access)
    if exp is not None and exp <= datetime.now(timezone.utc).timestamp():
        raise NeedsAuth()

    root = _http_json(
        "https://chatgpt.com/backend-api/wham/usage",
        {
            "Authorization": f"Bearer {access}",
            "ChatGPT-Account-Id": account,
            "Accept": "application/json",
            "Cache-Control": "no-cache, no-store",
        },
    )
    rate = root.get("rate_limit") or {}
    now = datetime.now(timezone.utc)
    windows = []
    for key, wid in (("primary_window", "primary"), ("secondary_window", "secondary")):
        window = rate.get(key)
        if not window:
            continue
        percent = window.get("used_percent")
        if percent is None:
            continue
        resets_at = None
        if window.get("reset_at") is not None:
            resets_at = datetime.fromtimestamp(window["reset_at"], tz=timezone.utc).isoformat()
        elif window.get("reset_after_seconds") is not None:
            resets_at = (now + timedelta(seconds=window["reset_after_seconds"])).isoformat()
        seconds = float(window.get("limit_window_seconds") or 0)
        minutes = seconds / 60 if seconds else 0
        if minutes and minutes < 60:
            label = f"{int(minutes)}m limit"
        elif minutes and minutes < 60 * 24:
            label = f"{int(minutes / 60)}h limit"
        else:
            days = round(minutes / (60 * 24)) if minutes else 0
            label = {7: "Weekly limit", 30: "Monthly limit"}.get(days, f"{days}d limit" if days else ("Current session" if wid == "primary" else "Longer window"))
        windows.append(
            {
                "id": wid,
                "label": label,
                "usedFraction": float(percent) / 100.0,
                "resetsAt": resets_at,
            }
        )
    if not windows:
        raise RuntimeError("Codex reported no usage windows")
    return {
        "id": "codex",
        "displayName": "Codex",
        "glyph": "openai",
        "fidelity": "official",
        "status": {"kind": "ok"},
        "windows": windows,
        "headlineId": windows[0]["id"],
    }


def _claude_token_from_files() -> str | None:
    candidates = [
        Path.home() / ".claude/.credentials.json",
        Path.home() / ".claude/credentials.json",
        Path.home() / ".config/claude/credentials.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except Exception:
            continue
        oauth = data.get("claudeAiOauth") or {}
        token = oauth.get("accessToken")
        if token:
            return token
    return None


def _claude_token_from_secret_service() -> str | None:
    try:
        import gi

        gi.require_version("Secret", "1")
        from gi.repository import Secret
    except Exception:
        return None

    for service in ("Claude Code-credentials", "claude-code", "Claude Code"):
        attrs = {"service": service}
        for item in Secret.password_search_sync(None, attrs, Secret.SearchFlags.LOAD_SECRETS):
            secret = item.get_secret()
            if not secret:
                continue
            text = secret.get().decode("utf-8", errors="ignore")
            try:
                data = json.loads(text)
                token = (data.get("claudeAiOauth") or {}).get("accessToken")
                if token:
                    return token
            except Exception:
                continue
    return None


def fetch_claude() -> dict[str, Any]:
    token = _claude_token_from_files() or _claude_token_from_secret_service()
    if not token:
        raise NeedsAuth()
    root = _http_json(
        "https://api.anthropic.com/api/oauth/usage",
        {
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
        },
    )
    windows = []
    for limit in root.get("limits") or []:
        kind = limit.get("kind")
        if not kind or limit.get("resetsAt") is None:
            continue
        label = {
            "session": "Current session",
            "weekly_all": "All models",
            "weekly_opus": "Opus",
            "weekly_sonnet": "Sonnet",
        }.get(kind, kind.replace("weekly_", "").replace("_", " "))
        windows.append(
            {
                "id": kind,
                "label": label,
                "usedFraction": float(limit.get("percent", 0)) / 100.0,
                "resetsAt": limit.get("resetsAt"),
            }
        )

    def merge(named: dict | None, wid: str, label: str):
        if not named or named.get("resetsAt") is None:
            return
        if any(w["id"] == wid for w in windows):
            return
        windows.append(
            {
                "id": wid,
                "label": label,
                "usedFraction": float(named.get("utilization", 0)) / 100.0,
                "resetsAt": named.get("resetsAt"),
            }
        )

    merge(root.get("fiveHour"), "session", "Current session")
    merge(root.get("sevenDay"), "weekly_all", "All models")
    windows.sort(key=lambda w: 0 if w["id"] == "session" else 1 if w["id"] == "weekly_all" else 2)
    if not windows:
        raise RuntimeError("Claude reported no usage windows")
    return {
        "id": "claude",
        "displayName": "Claude",
        "glyph": "claude",
        "fidelity": "official",
        "status": {"kind": "ok"},
        "windows": windows,
        "headlineId": "session",
    }
