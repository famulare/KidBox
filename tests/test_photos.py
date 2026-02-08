from datetime import datetime
import json
from pathlib import Path

from toddlerbox.photos.app import _is_image, _list_photos, _load_exif_cache, _parse_exif_datetime, _thumb_name


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


def test_list_photos_uses_cached_taken_date(tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"img")
    stat = path.stat()
    taken_ts = datetime(2020, 1, 2, 3, 4, 5).timestamp()
    cache = {"photo.jpg": taken_ts}

    paths, dirty = _list_photos(tmp_path, cache)
    assert [p.name for p in paths] == ["photo.jpg"]
    assert not dirty
    assert cache["photo.jpg"] == taken_ts


def test_list_photos_orders_newest_first_by_taken_date_then_mtime(tmp_path):
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

    cache = {
        "a.jpg": datetime(2020, 1, 1, 8, 0, 0).timestamp(),
        "b.jpg": datetime(2021, 1, 1, 8, 0, 0).timestamp(),
    }
    paths, dirty = _list_photos(tmp_path, cache)
    assert [path.name for path in paths] == ["b.jpg", "a.jpg", "c.jpg"]
    assert dirty


def test_list_photos_populates_missing_cache_from_exif(monkeypatch, tmp_path):
    path = tmp_path / "photo.jpg"
    path.write_bytes(b"x")
    taken = datetime(2022, 1, 1, 1, 2, 3)
    monkeypatch.setattr("toddlerbox.photos.app._photo_taken_at", lambda _path: taken)
    cache = {}

    _paths, dirty = _list_photos(tmp_path, cache)

    assert dirty
    assert cache["photo.jpg"] == taken.timestamp()


def test_load_exif_cache_replaces_incompatible_format(tmp_path):
    cache_path = tmp_path / "exif_cache.json"
    cache_path.write_text(json.dumps({"photo.jpg": {"taken": 123.0}}), encoding="utf-8")

    loaded = _load_exif_cache(cache_path)

    assert loaded == {}
    rewritten = json.loads(cache_path.read_text(encoding="utf-8"))
    assert rewritten == {}
