# KidBox

**KidBox** is a minimalist, offline-first Linux “kid mode” designed for very young children.
It boots directly into a fullscreen launcher with exactly three large buttons:

* **Paint**
* **Photos**
* **Typing**

There is no desktop environment visible, no file browser, no login/logout flow, and no network dependency during normal use. The system is intentionally constrained, predictable, and robust against accidental input, while remaining easy for a parent to administer and extend.

This is not a general-purpose “kids OS.”
It is a small, comprehensible appliance built on top of Ubuntu.

---

## Design Goals

* **Appliance-like UX**

  * Power on → three buttons → activity
  * No system UI exposed
* **Touch-first**

  * Large hit targets
  * No right-clicks, menus, or dialogs
* **Safe by construction**

  * Autosave everywhere
  * Undo everywhere
  * “New” never destroys work
* **Offline by default**

  * Wi-Fi disabled during normal operation
  * No browser, no app store
* **Parent-controlled escape**

  * Hidden keyboard chord drops back to GNOME
* **Grow-with-the-child**

  * Apps are normal Linux processes
  * Full desktop can be re-enabled later without reinstalling

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
              │ launches
┌─────────────▼──────────────┐
│     Individual Apps        │
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
- pygame / SDL
```

The launcher supervises apps. Apps exit cleanly back to the launcher. If an app crashes, the launcher simply reappears.

---

## Components

### Launcher

* Fullscreen home screen with three icons
* Spawns apps as child processes
* Ignores system keys (brightness, volume, etc.)
* **Parent escape chord:** `Ctrl + Alt + Home`

  * Exits the launcher and reveals GNOME

### Paint App

* Free drawing canvas
* Fixed brush set:

  * Round brushes (small / medium / large)
  * Shape brushes
  * Fountain pen
  * Textured brush
* 16-color palette
* Stroke-based undo (default depth: 10)
* Autosave + archive on “New”
* Custom UX for recalling saved artwork via thumbnails

### Photos App

* Photo library viewer
* Main image area + always-visible thumbnail strip
* Swipe left/right to navigate
* USB-only import (no network UI)

### Typing App

* Simple fullscreen text field
* No prompts, no curriculum
* Intended for free keyboard exploration
* Undo and “New” supported
* Session logs archived silently

---

## Data Layout

All child-generated data lives under a single directory:

```
/data/kidbox/
├── paint/
│   ├── latest.png
│   └── YYYY-MM-DD_HHMMSS.png
├── photos/
│   ├── library/
│   └── thumbs/
└── typing/
    └── sessions.jsonl
```

* No file dialogs
* No delete UI
* Parent manages files externally if desired

---

## Development Setup

### Requirements

* Ubuntu 22.04 or 24.04
* Python ≥ 3.10
* SDL-compatible graphics (works on older Intel laptops)

### Dev environment (recommended)

Development uses a virtual environment and `uv`.

```bash
uv venv
source .venv/bin/activate
uv pip install pygame-ce pyyaml
```

You develop and test inside the venv.

---

## Runtime Environment (Important)

At runtime, **no virtual environment is used**.

The system runs on:

* Ubuntu system Python (`/usr/bin/python3`)
* Dependencies installed via `apt`

Example:

```bash
sudo apt install python3 python3-pygame python3-yaml
```

All launcher and app scripts use a standard shebang:

```python
#!/usr/bin/env python3
```

This keeps the system robust and easy to recover.

---

## Running the Launcher Manually

From the repo root:

```bash
python launcher/launcher.py
```

On the target system, the launcher is started automatically at login via GNOME autostart or a kiosk-style session.

---

## Icons

Launcher icons are provided as pre-rendered PNGs with:

* Transparent background
* Normalized padding
* Multiple resolutions (256 / 512 / 1024)

See:

```
assets/icons/
```

---

## Security Model (Short)

* Single unprivileged user for child session
* No sudo access
* No network services listening
* Wi-Fi disabled during normal use
* Parent intervention is intentional and explicit

Security here is achieved through **minimal surface area**, not complexity.

---

## Non-Goals (v1)

* Screen time enforcement
* Internet browsing
* App store
* Cloud sync
* Multi-user profiles
* Typing curriculum or scoring

These are intentionally left out.

---

## Project Status

This is a personal project built for a real child on real hardware.
The emphasis is on **clarity, durability, and restraint**, not feature count.

Contributions are welcome if they respect the core design principles.

---

## License

MIT
