import sys
import os
from loguru import logger

def configure_logging(
    *,
    level: str = "DEBUG",
    colorize: bool = True,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level.icon} {level: <7}</level> | "
        "{message}"
    ),
):
    """
    Parameters:
    - level: minimum log level to output (e.g., "DEBUG", "INFO").
    - colorize: whether to use ANSI colors in the console.
    - format: Loguru format string for console output.
    """
    env_level = os.getenv("LOG_LEVEL")
    effective_level = env_level if env_level else (level or "DEBUG")
    logger.remove()

    # Custom levels
    logger.level("VISUAL", no=8, icon="🔍", color="<magenta>")
    logger.level("EVENT",  no=9,  icon="📅", color="<blue>")

    logger.add(
        sys.stdout,
        level=effective_level,
        colorize=colorize,
        format=format,
        enqueue=True,
    )
