from datetime import datetime
from pathlib import Path

from toddlerbox.photos.app import _is_image, _list_photos, _parse_exif_datetime, _photo_sort_key, _thumb_name


def test_thumb_name():
    path = Path("/data/photos/library/Summer.jpg")
    assert _thumb_name(path) == "Summer_jpg.png"


def test_is_image():
    assert _is_image(Path("photo.PNG"))
    assert not _is_image(Path("notes.txt"))


def test_parse_exif_datetime():
    assert _parse_exif_datetime("2024:10:05 11:22:33") == datetime(2024, 10, 5, 11, 22, 33)
    assert _parse_exif_datetime("2024-10-05 11:22:33") is None
    assert _parse_exif_datetime(None) is None


def test_photo_sort_key_prefers_taken_date(monkeypatch, tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"img")
    taken = datetime(2020, 1, 2, 3, 4, 5)
    monkeypatch.setattr("toddlerbox.photos.app._photo_taken_at", lambda _path: taken)

    assert _photo_sort_key(path) == (0, -taken.timestamp(), "photo.jpg")


def test_list_photos_orders_newest_first_by_taken_date_then_mtime(monkeypatch, tmp_path):
    a = tmp_path / "a.jpg"
    b = tmp_path / "b.jpg"
    c = tmp_path / "c.jpg"
    txt = tmp_path / "notes.txt"
    for path in (a, b, c, txt):
        path.write_bytes(b"x")

    # Newest mtime first among non-EXIF images.
    c.touch()
    a.touch()
    b.touch()

    taken_map = {
        "a.jpg": datetime(2020, 1, 1, 8, 0, 0),
        "b.jpg": datetime(2021, 1, 1, 8, 0, 0),
    }
    monkeypatch.setattr("toddlerbox.photos.app._photo_taken_at", lambda path: taken_map.get(path.name))

    paths = _list_photos(tmp_path)
    assert [path.name for path in paths] == ["b.jpg", "a.jpg", "c.jpg"]
