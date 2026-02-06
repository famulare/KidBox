from toddlerbox.paths import ensure_directories


def test_ensure_directories(tmp_path):
    dirs = ensure_directories(tmp_path)
    assert (tmp_path / "paint").exists()
    assert (tmp_path / "photos" / "library").exists()
    assert (tmp_path / "photos" / "thumbs").exists()
    assert (tmp_path / "typing").exists()
    assert dirs["paint"] == tmp_path / "paint"
