import json

from kidbox.typing.app import TypingApp
from kidbox.typing.app import _load_recent_sessions
from kidbox.typing.app import _preview_text


def test_delete_line_join_undo_restores_newline():
    app = TypingApp.__new__(TypingApp)
    app.text_lines = ["hello", "world"]
    app.undo_stack = []
    app.cursor_row = 1
    app.cursor_col = 0

    op = app._delete_backward()
    assert op is not None
    assert op.text == "\n"
    app._push_undo(op)

    app._undo()
    assert app.text_lines == ["hello", "world"]
    assert app.cursor_row == 1
    assert app.cursor_col == 0


def test_preview_text_normalizes_and_caps_at_150():
    text = "  hello\n\nworld   " + ("x" * 200)
    preview = _preview_text(text)
    assert preview.startswith("hello world")
    assert len(preview) == 150


def test_load_recent_sessions_skips_invalid_lines(tmp_path):
    sessions = tmp_path / "sessions.jsonl"
    with sessions.open("w", encoding="utf-8") as handle:
        handle.write("{bad json}\n")
        handle.write(json.dumps({"timestamp": "2026-02-06T10:00:00", "text": "first"}) + "\n")
        handle.write(json.dumps({"timestamp": "2026-02-06T10:01:00", "text": "second"}) + "\n")
        handle.write(json.dumps({"timestamp": "2026-02-06T10:02:00", "text": 3}) + "\n")

    items = _load_recent_sessions(sessions)
    assert items == [
        ("2026-02-06T10:01:00", "second"),
        ("2026-02-06T10:00:00", "first"),
    ]
