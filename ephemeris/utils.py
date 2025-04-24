# Standard
import os
import re
from datetime import datetime, timedelta, date
import calendar

import webcolors
from dateutil import tz

USE_24H = os.getenv("TIME_FORMAT", "24") == "24"

# Local: none

def css_color_to_hex(name_or_hex: str) -> str:
    """
    Convert a CSS color name, functional gray(%), or hex code to a 6-digit hex code.

    - Leaves valid hex codes unchanged.
    - Parses CSS4 gray(%) syntax.
    - Custom mapping for grayscale class names gray0–gray15, with aliases for black and white.
    - Falls back to standard CSS color names via webcolors.
    """

    if name_or_hex.startswith("#"):
        return name_or_hex

    lower = name_or_hex.lower().strip()

    m_pct = re.fullmatch(r'gray\(\s*([0-9]+(?:\.[0-9]+)?)%\s*\)', lower)
    if m_pct:
        pct = float(m_pct.group(1))
        level = round(255 * pct / 100)
        return f"#{level:02X}{level:02X}{level:02X}"

    if lower in ('black', 'gray0'):
        return '#000000'
    if lower in ('white', 'gray15'):
        return '#FFFFFF'

    m = re.fullmatch(r'gray([0-9]|1[0-5])', lower)
    if m:
        n = int(m.group(1))
        level = n * 17
        return f"#{level:02X}{level:02X}{level:02X}"

    try:
        return webcolors.name_to_hex(name_or_hex)
    except ValueError:
        print(f"⚠️ Unknown CSS color '{name_or_hex}', passing through")
        return name_or_hex


def fmt_time(dt):
    """
    Return a HH:MM or h:MM AM/PM string based on USE_24H.
    """
    if USE_24H:
        return dt.strftime("%H:%M")
    else:
        return dt.strftime("%-I:%M %p")


def parse_date_range(s: str, tzinfo) -> list[date]:
    """Given “YYYY‑MM‑DD:YYYY‑MM‑DD”, “this week”, “this month” or a single date,
    return a list of date objects in that range (inclusive)."""
    s = s.strip().strip('"').strip("'")
    s = s.lower()
    today = datetime.now(tz=tzinfo).date()

    if s in ("day", "today"):
        return [today]
    if s in ("week",):
        s = "this week"
    if s in ("month",):
        s = "this month"
    if s == "this week":
        # Assuming week = Sunday–Saturday
        offset = (today.weekday() + 1) % 7
        start = today - timedelta(days=offset)
        end = start + timedelta(days=6)
    elif s == "this month":
        start = today.replace(day=1)
        last_day = calendar.monthrange(start.year, start.month)[1]
        end = start.replace(day=last_day)
    elif re.search(r"[:/]", s):
        sep = ":" if ":" in s else "/"
        a, b = s.split(sep, 1)
        start = datetime.strptime(a.strip(), "%Y-%m-%d").date()
        end   = datetime.strptime(b.strip(), "%Y-%m-%d").date()
    elif " to " in s:
        a, b = re.split(r"\s+to\s+", s)
        start = datetime.strptime(a, "%Y-%m-%d").date()
        end   = datetime.strptime(b, "%Y-%m-%d").date()
    else:
        # single date
        start = end = datetime.strptime(s, "%Y-%m-%d").date()

    if start > end:
        raise ValueError(f"Start date {start} after end date {end}")
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]
