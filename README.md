# KidBox

**KidBox** is a minimalist, offline-first Linux "kid mode" designed for very young children.
By default it boots into a fullscreen launcher with three large buttons:

- **Paint**
- **Photos**
- **Typing**

There is no desktop environment visible, no file browser, no login/logout flow, and no network dependency during normal use. The system is intentionally constrained, predictable, and robust against accidental input, while remaining easy for a parent to administer and extend.

This is not a general-purpose “kids OS.”
It is a small, comprehensible appliance built on top of Ubuntu.

---

## Design Goals

- **Appliance-like UX**
  - Power on -> launcher -> activity
  - No system UI exposed
- **Touch-first**
  - Large hit targets
  - No right-clicks, menus, or dialogs
- **Safe by construction**
  - Autosave everywhere
  - Undo everywhere
  - "New" never destroys work
- **Offline by default**
  - No network dependency during normal use
- **Parent-controlled escape**
  - Hidden keyboard chord drops back to GNOME
- **Grow-with-the-child**
  - Built-in apps run in-process for smooth transitions
  - Non-built-in apps can still be launched via subprocess fallback
  - Full desktop can be re-enabled later without reinstalling

---

## High-level Architecture

```
┌────────────────────────────┐
│           KidBox           │
│  (Fullscreen Launcher)     │
│                            │
│  [ Paint ] [ Photos ]      │
│          [ Typing ]        │
│                            │
└─────────────┬──────────────┘
              │ switches scenes in-process
┌─────────────▼──────────────┐
│      Embedded App Views    │
│  - Paint                   │
│  - Photos                  │
│  - Typing                  │
│                            │
│  Fullscreen, no chrome     │
│  Exit = return to launcher │
└────────────────────────────┘

Underlying system:
- Ubuntu (GNOME installed but hidden)
- Python 3
- pygame-ce / SDL
```

The launcher supervises apps. Apps exit cleanly back to the launcher. If an app crashes, the launcher simply reappears.

---

## Components

### Launcher

- Fullscreen home screen with three icons
- Runs built-in apps in-process (`paint`, `photos`, `typing`)
- Subprocess fallback for non-built-in commands in config
- No clickable "exit" control on-screen
- Ignores function keys (`F1`-`F12`)
- **Parent escape chord:** `Ctrl + Alt + Home`
  - Exits the launcher and reveals GNOME

### Paint App

- Free drawing canvas
- Tools:
  - Round brush
  - Fountain pen (direction-sensitive width)
  - Eraser
  - Bucket fill
- 3 line-size options (small/medium/large)
- 13-color palette (configurable)
- Stroke-based undo (default depth: 10)
- Autosave + archive on "New"
- Recall overlay in the left tools panel:
  - First item is the current live canvas
  - Older archives below in a vertical scroll list
  - Tap outside recall closes it

### Photos App

- Photo library viewer
- Main image area + always-visible thumbnail strip on the left
- Swipe left/right to navigate
- Home button at top-right
- Photos are loaded from `data_root/photos/library`
- Thumbnail cache is stored in `data_root/photos/thumbs`

### Typing App

- Freeform text area with rich per-character styling
- Left control panel includes:
  - `New`, `Undo`
  - Font size buttons (`25`, `50`, `100`) with sample "A"
  - Font style buttons (`Plain`, `Bold`, `Italic`)
  - Recall thumbnail tile
- Styling changes apply to newly typed text from the cursor forward
- Undo and New supported (`Undo` depth 20)
- Recall overlay in the left panel shows saved session previews
- Session logs archived silently as rich glyph JSON in `sessions.jsonl`

---

## Data Layout

All child-generated data lives under a single directory, configured by `data_root`:

```
/data/
├── paint/
│   ├── latest.png
│   └── YYYY-MM-DD_HHMMSS.png
├── photos/
│   ├── library/
│   └── thumbs/
└── typing/
    └── sessions.jsonl
```

- No file dialogs
- No delete UI
- Parent manages files externally if desired

---

## Configuration

Runtime configuration is read from `config.yaml` (repo root for dev) or `/opt/kidbox/config.yaml` (deployment). Key settings:

- `data_root` (default dev config: `./data`)
- `launcher.apps` (icon paths + commands)
- `paint.autosave_seconds`
- `paint.palette`

---

## Icons

Launcher icons are provided as pre-rendered PNGs with:

- Transparent background
- Normalized padding
- Multiple resolutions (256 / 512 / 1024)

They are stored in:

```
assets/icons/
```

---

## Development Setup

### Requirements

- Ubuntu 22.04 or 24.04
- Python ≥ 3.10
- SDL-compatible graphics (works on older Intel laptops)

### Dev environment (recommended)

Development uses `uv` with a local `.venv`:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv venv .venv
source .venv/bin/activate
UV_CACHE_DIR=/tmp/uv-cache uv pip install -e .[dev]
```

## Convenience Script

```bash
./scripts/dev-run.sh
./scripts/dev-run.sh paint
./scripts/dev-run.sh photos
./scripts/dev-run.sh typing
./scripts/dev-run.sh tests
```

---

## Running the Apps

From the repo root:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run python -m kidbox.launcher
UV_CACHE_DIR=/tmp/uv-cache uv run python -m kidbox.paint
UV_CACHE_DIR=/tmp/uv-cache uv run python -m kidbox.photos
UV_CACHE_DIR=/tmp/uv-cache uv run python -m kidbox.typing
```

---

## GNOME Launch Setup (Deployment)

KidBox is launched by GNOME autostart after user login.

### 1) Enable autologin in GNOME

KidBox assumes the target user logs into a GNOME session automatically.

### 2) Add an autostart desktop entry

Create:

```text
~/.config/autostart/kidbox-launcher.desktop
```

Example:

```ini
[Desktop Entry]
Type=Application
Name=KidBox Launcher
Exec=/home/<user>/.local/bin/start-kidbox-launcher.sh
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=1
Terminal=false
```

### 3) Start script executed by GNOME

Create:

```text
~/.local/bin/start-kidbox-launcher.sh
```

Example:

```bash
#!/usr/bin/env bash
cd /opt/kidbox
export UV_CACHE_DIR=/tmp/uv-cache
exec /opt/kidbox/.venv/bin/python -m kidbox.launcher
```

Make it executable:

```bash
chmod +x ~/.local/bin/start-kidbox-launcher.sh
```

### 4) Delay behavior

There are two independent launch delays:

- `X-GNOME-Autostart-Delay` in the `.desktop` file.
- Any `sleep` in `start-kidbox-launcher.sh`.

Use one delay mechanism or keep both values low to avoid a long blank/login-to-launch gap.

---

## Tests

```bash
UV_CACHE_DIR=/tmp/uv-cache uv run pytest
```

---

## Project Status

This is a personal project built for a real child on real hardware.
The emphasis is on **clarity, durability, and restraint**, not feature count.

Contributions are welcome if they respect the core design principles.

---

## License

MIT
