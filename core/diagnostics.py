"""UTF-8, credential-redacted logging shared by GUI and silent mode."""
import logging
import logging.handlers
import os
import sys
import threading
from pathlib import Path

from core.proxy_checker import redact


class RedactingFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def configure_logging(directory=None):
    folder = Path(directory) if directory else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "AntigravityLauncher" / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(folder / "launcher.log", maxBytes=2 * 1024 * 1024,
                                                   backupCount=2, encoding="utf-8")
    handler.setFormatter(RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger = logging.getLogger("antigravity_launcher")
    for previous in list(logger.handlers):
        logger.removeHandler(previous)
        previous.close()
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    def report(exc_type, exc_value, traceback):
        logger.error("未捕获异常", exc_info=(exc_type, exc_value, traceback))
    sys.excepthook = report
    threading.excepthook = lambda args: report(args.exc_type, args.exc_value, args.exc_traceback)
    return folder / "launcher.log"
