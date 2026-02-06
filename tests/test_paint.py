import os
from pathlib import Path

import pygame

from toddlerbox.paint.app import _coerce_archive_limit
from toddlerbox.paint.app import _fountain_width_for_direction
from toddlerbox.paint.app import _load_canvas_image
from toddlerbox.paint.app import _list_archives
from toddlerbox.paint.app import _rollover_latest_snapshot
from toddlerbox.ui.common import is_primary_pointer_event


def test_list_archives_includes_latest(tmp_path):
    (tmp_path / "latest.png").write_bytes(b"")
    (tmp_path / "2024-01-01_120000.png").write_bytes(b"")
    (tmp_path / "2024-01-02_120000.png").write_bytes(b"")

    os.utime(tmp_path / "2024-01-01_120000.png", (1, 1))
    os.utime(tmp_path / "2024-01-02_120000.png", (2, 2))
    os.utime(tmp_path / "latest.png", (3, 3))

    archives = _list_archives(tmp_path)
    names = [p.name for p in archives]
    assert "latest.png" in names
    assert names[0] == "latest.png"


def test_list_archives_orders_by_mtime(tmp_path):
    a = tmp_path / "2024-01-01_120000.png"
    b = tmp_path / "2024-01-02_120000.png"
    c = tmp_path / "2024-01-03_120000.png"

    for path in (a, b, c):
        path.write_bytes(b"")

    os.utime(a, (10, 10))
    os.utime(c, (20, 20))
    os.utime(b, (30, 30))

    archives = _list_archives(tmp_path)
    assert [p.name for p in archives[:3]] == [b.name, c.name, a.name]


def test_coerce_archive_limit_clamps_and_falls_back():
    assert _coerce_archive_limit("5", 100) == 5
    assert _coerce_archive_limit(-2, 100) == 0
    assert _coerce_archive_limit("bad", 100) == 100

def test_rollover_latest_snapshot_archives_existing_latest(tmp_path):
    latest = tmp_path / "latest.png"
    latest.write_bytes(b"session")

    archived = _rollover_latest_snapshot(tmp_path)

    assert archived is not None
    assert archived.exists()
    assert archived.read_bytes() == b"session"
    assert not latest.exists()


def test_rollover_latest_snapshot_adds_counter_on_collision(tmp_path):
    latest = tmp_path / "latest.png"
    latest.write_bytes(b"new")
    existing = tmp_path / "2026-02-06_101112.png"
    existing.write_bytes(b"old")

    class FixedNow:
        def strftime(self, _fmt: str) -> str:
            return "2026-02-06_101112"

    archived = _rollover_latest_snapshot(tmp_path, now=FixedNow())

    assert archived == tmp_path / "2026-02-06_101112_1.png"
    assert archived.exists()
    assert archived.read_bytes() == b"new"
    assert existing.read_bytes() == b"old"


def test_primary_pointer_event_accepts_left_mouse_button():
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(10, 10))
    assert is_primary_pointer_event(event, is_down=True)


def test_primary_pointer_event_accepts_touch_emulated_mouse_button_zero():
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=0, pos=(10, 10), touch=True)
    assert is_primary_pointer_event(event, is_down=True)


def test_primary_pointer_event_rejects_right_mouse_button():
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(10, 10))
    assert not is_primary_pointer_event(event, is_down=True)


def test_fountain_width_changes_with_direction():
    size = 10
    horizontal = _fountain_width_for_direction(size, (0, 0), (20, 0), nib_angle_degrees=0)
    vertical = _fountain_width_for_direction(size, (0, 0), (0, 20), nib_angle_degrees=0)
    assert vertical > horizontal
    assert vertical - horizontal >= 12


def test_fountain_width_respects_ratio_bounds():
    size = 12
    min_ratio = 0.4
    max_ratio = 1.3
    width = _fountain_width_for_direction(
        size,
        (5, 5),
        (5, 5),
        min_ratio=min_ratio,
        max_ratio=max_ratio,
    )
    assert int(round(size * min_ratio)) <= width <= int(round(size * max_ratio))


def test_load_canvas_image_returns_none_on_image_error(monkeypatch, tmp_path):
    path = tmp_path / "broken.png"
    path.write_bytes(b"not-an-image")

    def _raise(*_args, **_kwargs):
        raise pygame.error("bad image")

    monkeypatch.setattr(pygame.image, "load", _raise)
    assert _load_canvas_image(path, (64, 64)) is None
