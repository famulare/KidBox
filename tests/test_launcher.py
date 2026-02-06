from kidbox.launcher import _resolve_command


def test_resolve_command_uses_active_interpreter_for_python(monkeypatch):
    monkeypatch.setattr("kidbox.launcher.sys.executable", "/opt/kidbox/.venv/bin/python3.11")
    command = _resolve_command(["python", "-m", "kidbox.paint"])
    assert command == ["/opt/kidbox/.venv/bin/python3.11", "-m", "kidbox.paint"]


def test_resolve_command_falls_back_to_python3_when_executable_missing(monkeypatch):
    monkeypatch.setattr("kidbox.launcher.sys.executable", "")
    monkeypatch.setattr("kidbox.launcher.shutil.which", lambda name: "/usr/bin/python3" if name == "python3" else None)
    command = _resolve_command(["python3", "-m", "kidbox.photos"])
    assert command == ["/usr/bin/python3", "-m", "kidbox.photos"]


def test_resolve_command_keeps_non_python_commands():
    command = _resolve_command(["/usr/bin/echo", "hello"])
    assert command == ["/usr/bin/echo", "hello"]
