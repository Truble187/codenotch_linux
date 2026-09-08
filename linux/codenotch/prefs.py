from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


CONFIG_DIR = Path.home() / ".config" / "codenotch"
PREFS_PATH = CONFIG_DIR / "preferences.json"


@dataclass
class Preferences:
    disconnected_providers: list[str] = field(default_factory=list)
    notch_visibility: str = "onHover"
    notch_edge: str = "right"
    launch_at_login: bool = False

    @classmethod
    def load(cls) -> "Preferences":
        if not PREFS_PATH.exists():
            return cls()
        try:
            data = json.loads(PREFS_PATH.read_text())
            return cls.from_dict(data)
        except Exception:
            return cls()

    @classmethod
    def from_dict(cls, data: dict) -> "Preferences":
        return cls(
            disconnected_providers=list(data.get("disconnectedProviders") or []),
            notch_visibility=data.get("notchVisibility") or "onHover",
            notch_edge=data.get("notchEdge") or "right",
            launch_at_login=bool(data.get("launchAtLogin")),
        )

    def to_dict(self) -> dict:
        return {
            "disconnectedProviders": self.disconnected_providers,
            "notchVisibility": self.notch_visibility,
            "notchEdge": self.notch_edge,
            "launchAtLogin": self.launch_at_login,
        }

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        PREFS_PATH.write_text(json.dumps(self.to_dict(), indent=2))

    def is_connected(self, provider_id: str) -> bool:
        return provider_id not in self.disconnected_providers

    def set_autostart(self, enabled: bool) -> None:
        self.launch_at_login = enabled
        autostart = Path.home() / ".config" / "autostart"
        desktop = autostart / "codenotch.desktop"
        if enabled:
            autostart.mkdir(parents=True, exist_ok=True)
            root = Path(__file__).resolve().parents[2]
            exec_line = f"{Path(sys_executable())} -m codenotch"
            # Prefer repo launcher script when developing from source.
            launcher = root / "linux" / "run.sh"
            if launcher.exists():
                exec_line = str(launcher)
            desktop.write_text(
                "[Desktop Entry]\n"
                "Type=Application\n"
                "Name=Codenotch\n"
                "Comment=Coding assistant usage notch\n"
                f"Exec={exec_line}\n"
                "Icon=codenotch\n"
                "Terminal=false\n"
                "X-GNOME-Autostart-enabled=true\n"
            )
        elif desktop.exists():
            desktop.unlink()


def sys_executable() -> str:
    import sys

    return sys.executable
