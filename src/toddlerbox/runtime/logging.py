from __future__ import annotations

import os
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional


LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "toddlerbox.log"
LOG_MAX_BYTES = 1_000_000
LOG_ROLLOVER_NAME = "toddlerbox.log.1"


class RuntimeLogger:
    def __init__(self, data_root: Path) -> None:
        self.log_dir = data_root / LOG_DIR_NAME
        self.log_path = self.log_dir / LOG_FILE_NAME
        self.rollover_path = self.log_dir / LOG_ROLLOVER_NAME

    def info(self, message: str) -> None:
        self._write("INFO", message)

    def warning(self, message: str) -> None:
        self._write("WARN", message)

    def exception(self, message: str) -> None:
        detail = traceback.format_exc()
        self._write("ERROR", f"{message}\n{detail}")

    def _write(self, level: str, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"{timestamp} [{level}] {message.rstrip()}\n"
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            if self.log_path.exists() and self.log_path.stat().st_size >= LOG_MAX_BYTES:
                try:
                    if self.rollover_path.exists():
                        self.rollover_path.unlink()
                except OSError:
                    pass
                try:
                    os.replace(self.log_path, self.rollover_path)
                except OSError:
                    pass
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError:
            # Logging is best-effort and must not affect child-facing behavior.
            pass


_LOGGER: Optional[RuntimeLogger] = None
_LOGGER_ROOT: Optional[Path] = None


def get_runtime_logger(data_root: Path) -> RuntimeLogger:
    global _LOGGER
    global _LOGGER_ROOT
    resolved = data_root.resolve()
    if _LOGGER is None or _LOGGER_ROOT != resolved:
        _LOGGER = RuntimeLogger(resolved)
        _LOGGER_ROOT = resolved
    return _LOGGER
