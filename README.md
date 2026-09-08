# Codenotch (Linux)

Linux-Port der macOS-App **Codenotch**: eine schwarze Kanten-Notch mit Usage-Ringen für Coding-Assistenten (Claude, Cursor, Codex). Optik und Maße folgen dem Original-Designframe [`docs/design/frame-124-hover-tooltip.png`](docs/design/frame-124-hover-tooltip.png).

Auf Ubuntu **GNOME/Wayland** läuft die App als immer-oben Overlay (kein GNOME-Shell-Extension-JS), mit derselben UI wie geplant (HTML/CSS/SVG).

## Schnellstart (empfohlen)

Voraussetzungen (Ubuntu):

```sh
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-secret-1
```

Demo mit Beispieldaten aus dem Designframe:

```sh
CODENOTCH_DEMO=1 ./linux/run.sh
```

Live-Readings (Credentials der Tools auf dem Rechner):

```sh
CODENOTCH_DEMO=0 ./linux/run.sh
```

Unter **GNOME** (Mutter) gibt es kein Layer Shell. Codenotch läuft deshalb über **XWayland** mit einem kleinen transparenten Overlay am Bildschirmrand — kein Vollbild.
Der Host wählt XWayland vor der GTK-Initialisierung, auch wenn die Sitzung `GDK_BACKEND=wayland` vorgibt.

```sh
CODENOTCH_DEMO=1 ./linux/run.sh
```

`gir1.2-gtklayershell-0.1` hilft nur auf Compositoren wie Sway/Hyprland, nicht unter GNOME.

Einstellungen: Mit der Maus über den Bereich unter der Notch fahren und auf das erscheinende Zahnrad klicken. Preferences liegen unter `~/.config/codenotch/preferences.json`. Autostart schreibt `~/.config/autostart/codenotch.desktop`.

## Was angezeigt wird

| Provider | Quelle auf Linux |
|---|---|
| **Claude** | `~/.claude/.credentials.json` bzw. Secret Service (`Claude Code-credentials`) → Anthropic OAuth `/usage` |
| **Cursor** | `~/.config/Cursor/User/globalStorage/state.vscdb` → `cursor.com/api/usage-summary` |
| **Codex** | `~/.codex/auth.json` → ChatGPT `wham/usage` |

Codenotch meldet sich nirgends selbst an — es liest nur bestehende Sessions.

Cursor zeigt die Kontingente **Cursor Models** (`autoPercentUsed`) und
**Other Models** (`apiPercentUsed`) getrennt an, auch bei 0 %. Der Ring zeigt
Cursor Models; `totalPercentUsed` dient nur als Fallback für ältere Antworten.
Prozentanzeigen werden auf ganze Zahlen gerundet, bei halben Prozenten nach oben.
Dadurch ergeben beispielsweise 6,8867 % im Cursor-Kontingent korrekt 7 %, auch
wenn die API daneben einen abweichenden Gesamtwert liefert.

Provider- und Geometrieprüfungen: `make -f Makefile.linux test`.

## Optik

- Farben: Notch `#000`, Track `#303030`, Ample `#00FF88`, Watch `#F2FF00`, Critical `#FF3F00`
- Scale `44/117` wie im Swift-Original (`Design.scale`)
- Side-Notch-Shape mit Flare/Curl, folded Pill, Hover-Tooltip, Settings-Orb
- Visibility: On hover / Always show / Hidden; Kante: rechts/links/oben/unten

UI-Dateien: [`ui/`](ui/) (`index.html`, `styles.css`, `design.js`, `main.js`, `settings.html`).

## Architektur

```
ui/                     Notch + Tooltip + Settings (pixelnahe Web-UI)
linux/codenotch/        Python-Host (GTK3 + WebKit2), Provider, Preferences
src-tauri/              Optionaler Tauri/Rust-Port derselben Architektur
Sources/                Original-Swift (macOS) als Verhaltens-/Design-Referenz
```

Der **laufende Linux-Pfad** ist der Python-Host (`./linux/run.sh`). Er lädt `ui/` in einem transparenten Always-on-top-Fenster und bridged `window.__TAURI__.core.invoke` auf die Python-Provider.

## Linux-Tests

`make -f Makefile.linux test` prüft Fenstergeometrie und Mausregionen ohne Desktop-Zugriff.
`make -f Makefile.linux test-ui` startet kurz ein Demo-Fenster und prüft mit GTK/WebKit alle vier Kanten,
Tooltips, Ein-/Ausklappen und wechselnde Provider-Anzahlen bei einfacher und doppelter Skalierung.
Der UI-Test benötigt eine laufende Desktop-Sitzung und verändert keine gespeicherten Einstellungen.

## Optional: Tauri/Rust bauen

Wenn du den Rust-Host statt Python nutzen willst:

```sh
sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev libsecret-1-dev \
  libayatana-appindicator3-dev librsvg2-dev patchelf build-essential pkg-config libssl-dev
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
cargo install tauri-cli --version "^2"
cd src-tauri
cargo tauri build
```

`CODENOTCH_DEMO=1` gilt auch dort.

## Upstream

Das Verzeichnis `Sources/` enthält weiterhin die originale macOS-Swift-App (XcodeGen / `make run` nur auf dem Mac). Dieser Repo-Zweig ist der Linux-Port.

## Lizenz

Siehe [LICENSE](LICENSE).
