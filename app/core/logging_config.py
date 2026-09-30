"""Logging setup for the app's own `app.*` loggers."""
import logging
import sys

from app.core.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] [pid %(process)d] %(message)s"

_HANDLER_NAME = "app-stderr"


def configure_logging() -> None:
    """Sends `app.*` log records to stderr with timestamp, level and logger name.

    uvicorn only configures its own loggers, so without this, records from
    module-level `logging.getLogger(__name__)` loggers reached Python's
    last-resort handler: WARNING and above only, with no level or name.
    stderr is where uvicorn logs too, and it isn't block-buffered, so lines
    show up in `docker compose logs` straight away. Safe to call repeatedly.
    """
    logger = logging.getLogger("app")
    logger.setLevel(settings.LOG_LEVEL)
    if any(handler.get_name() == _HANDLER_NAME for handler in logger.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.set_name(_HANDLER_NAME)
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logger.addHandler(handler)
    # The handler above is the only output; don't also hand records to a
    # root handler someone else configures (that would log them twice).
    logger.propagate = False
