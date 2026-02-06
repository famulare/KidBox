# Changelog

## 0.2.0 - 2026-02-06

- Photos now sort newest-first by EXIF capture date when available.
- Photos without EXIF date fall back to file modified time (newest-first).
- Added screenshot gallery to README with inline GitHub-rendered images.
- Added `Pillow` dependency for EXIF metadata parsing.
- `pytest` is included in core dependencies for always-available test runs in the project venv.

