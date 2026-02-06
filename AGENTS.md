# Repository Guidelines

## Project Structure & Module Organization
- `src/toddlerbox/` contains the launcher and apps (`launcher.py`, `paint/`, `photos/`, `typing/`).
- `src/toddlerbox/ui/` contains shared UI helpers and widgets.
- `tests/` holds pytest unit tests.
- `assets/` is reserved for launcher icons and other static files.
- `config.yaml` provides dev defaults (paths, palette, app commands).
- `toddlerbox_design_contract.md` is the source of truth for product requirements.

## Build, Test, and Development Commands
Use `uv` with the local `.venv` and a writable cache directory.
- `UV_CACHE_DIR=/tmp/uv-cache uv venv .venv` — create or refresh the virtualenv.
- `UV_CACHE_DIR=/tmp/uv-cache uv pip install -e ".[dev]"` — install in editable mode with test deps.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m toddlerbox.launcher` — run launcher.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m toddlerbox.paint` — run paint.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m toddlerbox.photos` — run photos.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m toddlerbox.typing` — run typing.
- `UV_CACHE_DIR=/tmp/uv-cache uv run pytest` — run unit tests.

## Coding Style & Naming Conventions
- Python: 4-space indentation; keep modules small and focused.
- File names: lowercase with underscores for Python modules (e.g., `photos/app.py`).
- Config: YAML keys in lower snake_case.

## Testing Guidelines
- Framework: `pytest`.
- Prefer unit tests for pure logic (config merge, file naming, thumbnail cache decisions).
- Name tests with behavior-focused descriptions (e.g., `test_autosave_atomic_write`).

## Commit & Pull Request Guidelines
- Use short, imperative commit messages (e.g., “Add paint app autosave”).
- PRs should describe changes, reference the design contract section, and include screenshots for UI changes.

## Security & Configuration Tips
- Do not commit secrets or local env files (`.venv/`, `.env`).
- Dev config uses `config.yaml` at repo root; production config should live at `/opt/toddlerbox/config.yaml`.
- Data writes default to `data_root` from config; dev defaults to `./data`.

## Agent-Specific Instructions
- Keep UI minimal and fullscreen; avoid dialogs and OS UI elements.
- Prioritize autosave safety and graceful failure (no error UI for child-facing screens).
