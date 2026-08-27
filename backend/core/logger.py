import logging
import json
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from contextvars import ContextVar

# Request ID context variable (middleware tomonidan o'rnatiladi)
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Mijoz IP va User-Agent — RequestIDMiddleware o'rnatadi, audit jurnali o'qiydi.
# ContextVar tanlandi (endpoint imzosiga `request: Request` qo'shish o'rniga):
# `log_audit` 18 ta joyda chaqiriladi, ularning birortasi ham Request olmaydi.
# Shu yo'l bilan chaqiruv joylari TEGILMAYDI va yangi chaqiruv ham avtomatik
# IP oladi (kelajakda kimdir uzatishni unutib qolmaydi).
client_ip_var:   ContextVar[str] = ContextVar("client_ip",  default=None)
user_agent_var:  ContextVar[str] = ContextVar("user_agent", default=None)


class JSONFormatter(logging.Formatter):
    """Production uchun JSON formatli log."""

    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts":      self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level":   record.levelname,
            "name":    record.name,
            "rid":     request_id_var.get("-"),
            "msg":     record.getMessage(),
        }
        if record.exc_info:
            log["exc"] = self.formatException(record.exc_info)
        return json.dumps(log, ensure_ascii=False)


class HumanFormatter(logging.Formatter):
    """Development uchun o'qilishi qulay format."""

    FMT = "%(asctime)s [%(levelname)-8s] %(name)s (rid=%(rid)s) %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        record.rid = request_id_var.get("-")
        return super().format(record)


def setup_logger() -> None:
    os.makedirs("logs", exist_ok=True)

    is_production = os.getenv("ENVIRONMENT", "development") == "production"
    formatter: logging.Formatter = (
        JSONFormatter() if is_production else HumanFormatter(HumanFormatter.FMT, datefmt="%H:%M:%S")
    )

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    # stdout handler (Docker: stdout → log driver)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)
    stdout_handler.setFormatter(formatter)
    root.addHandler(stdout_handler)

    today = datetime.now().strftime("%Y%m%d")

    # Umumiy log fayl (INFO+)
    file_handler = RotatingFileHandler(
        f"logs/app_{today}.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Xato log fayl (ERROR+)
    error_handler = RotatingFileHandler(
        f"logs/error_{today}.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=30,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root.addHandler(error_handler)

    # Uchinchi tomon kutubxonalar shovqinini kamaytirish
    for noisy in ("uvicorn.access", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
