from kidbox.typing.app import TypingApp


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
