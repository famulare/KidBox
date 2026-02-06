from kidbox.config import load_config


def test_load_config_overrides(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("data_root: /tmp/data\npaint:\n  autosave_seconds: 5\n", encoding="utf-8")
    monkeypatch.setenv("KIDBOX_CONFIG", str(config_path))

    config = load_config()
    assert config["data_root"] == "/tmp/data"
    assert config["paint"]["autosave_seconds"] == 5

    monkeypatch.delenv("KIDBOX_CONFIG", raising=False)
