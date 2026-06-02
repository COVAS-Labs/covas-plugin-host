from __future__ import annotations

import logging
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def log(level: str, *args: Any) -> None:
    message = " ".join(str(arg) for arg in args)
    normalized = level.lower()
    if normalized == "warn":
        normalized = "warning"
    logger = logging.getLogger("covas-plugin-host")
    log_fn = getattr(logger, normalized, logger.info)
    log_fn(message)
