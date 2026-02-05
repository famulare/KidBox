from pathlib import Path

from kidbox.paint.app import _list_archives


def test_list_archives_excludes_latest(tmp_path):
    (tmp_path / "latest.png").write_bytes(b"")
    (tmp_path / "2024-01-01_120000.png").write_bytes(b"")
    (tmp_path / "2024-01-02_120000.png").write_bytes(b"")

    archives = _list_archives(tmp_path)
    names = [p.name for p in archives]
    assert "latest.png" not in names
    assert names[0].startswith("2024-01-02")
