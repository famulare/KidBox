# Toddler Portal — v1 Detailed Spec (Python)

## 0. Global constraints (hard invariants)

* Language: **Python 3**
* UI framework: **pygame-ce** (or SDL2 bindings)
* Windowing:

  * Borderless
  * Fullscreen
  * Single window per process
* No desktop widgets, menus, dialogs, notifications
* All state persists via autosave
* Sudden power loss is expected and safe

---

## 1. Launcher (Toddler Portal)

### 1.1 Purpose

The launcher is the **only persistent UI surface**. It supervises apps and is the only thing the child can return to.

---

### 1.2 Visual layout

* Fullscreen background (solid color)
* **Three large icons**, centered horizontally:

  1. Paint
  2. Photos
  3. Typing
* Icon hit targets ≥ 120×120 px
* No clock, no status indicators, no text labels required

---

### 1.3 Input handling

#### Ignore completely:

* Brightness keys
* Volume keys
* Airplane mode key
* Media keys
* Function keys (except escape chord)
* System shortcuts

#### Parent escape chord (ONLY special key combo):

```
Ctrl + Alt + Home
```

Behavior:

* Launcher immediately exits
* Control returns to GNOME session (already installed)
* No confirmation UI
* No visual indicator

Implementation:

* Capture keydown events
* Track modifier state
* On exact chord → `sys.exit(0)`

---

### 1.4 App launching model

* Launcher spawns apps via `subprocess.Popen`
* Launcher blocks on child process exit
* When child exits → launcher redraws home screen

No IPC required in v1.

---

### 1.5 Files and paths

```text
/opt/kidbox/launcher/launcher.py
/opt/kidbox/config.yaml
/data/kidbox/
```

---

## 2. Common app conventions (ALL apps)

### 2.1 Shared UI rules

* Fullscreen
* No window chrome
* No menus
* No toolbars beyond explicitly listed controls
* One **Home / Minimize** button per app
* Esc key triggers Home / Minimize

### 2.2 Minimize behavior

* Minimize == process exit
* Launcher reappears automatically

### 2.3 Undo

* Default undo depth = **10**
* Undo is always visible
* Undo never asks for confirmation

---

## 3. Paint App

### 3.1 Purpose

Free-form drawing with variety but **no configuration UI**.

---

### 3.2 Canvas

* Occupies ~70–80% of screen
* White or off-white background
* Touch/mouse draws immediately

---

### 3.3 Brushes (fixed set, visible buttons)

No size chooser, no sliders.

#### Round brushes

* Small
* Medium
* Large

#### Shape brushes

* Square
* Triangle
* Star (or hexagon)

#### Specialty brushes

* Fountain pen (pressure simulated via speed)
* Textured brush (noise-based alpha)

Each brush has:

* Fixed size
* Fixed shape
* One button per brush

Total brushes: ~8–10

---

### 3.4 Color palette

* Exactly **16 colors**
* Visible at all times
* Large swatches
* No picker, no RGB sliders

---

### 3.5 Undo

* Stroke-based undo
* One undo removes one stroke
* Undo stack capped at 10

---

### 3.6 New behavior

* `New` button:

  * Autosaves current canvas to archive
  * Clears canvas
  * Resets undo stack
* No confirmation dialogs

---

### 3.7 Autosave & persistence

Files:

```text
/data/kidbox/paint/latest.png
/data/kidbox/paint/YYYY-MM-DD_HHMMSS.png
```

Rules:

* `latest.png` updated every 10 seconds
* Also saved on New
* Atomic writes only

---

### 3.8 **Saved art recall UX (important, custom)**

This is non-trivial and should be explicit.

#### Base UI state

* A **thumbnail button** is visible
* It displays:

  * The most recent archived painting (not `latest.png`)
  * If none exists, button is hidden or disabled

#### On thumbnail tap

* Paint UI is **entirely replaced**
* A fullscreen overlay appears:

  * Scrollable horizontal strip of thumbnails
  * No other controls visible
* Tap a thumbnail:

  * Loads that painting into canvas
  * Closes overlay
  * Returns to base paint UI
* Tap outside strip or Home:

  * Cancel and return to base UI

No delete, no rename.

---

## 4. Photos App

### 4.1 Layout

* Main image area: left ~70% of screen
* Thumbnail strip: **always visible on the right**
* Strip scrolls vertically

---

### 4.2 Behavior

* Load images from:

```text
/data/kidbox/photos/library/
```

* Generate thumbnails in:

```text
/data/kidbox/photos/thumbs/
```

* Tap thumbnail → display in main area
* Swipe left/right on main image → next/previous photo

---

### 4.3 Import policy

* No UI for import in v1

Parent workflow:

* Mount USB and/or locate local files using ubuntu UX.
* Copy files into `library/`
* App picks them up on next launch

---

### 4.4 Controls

* Home / Minimize
* Optional next/prev arrows (only if swipe unreliable)

No delete, no share, no edit.

---

## 5. Typing App

### 5.1 Purpose

Pure keyboard play. No curriculum.

---

### 5.2 UI

* Fullscreen blank canvas
* Single text field
* Simple sans-serif font
* Font size ~12pt (low-res screen assumption)
* Cursor always visible

---

### 5.3 Input handling

Accepted:

* Printable characters
* Space
* Backspace
* Shift for capitalization
* Enter for new line
* Esc for home / minimize

Ignored:

* All other modifiers
* Ctrl shortcuts
* Alt shortcuts
* Function keys

---

### 5.4 Undo

* Undo removes:

  * Last character
* Undo depth = 20

---

### 5.5 New

* Clears text
* Archives session to:

```text
/data/kidbox/typing/sessions.jsonl
```

No prompts, no warnings.

---

## 6. Kiosk + GNOME integration

### 6.1 Session model

* GNOME installed normally
* Kid launcher runs fullscreen **on top**
* Escape chord exits launcher → GNOME desktop appears

No display manager hacks required beyond autostart.

---

### 6.2 Autostart strategy (recommended)

* Autologin enabled
* GNOME session
* Launcher added as startup application
* Launcher set fullscreen and grabs input

This keeps:

* Hardware keys manageable
* Parent recovery trivial
* Future growth easy

---

## 7. Error handling & resilience

* If any app crashes:

  * Launcher regains control
  * No error shown to child
* If paint/photos data missing:

  * App recreates directories
* No fatal errors allowed to reach screen

---

## 8. Explicit deferrals (NOT in v1)

* Typing history recall UI
* Multi-user profiles
* Screen time controls
* Audio feedback
* Accessibility modes

---

## 9. Codex-friendly task breakdown

You can hand this directly to codegen:

### Task 1 — Launcher

* Fullscreen pygame window
* 3 buttons
* Subprocess launch
* Ctrl+Alt+Home escape
* Ignore system keys

### Task 2 — Paint App

* Stroke engine
* Fixed brush set
* 16-color palette
* Undo stack (10)
* Autosave
* Thumbnail recall overlay

### Task 3 — Photos App

* Directory scan
* Thumbnail cache
* Fixed right-side strip
* Swipe navigation

### Task 4 — Typing App

* Raw text input
* Undo
* New
* Session logging

---

## 10. Sanity check (does this match intent?)

* ✔ Minimal UI
* ✔ No accidental exits
* ✔ Undo everywhere
* ✔ “New” is safe
* ✔ No file metaphors for child
* ✔ Parent can always escape cleanly
* ✔ Python-readable
