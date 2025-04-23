import os

import requests
from icalendar import Calendar as iCal

from .utils import css_color_to_hex


def load_raw_events(sources: list[dict]) -> list:
    """Download/parse ICS, extract VEVENTs with VTIMEZONE support."""
    # ... implementation ...
    return []
