import sys
from logging import (
    ERROR,
    FATAL,
    WARNING,
    Formatter,
    StreamHandler,
    addLevelName,
    basicConfig,
)


def configure_logging() -> None:
    errorHandler = StreamHandler(sys.stderr)
    errorHandler.setFormatter(Formatter("%(levelname)s: %(message)s"))
    errorHandler.setLevel(WARNING)
    basicConfig(handlers=[errorHandler])
    addLevelName(WARNING, "warn")
    addLevelName(ERROR, "error")
    addLevelName(FATAL, "fatal")
