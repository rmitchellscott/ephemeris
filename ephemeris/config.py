import os
import yaml
from utils import css_color_to_hex

def load_config(path: str = "config.yaml") -> dict:
    """Load calendar config and normalize colors."""
    with open(path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    for cal in config.get("calendars", []):
        cal["color"] = css_color_to_hex(cal.get("color", "#CCCCCC"))
    return config

def load_meta() -> dict:
    """
    Load metadata from META_FILE. Return {} if missing or invalid.
    """
    if META_FILE.exists() and META_FILE.is_file():
        try:
            data = yaml.safe_load(META_FILE.read_text())
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if k in ("_last_anchor", "events_hash")}
        except Exception as e:
            print(f"⚠️ Failed to parse meta file: {e}, using empty metadata.")
    return {}

def save_meta(meta: dict) -> None:
    """
    Save metadata to META_FILE, only writing expected keys.
    """
    to_write = {k: meta[k] for k in ("_last_anchor", "events_hash") if k in meta}
    try:
        META_FILE.parent.mkdir(parents=True, exist_ok=True)
        META_FILE.write_text(yaml.safe_dump(to_write))
    except Exception as e:
        print(f"⚠️ Failed to write meta file: {e}")
