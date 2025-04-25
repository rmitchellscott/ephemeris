import sys
import os
from loguru import logger

def configure_logging(
    *,
    level: str = "INFO",
    colorize: bool = True,
    format=(
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <7}</level> | "
        "{message}"
    ),
):
    """
    Parameters:
    - level: minimum log level to output (e.g., "DEBUG", "INFO").
    - colorize: whether to use ANSI colors in the console.
    - format: Loguru format string for console output.
    """
    env_level = os.getenv("APP_LOG_LEVEL", "").upper()
    env_colorize = os.getenv("APP_LOG_COLORIZE", "").lower()
    env_format = os.getenv("APP_LOG_FORMAT", "")
    
    effective_level = env_level if env_level else (level or "INFO")
    effective_colorize = env_colorize in ("1", "true", "yes") if env_colorize else colorize
    effective_format = env_format if env_format else format
    
    logger.remove()

    # Custom levels
    logger.level("VISUAL", no=8, icon="🔍", color="<magenta>")
    logger.level("EVENTS",  no=9,  icon="📅", color="<magenta>")

    logger.add(
        sys.stdout,
        level=effective_level,
        colorize=effective_colorize,
        format=effective_format,
        enqueue=True,
    )
