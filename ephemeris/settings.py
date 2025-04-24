import os
from dateutil import tz
from datetime import datetime, date
from pathlib import Path
from loguru import logger

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent

# File paths
CONFIG_PATH  = Path(os.getenv("CONFIG", str(BASE_DIR / "config.yaml")))
META_FILE    = Path(os.getenv("META_FILE", str(BASE_DIR / "feeds_meta.yaml")))
OUTPUT_PDF   = os.getenv("OUTPUT_PDF", "output/ephemeris.pdf")
DEFAULT_COVER = os.getenv("COVER_SVG_PATH", str(BASE_DIR / "assets/cover.pdf"))
FONTS_DIR = BASE_DIR / "fonts"

TIMEZONE = os.getenv("TIMEZONE", "UTC")
DATE_RANGE = os.getenv("DATE_RANGE")
TARGET_DATE = os.getenv("TARGET_DATE")

TZ_LOCAL = tz.gettz(TIMEZONE) or tz.tzutc()
EXCLUDE_BEFORE = int(os.getenv("EXCLUDE_BEFORE", "0"))
START_HOUR     = int(os.getenv("START_HOUR", "6"))
END_HOUR       = int(os.getenv("END_HOUR", "21"))
TIME_FORMAT    = os.getenv("TIME_FORMAT", "24")
USE_24H        = TIME_FORMAT == "24"

FORMAT       = os.getenv("FORMAT", "pdf").lower()
COVER_PAGE   = os.getenv("COVER_PAGE", "true").lower() not in ("0","false","no")

# Color defaults
EVENT_FILL      = os.getenv("EVENT_FILL", "gray14")
EVENT_STROKE    = os.getenv("EVENT_STROKE", "gray(20%)")
GRIDLINE_COLOR  = os.getenv("GRIDLINE_COLOR", "gray(20%)")
FOOTER_COLOR    = os.getenv("FOOTER_COLOR", "gray(60%)")

# Page layout
PDF_MARGIN_LEFT   = float(os.getenv("PDF_MARGIN_LEFT", 6))
PDF_MARGIN_RIGHT  = float(os.getenv("PDF_MARGIN_RIGHT", 6))
PDF_MARGIN_TOP    = float(os.getenv("PDF_MARGIN_TOP", 9))
PDF_MARGIN_BOTTOM = float(os.getenv("PDF_MARGIN_BOTTOM", 6))
MINICAL_ALIGN = os.getenv("MINICAL_ALIGN", "right").lower()
MINICAL_HEIGHT   = float(os.getenv("MINICAL_HEIGHT", 60))
MINICAL_GAP = float(os.getenv("MINICAL_GAP", 10))
ALLDAY_FROM   = os.getenv("ALLDAY_FROM",   "grid").lower()
MINICAL_TEXT_PADDING= float(os.getenv("MINICAL_TEXT_PADDING", 5))
MINICAL_OFFSET = float(os.getenv("MINICAL_OFFSET", 0))
PDF_GRID_BOTTOM_BUFFER = float(os.getenv("PDF_GRID_BOTTOM_BUFFER", 9))
DRAW_ALL_DAY  = os.getenv("DRAW_ALL_DAY",  "true").lower() in ("1","true","yes")
minical_mode = os.getenv("DRAW_MINICALS", "full").strip().lower()
DRAW_MINICALS = minical_mode not in ("false", "0", "no")
PDF_PAGE_SIZE= os.getenv("PDF_PAGE_SIZE", "1872x1404")  # Default to reMarkable 2
PDF_DPI = float(os.getenv("PDF_DPI", "226")) 
FOOTER = os.getenv("FOOTER", "E P H E M E R I S")

# Behavior
FORCE_REFRESH = os.getenv("FORCE_REFRESH", "false").lower() in ("1", "true", "yes")
DEBUG_LAYERS = os.getenv("DEBUG_LAYERS", "false").lower() in ("1", "true", "yes")

# Cover
COVER_WIDTH_FRAC = float(os.getenv("COVER_WIDTH_FRAC", 0.75))
COVER_VERT_FRAC = float(os.getenv("COVER_VERT_FRAC", 0.25))

# Date helpers
def today_date():
    return date.today()

def default_date_range():
    return [today_date()]
