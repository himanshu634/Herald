"""Send Herald's own log lines to stderr, so the API and worker terminals show each email's run."""

import logging

# Only Herald's loggers. A root handler at INFO would also print every httpx request (Gmail
# and Anthropic URLs) and the langgraph and sqlalchemy chatter.
_LOGGERS = ("herald_core", "herald_server")
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%H:%M:%S"))
    for name in _LOGGERS:
        logger = logging.getLogger(name)
        logger.setLevel(level.upper())
        # create_app runs once per test and on every reload: add the handler only once.
        if not any(getattr(h, "_herald", False) for h in logger.handlers):
            handler._herald = True  # type: ignore[attr-defined]
            logger.addHandler(handler)
        # propagate stays on: pytest's caplog reads records from the root logger. Root has no
        # handler under uvicorn or arq, so nothing prints twice.
