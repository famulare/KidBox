from pathlib import Path

import pygame

from kidbox.paint.app import _list_archives
from kidbox.paint.app import _is_primary_pointer_event


def test_list_archives_excludes_latest(tmp_path):
    (tmp_path / "latest.png").write_bytes(b"")
    (tmp_path / "2024-01-01_120000.png").write_bytes(b"")
    (tmp_path / "2024-01-02_120000.png").write_bytes(b"")

    archives = _list_archives(tmp_path)
    names = [p.name for p in archives]
    assert "latest.png" not in names
    assert names[0].startswith("2024-01-02")


def test_primary_pointer_event_accepts_left_mouse_button():
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))
    assert _is_primary_pointer_event(event, is_down=True)


def test_primary_pointer_event_accepts_touch_emulated_mouse_button_zero():
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=0, pos=(10, 10), touch=True)
    assert _is_primary_pointer_event(event, is_down=True)


def test_primary_pointer_event_rejects_right_mouse_button():
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(10, 10))
    assert not _is_primary_pointer_event(event, is_down=True)
