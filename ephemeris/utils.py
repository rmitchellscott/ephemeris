# Standard
import os
import re
from datetime import datetime, timedelta, date

import webcolors
from dateutil import tz

USE_24H = os.getenv("TIME_FORMAT", "24") == "24"

# Local: none

def css_color_to_hex(name_or_hex: str) -> str:
    """Convert CSS color to 6-digit hex."""
    # ... implementation ...
    pass


def fmt_time(dt: datetime) -> str:
    if USE_24H:
        return dt.strftime("%H:%M")
    return dt.strftime("%-I:%M %p")


def parse_date_range(s: str, tzinfo: tz.tzinfo) -> list[date]:
    # ... full implementation ...
    pass
