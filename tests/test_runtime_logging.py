from toddlerbox.runtime.logging import LOG_MAX_BYTES, get_runtime_logger


def test_runtime_logger_writes_file(tmp_path):
    logger = get_runtime_logger(tmp_path)
    logger.info("hello")
    log_path = tmp_path / "logs" / "toddlerbox.log"
    assert log_path.exists()
    assert "hello" in log_path.read_text(encoding="utf-8")


def test_runtime_logger_rollover(tmp_path):
    logger = get_runtime_logger(tmp_path)
    log_path = tmp_path / "logs" / "toddlerbox.log"
    rollover_path = tmp_path / "logs" / "toddlerbox.log.1"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text("x" * (LOG_MAX_BYTES + 10), encoding="utf-8")

    logger.info("after-rollover")

    assert rollover_path.exists()
    assert "after-rollover" in log_path.read_text(encoding="utf-8")
