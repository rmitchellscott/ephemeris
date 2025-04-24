import yaml
from loguru import logger

from ephemeris.utils import css_color_to_hex

def load_config(path: str = "config.yaml") -> dict:
    """Load calendar config and normalize colors."""
    with open(path, 'r', encoding='utf-8') as f:
        logger.debug("Loading configuration from {}", path)
        config = yaml.safe_load(f)
    for cal in config.get("calendars", []):
        cal["color"] = css_color_to_hex(cal.get("color", "#CCCCCC"))
    return config
