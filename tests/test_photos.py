from pathlib import Path

from kidbox.photos.app import _thumb_name, _is_image


def test_thumb_name():
    path = Path("/data/kidbox/photos/library/Summer.jpg")
    assert _thumb_name(path) == "Summer_jpg.png"


def test_is_image():
    assert _is_image(Path("photo.PNG"))
    assert not _is_image(Path("notes.txt"))
