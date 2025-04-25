import os
from dateutil import tz
from datetime import datetime, date
from pathlib import Path
from loguru import logger

# Project root
BASE_DIR = Path(__file__).resolve().parent.parent

# File paths
CONFIG_PATH  = Path(os.getenv("APP_CONFIG_PATH", str(BASE_DIR / "config.yaml")))
META_FILE    = Path(os.getenv("APP_META_FILE_PATH", str(BASE_DIR / "feeds_meta.yaml")))
OUTPUT_PDF   = os.getenv("APP_OUTPUT_PATH", "output/ephemeris.pdf")
DEFAULT_COVER = os.getenv("DOC_COVER_SVG_PATH", str(BASE_DIR / "assets/cover.svg"))
FONTS_DIR = BASE_DIR / "fonts"

TIMEZONE = os.getenv("TIME_ZONE", "UTC")
DATE_RANGE = os.getenv("TIME_DATE_RANGE", "today")

TZ_LOCAL = tz.gettz(TIMEZONE) or tz.tzutc()
EXCLUDE_BEFORE = int(os.getenv("TIME_FILTER_MIN_HOUR", "0"))
START_HOUR     = int(os.getenv("TIME_DISPLAY_START", "6"))
END_HOUR       = int(os.getenv("TIME_DISPLAY_END", "21"))
TIME_FORMAT    = os.getenv("TIME_FORMAT", "24")
USE_24H        = TIME_FORMAT == "24"

FORMAT       = os.getenv("APP_OUTPUT_FORMAT", "pdf").lower()
COVER_PAGE   = os.getenv("DOC_COVER_ENABLED", "true").lower() not in ("0","false","no")

# Color defaults
EVENT_FILL      = os.getenv("DOC_EVENT_FILL_COLOR", "gray14")
EVENT_STROKE    = os.getenv("DOC_EVENT_BORDER_COLOR", "gray(20%)")
GRIDLINE_COLOR  = os.getenv("DOC_GRID_LINE_COLOR", "gray(20%)")
FOOTER_COLOR    = os.getenv("DOC_FOOTER_COLOR", "gray(60%)")

# Page layout
PDF_MARGIN_LEFT   = float(os.getenv("DOC_MARGIN_LEFT", 6))
PDF_MARGIN_RIGHT  = float(os.getenv("DOC_MARGIN_RIGHT", 6))
PDF_MARGIN_TOP    = float(os.getenv("DOC_MARGIN_TOP", 9))
PDF_MARGIN_BOTTOM = float(os.getenv("DOC_MARGIN_BOTTOM", 6))
MINICAL_ALIGN = os.getenv("DOC_MINICAL_ALIGN", "right").lower()
MINICAL_HEIGHT   = float(os.getenv("DOC_MINICAL_HEIGHT", 60))
MINICAL_GAP = float(os.getenv("DOC_MINICAL_SPACING", 10))
ALLDAY_FROM   = os.getenv("DOC_ALLDAY_BOUNDARY",   "grid").lower()
MINICAL_TEXT_PADDING= float(os.getenv("DOC_MINICAL_TEXT_PADDING", 5))
MINICAL_OFFSET = float(os.getenv("DOC_MINICAL_POSITION_OFFSET", 0))
PDF_GRID_BOTTOM_BUFFER = float(os.getenv("DOC_GRID_BOTTOM_PADDING", 9))
DRAW_ALL_DAY  = os.getenv("DOC_ALLDAY_MODE",  "true").lower() in ("1","true","yes")
minical_mode = os.getenv("DOC_MINICAL_MODE", "full").strip().lower()
DRAW_MINICALS = minical_mode not in ("false", "0", "no", "disabled", "disable")
PDF_PAGE_SIZE= os.getenv("DOC_PAGE_DIMENSIONS", "1404x1872")  # Default to reMarkable 2
PDF_DPI = float(os.getenv("DOC_PAGE_DPI", "226")) 
FOOTER = os.getenv("DOC_FOOTER_TEXT", "E P H E M E R I S")

# Behavior
FORCE_REFRESH = os.getenv("APP_FORCE_REFRESH", "false").lower() in ("1", "true", "yes")

# Cover
COVER_WIDTH_FRAC = float(os.getenv("DOC_COVER_WIDTH_SCALE", 0.75))
COVER_VERT_FRAC = float(os.getenv("DOC_COVER_VERTICAL_POSITION", 0.25))

# Date helpers
def today_date():
    return date.today()

def default_date_range():
    return [today_date()]
