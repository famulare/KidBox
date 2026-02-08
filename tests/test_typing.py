import json

from toddlerbox.typing.app import Glyph
from toddlerbox.typing.app import TypingApp
from toddlerbox.typing.app import _Token
from toddlerbox.typing.app import _load_recent_sessions
from toddlerbox.typing.app import _preview_text
from toddlerbox.typing.app import _wrap_tokens


def test_delete_line_join_undo_restores_newline():
    app = TypingApp.__new__(TypingApp)
    app.rich_lines = [
        [Glyph(char=c, size=25, style="plain") for c in "hello"],
        [Glyph(char=c, size=25, style="plain") for c in "world"],
    ]
    app.text_lines = ["hello", "world"]
    app.default_line_style = (25, "plain")
    app.line_styles = [(25, "plain"), (25, "plain")]
    app.undo_stack = []
    app.cursor_row = 1
    app.cursor_col = 0

    op = app._delete_backward()
    assert op is not None
    assert op.newline
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
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-02-06T10:00:00",
                    "rich_lines": [[{"char": "f", "size": 25, "style": "plain"}]],
                }
            )
            + "\n"
        )
        handle.write(
            json.dumps(
                {
                    "timestamp": "2026-02-06T10:01:00",
                    "rich_lines": [[{"char": "s", "size": 25, "style": "plain"}]],
                }
            )
            + "\n"
        )
        handle.write(json.dumps({"timestamp": "2026-02-06T10:02:00", "text": 3}) + "\n")

    items = _load_recent_sessions(sessions)
    assert [item.label for item in items] == ["2026-02-06T10:01:00", "2026-02-06T10:00:00"]
    assert [item.preview for item in items] == ["s", "f"]


def test_wrap_tokens_moves_word_to_next_line():
    tokens = [
        _Token(start=0, end=5, widths=[1, 1, 1, 1, 1], is_space=False),
        _Token(start=5, end=6, widths=[1], is_space=True),
        _Token(start=6, end=11, widths=[1, 1, 1, 1, 1], is_space=False),
    ]
    assert _wrap_tokens(tokens, max_width=6) == [(0, 6), (6, 11)]


def test_wrap_tokens_splits_single_long_word():
    tokens = [_Token(start=0, end=10, widths=[1] * 10, is_space=False)]
    assert _wrap_tokens(tokens, max_width=4) == [(0, 4), (4, 8), (8, 10)]


def test_wrap_tokens_preserves_leading_spaces():
    tokens = [
        _Token(start=0, end=1, widths=[1], is_space=True),
        _Token(start=1, end=3, widths=[1, 1], is_space=False),
    ]
    assert _wrap_tokens(tokens, max_width=2) == [(0, 1), (1, 3)]
