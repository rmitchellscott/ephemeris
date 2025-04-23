import os
from dateutil import tz
from datetime import datetime, date

# Environment-driven constants
TIMEZONE     = os.getenv("TIMEZONE", "UTC")
TZ_LOCAL     = tz.gettz(TIMEZONE)
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

# File paths
CONFIG_PATH      = os.getenv("CONFIG", "config.yaml")
OUTPUT_PDF       = os.getenv("OUTPUT_PDF", "output/ephemeris.pdf")
META_FILE        = os.getenv("META_FILE", "feeds_meta.yaml")
FONTS_DIR        = os.path.join(os.path.dirname(__file__), "fonts")

# Date helpers
def today_date():
    return date.today()

def default_date_range():
    return [today_date()]
