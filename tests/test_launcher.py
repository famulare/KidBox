from kidbox.launcher import _resolve_command, _restore_launcher_window


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


def test_restore_launcher_window_reuses_existing_surface(monkeypatch):
    class FakeSurface:
        def get_rect(self):
            return "fake-rect"

    existing = FakeSurface()
    monkeypatch.setattr("kidbox.launcher.pygame.display.get_surface", lambda: existing)

    surface, rect = _restore_launcher_window()
    assert surface is existing
    assert rect == "fake-rect"


def test_restore_launcher_window_recreates_when_surface_missing(monkeypatch):
    monkeypatch.setattr("kidbox.launcher.pygame.display.get_surface", lambda: None)
    monkeypatch.setattr("kidbox.launcher.create_fullscreen_window", lambda: ("new-surface", "new-rect"))

    surface, rect = _restore_launcher_window()
    assert surface == "new-surface"
    assert rect == "new-rect"
