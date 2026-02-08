# ToddlerBox — v1 As-Built Contract (Current Implementation)

This document is the source of truth for the code currently shipped in `main`.
It reflects implementation as it exists today, not aspirational scope.

## 0. Global invariants

- Language: Python 3
- UI framework: pygame / SDL
- Fullscreen, borderless kiosk-style UI
- Child-facing screens never show dialogs or crash traces
- Parent escape chord from launcher: `Ctrl + Alt + Home`
- Data root is configurable via `data_root` (defaults: dev `./data`, runtime fallback `/data`)

## 1. Launcher

### 1.1 UX

- Fullscreen home view with three large app icons:
  - Paint
  - Photos
  - Typing
- Icon hit targets are computed from screen size (minimum 120px)
- Function keys `F1`-`F12` are ignored
- `Ctrl + Alt + Home` exits launcher to GNOME

### 1.2 App handoff model

- Built-in apps (`toddlerbox.paint`, `toddlerbox.photos`, `toddlerbox.typing`) run embedded in-process.
- Launcher keeps a single pygame window and switches scenes to reduce transition flicker.
- Non-built-in commands in config are launched via subprocess fallback.
- Subprocess fallback suppresses child stdout/stderr.

### 1.3 Return behavior

- App exits return to launcher home view.
- Pointer down/up events are cleared on return and pointer input is briefly debounced to avoid accidental relaunch.

## 2. Paint App

### 2.1 Layout

- Left tools panel + right canvas area
- Small Home button at top-right

### 2.2 Tools and controls

- Tools:
  - Round brush
  - Fountain pen (direction-sensitive width)
  - Eraser
  - Bucket fill
- Sizes: 3 presets (scaled by display)
- Palette: configurable; current config provides 14 colors
- Undo stack depth: 10
- Actions:
  - `New`: archive current canvas, clear canvas, clear undo
  - `Undo`
  - `Recall`

### 2.3 Persistence

- Stores in `data_root/paint/`
- `latest.png` autosaved periodically (default 10s)
- Archived snapshots named `YYYY-MM-DD_HHMMSS(.+counter).png`
- Atomic PNG writes are used
- Existing `latest.png` is rolled over to archive on app start

### 2.4 Recall UX

- Recall opens as a modal overlay in the left panel area
- Vertical scroll list of square thumbnails
- First thumbnail is current live canvas
- Remaining thumbnails are archived paintings (newest first)
- Tap-release selects; drag scrolls
- Tap outside closes recall
- Selecting archive loads it into canvas and promotes to `latest.png`

## 3. Photos App

### 3.1 Layout

- Vertical thumbnail strip on the left
- Main image area on the right
- Home button at top-right
- Optional next/prev arrows controlled by config (`photos.show_arrows`)

### 3.2 Behavior

- Library path: `data_root/photos/library`
- Thumbnail cache path: `data_root/photos/thumbs`
- Supported extensions: `.png .jpg .jpeg .bmp .gif`
- Thumbnails are generated/cached and reused by mtime
- Strip supports drag/wheel scrolling
- Tap-release on thumbnail selects image
- Horizontal drag in main image area changes image index

## 4. Typing App

### 4.1 Layout

- Left controls panel, right text area
- Home button at top-right

### 4.2 Text model

- Rich per-character glyph model:
  - `char`
  - `size`
  - `style` (`plain|bold|italic`)
- Styling changes apply to newly typed characters from cursor forward
- Cursor and glyph rendering support mixed sizes/styles in one line
- Mixed-size line rendering is bottom-aligned per row

### 4.3 Controls

- `New`: archive session and clear document
- `Undo`: depth 20
- Size buttons: default 25, plus 50 and 100
- Style buttons: Plain, Bold, Italic
- Recall button uses static thumbnail text prompt

### 4.4 Recall and persistence

- Session file: `data_root/typing/sessions.jsonl`
- Each record stores:
  - `timestamp`
  - `rich_lines` (glyph arrays)
- Recall overlay opens in left panel and lists:
  - `Current`
  - Recent archived sessions (newest first)
- Each item shows text preview (first 150 normalized chars)
- Tap outside closes recall; tap-release loads selected session

## 5. Data layout

All app data lives directly under `data_root`:

```text
data_root/
├── paint/
│   ├── latest.png
│   └── YYYY-MM-DD_HHMMSS*.png
├── photos/
│   ├── library/
│   └── thumbs/
└── typing/
    └── sessions.jsonl
```

## 6. Configuration (current keys)

- `data_root`
- `launcher.apps[]` (`name`, `icon_path`, `command`)
- `paint.autosave_seconds`
- `paint.palette`
- `photos.show_arrows` (optional)

## 7. Error handling

- App `main()` wrappers swallow exceptions and call `pygame.quit()` in standalone mode
- Embedded launcher path catches app exceptions and returns to launcher
- Child-facing UIs do not show error dialogs
