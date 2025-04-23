import os
from io import StringIO
import sys
import copy
import hashlib
from pathlib import Path
from tempfile import NamedTemporaryFile
from itertools import chain
from collections import defaultdict, deque, Counter
from datetime import datetime, timedelta, time, date
import calendar
from math import floor

import yaml
import requests
import pytz
import webcolors
import re

from dateutil import tz
from dateutil.rrule import rrulestr

from icalendar import Calendar as iCal

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.ttfonts import TTFont
from pdfrw import PdfReader
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl
from PyPDF2 import PdfMerger

DEBUG_LAYERS = os.getenv("DEBUG_LAYERS", "false").lower() in ("1", "true", "yes")

timezone_str = os.getenv("TIMEZONE", "UTC")
EXCLUDE_BEFORE = int(os.getenv("EXCLUDE_BEFORE", "0"))
START_HOUR = int(os.getenv("START_HOUR", "6"))
END_HOUR = int(os.getenv("END_HOUR", "21"))
TIME_FORMAT = os.getenv("TIME_FORMAT", "24")
USE_24H = TIME_FORMAT == "24"

FORMAT = os.getenv("FORMAT", "pdf").lower()
TIMEZONE = tz.gettz(timezone_str)
tz_local  = TIMEZONE

EVENT_FILL = os.getenv("EVENT_FILL", "gray14")
EVENT_STROKE = os.getenv("EVENT_STROKE", "gray(20%)")
GRIDLINE_COLOR = os.getenv("GRIDLINE_COLOR", "gray(20%)")
FOOTER_COLOR = os.getenv("FOOTER_COLOR", "gray(60%)")

print("Timezone:", timezone_str)
CONFIG_PATH = "config.yaml"
OUTPUT_PDF = "output/daily_schedule.pdf"
COVER_PAGE = os.getenv("COVER_PAGE", "true").lower() not in ("0", "false", "no")
META_FILE = Path("feeds_meta.yaml")
FORCE_REFRESH = os.getenv("FORCE_REFRESH", "false").lower() in ("1", "true", "yes")

BASE_DIR = Path(__file__).resolve().parent
FONTS_DIR = BASE_DIR / "fonts"

pdfmetrics.registerFont(TTFont("Montserrat-ExtraLight", str(FONTS_DIR / "Montserrat-ExtraLight.ttf")))
pdfmetrics.registerFont(TTFont("Montserrat-Regular",   str(FONTS_DIR / "Montserrat-Regular.ttf")))
pdfmetrics.registerFont(TTFont("Montserrat-Bold",   str(FONTS_DIR / "Montserrat-Bold.ttf")))
pdfmetrics.registerFont(TTFont("Montserrat-SemiBold",   str(FONTS_DIR / "Montserrat-SemiBold.ttf")))
pdfmetrics.registerFont(TTFont("Montserrat-Light",   str(FONTS_DIR / "Montserrat-Light.ttf")))

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

def load_config():
    config_path = os.environ.get("CONFIG", "config.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    for cal in config.get("calendars", []):
        raw = cal.get("color", "#CCCCCC")
        cal["color"] = css_color_to_hex(raw)

    return config

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

def draw_gray_strip(c, page_width, strip_height=20):
    """
    Draws a horizontal strip of gray0–gray15 at the bottom of the canvas.
    - c: ReportLab canvas
    - page_width: width of the page in points
    - strip_height: height of the strip in points
    """
    swatch_width = page_width / 16.0
    y = 0  # bottom of page
    for i in range(16):
        hexcode = css_color_to_hex(f"gray{i}")
        c.setFillColor(HexColor(hexcode))
        c.rect(i * swatch_width, y, swatch_width, strip_height, stroke=0, fill=1)

def pixels_to_points(pixels, dpi=226):
    return pixels * 72 / dpi

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

def compute_events_hash(raw_events: list[tuple]) -> str:
    """
    Compute a SHA256 hash over all VEVENT components and calendar names.
    Sorts entries for deterministic ordering.
    """
    items = []
    for comp, color, tzf, name in raw_events:
        # make a shallow copy so we don’t destroy the in‑memory comp
        comp2 = copy.deepcopy(comp)
        # drop fields that change on each to_ical()
        for prop in ("DTSTAMP", "CREATED", "LAST‑MODIFIED", "SEQUENCE"):
            comp2.pop(prop, None)
        ical_bytes = comp2.to_ical()
        items.append((name, ical_bytes))
    items.sort(key=lambda x: (x[0], hashlib.sha256(x[1]).hexdigest()))
    h = hashlib.sha256()
    for name, ical_bytes in items:
        h.update(name.encode())
        h.update(ical_bytes)
    return h.hexdigest()

def draw_mini_cal(c, year, month, weeks, x, y, mini_w, mini_h, highlight_day=None):
    # Month label
    c.setFont("Montserrat-Regular", 6)
    month_name = calendar.month_name[month]
    c.drawCentredString(x + mini_w/2, y + mini_h + 4, f"{month_name} {year}")

    # Weekday headers
    days   = ['S','M','T','W','T','F','S']
    cell_w = mini_w / 7
    cell_h = 8

    c.setFont("Montserrat-Regular", 6)
    for i, d in enumerate(days):
        hx = x + i*cell_w + cell_w/2
        c.drawCentredString(hx, y + mini_h - 6, d)

    # Day numbers
    for row_i, week in enumerate(weeks):
        for col_i, day in enumerate(week):
            if day == 0:
                continue

            # compute the top‑left of this cell
            xx = x + col_i*cell_w
            yy = y + mini_h - 8 - (row_i+1)*cell_h

            # center of the cell
            cx = xx + cell_w/2
            # vertical offset: roughly center. adjust v_off if you like.
            v_off = cell_h/2 - 2

            if highlight_day and day == highlight_day:
                # draw black highlight box
                c.setFillColor(black)
                c.rect(xx, yy, cell_w, cell_h, stroke=0, fill=1)

                # draw the day number in white, centered
                c.setFillColor(white)
                c.setFont("Montserrat-SemiBold", 6)
                c.drawCentredString(cx, yy + v_off, str(day))

                # reset
                c.setFillColor(black)
                c.setFont("Montserrat-Regular", 6)

            else:
                # normal day, centered
                c.drawCentredString(cx, yy + v_off, str(day))
def get_page_size():
    env_size = os.getenv("PDF_PAGE_SIZE", "1404x1872")  # Default to reMarkable 2
    env_dpi = float(os.getenv("PDF_DPI", "226"))        # Default to reMarkable 2 DPI
    try:
        px_width, px_height = map(int, env_size.lower().split("x"))
        width_pt = pixels_to_points(px_width, dpi=env_dpi)
        height_pt = pixels_to_points(px_height, dpi=env_dpi)
        return width_pt, height_pt
    except Exception as e:
        print(f"⚠️ Invalid PDF_PAGE_SIZE or PDF_DPI: {e}. Using fallback letter size.")
        return letter


def load_calendars_from_config(config):
    """
    Load calendars from config entries, parsing each ICS source (URL or file)
    with full VTIMEZONE support via icalendar and dateutil.tz.tzical,
    while filtering out unsupported X- properties.
    Returns list of (start_dt, end_dt, title, color).
    """
    all_events = []

    for entry in config["calendars"]:
        name   = entry["name"]
        color  = entry.get("color", "#CCCCCC")
        source = entry["source"]

        if source.startswith("http"):
            print(f"🔗 Downloading {name} from {source}...")
            resp = requests.get(source)
            resp.raise_for_status()
            raw = resp.content
        else:
            print(f"📂 Loading calendar '{name}' from file: {source}")
            with open(source, "rb") as f:
                raw = f.read()

        cal = iCal.from_ical(raw)

        vtz_blocks = []
        for comp in cal.walk():
            if comp.name == "VTIMEZONE":
                # drop any X- properties that dateutil.tzical can't handle
                for prop in list(comp.keys()):
                    if prop.upper().startswith("X-"):
                        comp.pop(prop, None)
                vtz_blocks.append(comp.to_ical())

        if vtz_blocks:
            with NamedTemporaryFile(mode="wb", suffix=".ics", delete=False) as tf:
                for block in vtz_blocks:
                    tf.write(block)
                tf.flush()
                tz_factory = tz.tzical(tf.name)
        else:
            tz_factory = None  # fallback to UTC

        for comp in cal.walk():
            if comp.name != "VEVENT":
                continue

            try:
                start = comp.decoded("dtstart")
                end   = comp.decoded("dtend")
            except KeyError as e:
                summary = comp.get("SUMMARY", "Untitled")
                uid     = comp.get("UID", "<no‑uid>")
                print(f"⚠️ Skipping event without {e!r}: '{summary}' (UID={uid})")
                continue

            dtend_prop = comp.get("dtend")
            if dtend_prop is not None:
                end = comp.decoded("dtend")
            else:
                dur_prop = comp.get("duration")
                if dur_prop is not None:
                    duration = comp.decoded("duration")
                    end = start + duration
                else:
                    end = start

            tzid = comp["dtstart"].params.get("TZID")
            if start.tzinfo is None:
                if tz_factory and tzid in tz_factory._ttinfo_cache:
                    start = start.replace(tzinfo=tz_factory.get(tzid))
                else:
                    start = start.replace(tzinfo=tz.UTC)
            if end.tzinfo is None:
                if tz_factory and tzid in tz_factory._ttinfo_cache:
                    end = end.replace(tzinfo=tz_factory.get(tzid))
                else:
                    end = end.replace(tzinfo=tz.UTC)

            title = str(comp.get("summary", "Untitled"))
            all_events.append((start, end, title, {"calendar_color": color}))

    return sorted(all_events, key=lambda x: x[0])



def filter_events_for_day(events, target_date):
    """
    Given loader’s (start, end, title, meta) tuples,
    keep only those that:
      • start on target_date in local time,
      • start hour ≥ MIN_START_HOUR,
      • title does NOT contain “canceled”,
      • duration ≥ 15 minutes.
    """
    cancel_variants = ("cancelled", "canceled")
    kept = []
    for start, end, title, meta in events:
        local_start = start.astimezone(tz_local)
        # 1) same local day
        if local_start.date() != target_date:
            continue
        if local_start.hour < EXCLUDE_BEFORE:
            print(f"⏰  Dropped (too early): {title!r} at hour {local_start.hour}")
            continue
        if local_start.hour >= END_HOUR:
            print(f"⏰  Dropped (after end hour): {title!r} at {local_start.hour}")
            continue
        # 3) not canceled
        title_lower     = title.lower()
        status          = meta.get("status", "").lower()
        if any(v in title_lower for v in cancel_variants) or status in cancel_variants:
            if any(v in title_lower for v in cancel_variants):
                print(f"❌  Dropped (cancelled): {title!r}")
            continue
        # 4) duration at least 15 min
        duration_min = (end - start).total_seconds() / 60.0
        if duration_min < 15.0:
            print(f"⌛  Dropped (too short {duration_min:.1f} min): {title!r}")
            continue
        kept.append((start, end, title, meta))

    return sorted(kept, key=lambda x: x[0])

def expand_recurring_event(event, target_date):


    instances = []

    start = event.begin.datetime
    end = event.end.datetime

    if start.tzinfo is None:
        start = pytz.UTC.localize(start)
    if end.tzinfo is None:
        end = pytz.UTC.localize(end)

    # If no recurrence rule, just return single instance on matching day
    rrule_str = event.extra_fields.get('rrule') if hasattr(event, 'extra_fields') else None
    if not rrule_str:
        if start.date() == target_date:
            start_local = start.astimezone(tz_local)
            end_local   = end.astimezone(tz_local)
            # merge in the UID
            meta = dict(event.extra_fields)
            meta["uid"] = uid
            instances.append((start_local, end_local, event.name, meta))
        return instances


    # Build rule and get occurrences
    rule = rrulestr(rrule_str, dtstart=start)
    for occ in rule.between(day_start, day_end, inc=True):
        start_inst  = occ
        end_inst    = occ + (end - start)
        start_local = start_inst.astimezone(tz_local)
        end_local   = end_inst.astimezone(tz_local)
        # merge UID into the meta dict
        meta = dict(event.extra_fields)
        meta["uid"] = uid
        instances.append((start_local, end_local, event.name, meta))

    return instances

def assign_stacks(events):
    # Helper to detect overlap
    def overlaps(e1, e2):
        return e1[0] < e2[1] and e2[0] < e1[1]

    # Build overlap graph
    graph = defaultdict(set)
    for i in range(len(events)):
        for j in range(i + 1, len(events)):
            if overlaps(events[i], events[j]):
                graph[i].add(j)
                graph[j].add(i)

    # Find clusters via BFS
    visited = set()
    clusters = []
    for i in range(len(events)):
        if i not in visited:
            queue = deque([i])
            cluster = []
            while queue:
                node = queue.popleft()
                if node not in visited:
                    visited.add(node)
                    cluster.append(node)
                    queue.extend(graph[node])
            clusters.append(cluster)

    result = []
    for cluster in clusters:
        # Prepare list of (idx, event)
        cluster_events = [(i, events[i]) for i in cluster]

        # Dynamic layer assignment: longer events first
        layers = []         # list of lists of (start,end)
        assignments = {}    # event idx -> layer index

        # Sort by duration descending, then by start ascending
        sorted_by_duration = sorted(
            cluster_events,
            key=lambda x: (-(x[1][1] - x[1][0]).total_seconds(), x[1][0])
        )

        for idx, (start, end, title, meta) in sorted_by_duration:
            placed = False
            for layer_index, layer in enumerate(layers):
                # if no overlap with existing items in this layer
                if all(end <= s or start >= e for (s, e) in layer):
                    layer.append((start, end))
                    assignments[idx] = layer_index
                    placed = True
                    break
            if not placed:
                # new layer
                layers.append([(start, end)])
                assignments[idx] = len(layers) - 1

        max_depth = len(layers)
        # ── DEBUG DUMP ─────────────────────────────
        if DEBUG_LAYERS:
            print("🔍  Debug: event layers for this cluster:")
            for idx, (start, end, title, meta) in cluster_events:
                li = assignments[idx]              # safe now, idx ∈ cluster
                ts = lambda dt: dt.astimezone(tz_local).strftime("%H:%M")
                clean_title = str(title)    # title is your vText instance
                print(f"   • Layer {li}: {clean_title} [{ts(start)} → {ts(end)}]")
            print("🔍  End debug dump\n")
        # ────────────────────────────────────────────

        # Compute width fraction for each event in cluster
        for idx, (start, end, title, meta) in cluster_events:
            layer_index = assignments[idx]
            width_frac  = (max_depth - layer_index) / max_depth
            result.append({
                "start":       start,
                "end":         end,
                "title":       title,
                "meta":        meta,
                "width_frac":  width_frac,
                "layer_index": layer_index
            })

    return result

def init_text_helpers(hour_height):
    H30 = hour_height / 2.0
    H15 = H30 / 2.0

    # title sizes
    title15 = 0.75 * H15
    title30 = 0.50 * H30

    # time sizes (cap 15‑min at the 30‑min size)
    time30       = 0.33 * H30
    time15_uncap = 0.75 * H15
    time15       = min(time15_uncap, time30)

    # grab font metrics
    face = pdfmetrics.getFont("Montserrat-Regular").face

    def compute_baseline_offset(box_h, fs):
        ascent  = face.ascent  / 1000 * fs
        descent = face.descent / 1000 * fs
        return (box_h + ascent + descent) / 2.0

    def get_title_font_and_offset(d):
        fs = title15 if d == 15 else title30
        if   d == 15: box_h = H15
        elif d <= 30: box_h = H30 * (d / 30.0)
        else:          box_h = H30
        return fs, compute_baseline_offset(box_h, fs)

    def get_time_font_and_offset(d):
        fs = time15 if d == 15 else time30
        if   d == 15: box_h = H15
        elif d <= 30: box_h = H30 * (d / 30.0)
        else:          box_h = H30
        return fs, compute_baseline_offset(box_h, fs)

    return get_title_font_and_offset, get_time_font_and_offset

def draw_centered_multiline(
    c,
    lines,
    font_name,
    font_size,
    x,
    band_bottom,
    band_height,
    line_spacing=1.2
):
    face     = pdfmetrics.getFont(font_name).face
    ascent   = face.ascent  / 1000 * font_size
    descent  = abs(face.descent) / 1000 * font_size

    line_height  = font_size * line_spacing

    # ── BASELINE CALCULATION ────────────────────────
    # center of band minus half of (text block center offset)
    y_first = (
        band_bottom
        + (band_height / 2)
        - (line_height + ascent - descent) / 2
    )

    c.setFont(font_name, font_size)
    for i, line in enumerate(lines):
        y = y_first + (len(lines)-1 - i) * line_height
        c.drawString(x, y, line)

def get_layout_config(width, height, start_hour=6, end_hour=17):
    # Raw page margins from environment
    page_left   = float(os.getenv("PDF_MARGIN_LEFT", 6))
    page_right  = width - float(os.getenv("PDF_MARGIN_RIGHT", 6))
    page_top    = height - float(os.getenv("PDF_MARGIN_TOP", 9))
    page_bottom = float(os.getenv("PDF_MARGIN_BOTTOM", 6))

    # Fixed dimensions
    time_label_width = 26  # width reserved for the HH:MM column
    heading_size   = 12
    heading_ascent = heading_size * 0.75
    element_pad      = 8
    text_padding     = 5

    # Mini-calendar block dimensions
    mini_block_h   = float(os.getenv("MINICAL_HEIGHT", 60))
    mini_block_gap = float(os.getenv("MINICAL_GAP", 10))
    mini_text_pad = float(os.getenv("MINICAL_TEXT_PADDING", 5))

    # Buffer below time grid
    bottom_buffer = float(os.getenv("PDF_GRID_BOTTOM_BUFFER", 9))

    # Feature Flags Affecting Grid
    minical_mode = os.getenv("DRAW_MINICALS", "full").strip().lower()
    DRAW_MINICALS = minical_mode not in ("false", "0", "no")
    DRAW_ALL_DAY  = os.getenv("DRAW_ALL_DAY",  "true").lower() in ("1","true","yes")

    # Compute vertical extents for the grid
    grid_top    = page_top - heading_ascent - (4 * element_pad)

    grid_bottom = page_bottom + bottom_buffer

    # Compute horizontal extents for the grid
    grid_left  = page_left + time_label_width
    grid_right = page_right

    # Recompute grid_top so it floats up when we skip the minis or all‑day band
    # Start from the page_top
    if DRAW_MINICALS:
        # subtract the vertical space occupied by the two mini‑cals + padding
        mini_total_height = mini_block_h + (2 * mini_text_pad)
        grid_top -= mini_total_height

    if DRAW_ALL_DAY:
        if not DRAW_MINICALS:
        # note: band_height is mini_h + 2*mini_text_pad in your code
            band_height = mini_block_h + (2 * mini_text_pad)
            grid_top -= band_height

    # How many hours will be shown
    hours_shown  = end_hour - start_hour
    available_h  = grid_top - grid_bottom
    hour_height  = available_h / hours_shown

    return {
        "grid_top":         grid_top,
        "grid_bottom":      grid_bottom,
        "grid_left":        grid_left,
        "grid_right":       grid_right,
        "hour_height":      hour_height,
        "start_hour":       start_hour,
        "end_hour":         end_hour,
        "time_label_width": time_label_width,
        "heading_size":     heading_size,
        "page_left":        page_left,
        "page_right":       page_right,
        "page_top":         page_top,
        "element_pad":      element_pad,
        "heading_ascent":   heading_ascent,
        "mini_text_pad":    mini_text_pad,
        "mini_block_gap":   mini_block_gap,
        "text_padding":     text_padding,
        "page_bottom":      page_bottom,
        "mini_block_h":     mini_block_h,

    }
def time_to_y(dt, layout):
    # Convert a datetime to a vertical position inside the grid
    elapsed = (dt.hour + dt.minute / 60) - layout["start_hour"]
    return layout["grid_top"] - elapsed * layout["hour_height"]

def draw_rect_with_optional_round(c, x, y, w, h, radius,
                                  round_top=True, round_bottom=True,
                                  stroke=1, fill=1):
    """
    Draws a rectangle at (x,y) of width w, height h.
    If round_bottom is True, rounds the bottom two corners with `radius`.
    If round_top is   True, rounds the top two corners.
    Otherwise corners are square.
    """
    p = c.beginPath()
    # start at bottom-left
    if round_bottom:
        p.moveTo(x + radius, y)
    else:
        p.moveTo(x, y)

    # bottom edge
    if round_bottom:
        p.lineTo(x + w - radius, y)
        p.arcTo(x + w - 2*radius, y, x + w, y + 2*radius,
                startAng=270, extent=90)
    else:
        p.lineTo(x + w, y)

    # right edge
    if round_top:
        p.lineTo(x + w, y + h - radius)
        p.arcTo(x + w - 2*radius, y + h - 2*radius, x + w, y + h,
                startAng=0, extent=90)
    else:
        p.lineTo(x + w, y + h)

    # top edge
    if round_top:
        p.lineTo(x + radius, y + h)
        p.arcTo(x, y + h - 2*radius, x + 2*radius, y + h,
                startAng=90, extent=90)
    else:
        p.lineTo(x, y + h)

    # left edge
    if round_bottom:
        p.lineTo(x, y + radius)
        p.arcTo(x, y, x + 2*radius, y + 2*radius,
                startAng=180, extent=90)
    else:
        p.lineTo(x, y)

    c.drawPath(p, stroke=stroke, fill=fill)

def render_time_grid(c, date_label, layout):
    # Vertical line
    c.setStrokeColor(css_color_to_hex(GRIDLINE_COLOR))
    c.setLineWidth(0.5)
    c.line(
        layout["grid_left"] +0.25,
        layout["grid_bottom"] + 1,
        layout["grid_left"] +0.25,
        layout["grid_top"] + 0.25
    )

    # Draw the grid heading
    c.setStrokeColor(css_color_to_hex(GRIDLINE_COLOR))
    c.setFont("Montserrat-SemiBold", 10)
    c.drawString((layout["grid_left"] +0.25), (layout["grid_top"] + 0.25 + layout["text_padding"]), "Schedule")

    # Draw the horizontal hour lines and labels
    for hour in range(layout["start_hour"], layout["end_hour"] + 1):
        y = time_to_y(datetime.combine(date_label, time(hour=hour)), layout)
        # Emphasize the start hour
        if hour == layout["start_hour"]:
            c.setStrokeGray(0)
            c.setLineWidth(1)
        else:
            c.setStrokeColor(css_color_to_hex(GRIDLINE_COLOR))
            c.setLineWidth(0.5)
        c.line(layout["grid_left"], y, layout["grid_right"], y)
        # Draw the time label
        c.setFillGray(0.2)
        c.setFont("Montserrat-SemiBold", 7)
        label = f"{hour:02}:00" if USE_24H else datetime.combine(date_label, time(hour=hour)).strftime("%-I %p")
        c.drawRightString(
            layout["grid_left"] - 5,
            y - 2,
            label
        )


def load_raw_events(config):
    """
    Returns a list of (icalendar.Event component, calendar_color, tz_factory).
    """
    raw_events = []
    names = [e["name"] for e in config["calendars"]]
    print(f"⚙️ Loading {len(names)} calendars: {names!r}")
    for entry in config["calendars"]:
        name, color, source = entry["name"], entry.get("color","#CCCCCC"), entry["source"]

        # fetch bytes
        if source.startswith("http"):
            resp = requests.get(source); resp.raise_for_status()
            raw = resp.content
        else:
            with open(source, "rb") as f:
                raw = f.read()

        # parse and build tz factory
        cal = iCal.from_ical(raw)
        vtz_blocks = [comp for comp in cal.walk() if comp.name=="VTIMEZONE"]
        if vtz_blocks:
            with NamedTemporaryFile(mode="wb", suffix=".ics", delete=False) as tf:
                for comp in vtz_blocks:
                    # strip out X-… props
                    for p in list(comp.keys()):
                        if p.upper().startswith("X-"):
                            comp.pop(p, None)
                    tf.write(comp.to_ical())
                tf.flush()
                tz_factory = tz.tzical(tf.name)
        else:
            tz_factory = None

        # collect every VEVENT
        for comp in cal.walk():
            if comp.name == "VEVENT":
                raw_events.append((comp, color, tz_factory, name))

    return raw_events

def split_all_day_events(events, target_date, tz_local):
    """
    Returns (all_day_events, timed_events).
    An event is “all‑day” if meta['all_day'] is truthy OR
    it spans midnight at start-of-day to midnight after.
    """
    all_day, timed = [], []
    next_day = target_date + timedelta(days=1)
    start_of_day = datetime.combine(target_date, time.min).replace(tzinfo=tz_local)
    start_of_next = datetime.combine(next_day,   time.min).replace(tzinfo=tz_local)

    for start, end, title, meta in events:
        ls = start.astimezone(tz_local)
        le = end.astimezone(tz_local)

        is_flagged = meta.get("all_day", False)
        spans_midnight = ls <= start_of_day and le >= start_of_next

        if is_flagged or spans_midnight:
            all_day.append((start, end, title, meta))
        else:
            timed.append((start, end, title, meta))

    return all_day, timed

def expand_event_for_day(comp, color, tz_factory, target_date, tz_local):
    """
    comp:       an icalendar.VEvent
    color:      hex color for the calendar
    tz_factory: a dateutil tzical or None
    target_date: date we’re expanding for
    tz_local:   local tzinfo
    """
    # ─────────── 0) Grab the UID up front ───────────
    uid = comp.get("UID")
    overrides = override_map.get(uid, set())
    if uid is None:
        print(f"⚠️  Event has no UID: SUMMARY={comp.get('SUMMARY')!r}")

    instances = []

    # ─────────── decode DTSTART / DTEND ───────────
    start = comp.decoded("dtstart")
    if comp.get("dtend"):
        end = comp.decoded("dtend")
    elif comp.get("duration"):
        end = start + comp.decoded("duration")
    else:
        # fallback: treat as zero‑length
        end = start

    # ─────────── 1) All‑day branch ───────────
    if isinstance(start, date) and not isinstance(start, datetime):
        if start != target_date:
            return []
        end_date = comp.decoded("dtend")
        st = datetime.combine(start, time.min).replace(tzinfo=tz_local)
        en = datetime.combine(end_date, time.min).replace(tzinfo=tz_local)
        meta = {
            "uid":            uid,
            "calendar_color": color,
            "all_day":        True,
        }
        return [(st, en, comp.get("SUMMARY", "Untitled"), meta)]

    # ─────────── 2) One‑off, no RRULE ───────────
    rrule_str = comp.get("RRULE")
    if not rrule_str:
        local_start = start.astimezone(tz_local)
        if local_start.date() == target_date:
            st = local_start
            en = end.astimezone(tz_local)
            meta = {
                "uid":            uid,
                "calendar_color": color,
                "all_day":        False,
            }
            instances.append((st, en, comp.get("SUMMARY", "Untitled"), meta))
        return instances

    # ─────────── 3) Recurring via RRULE ───────────
    rule = rrulestr(rrule_str.to_ical().decode(), dtstart=start)
    day_start = datetime.combine(target_date, time.min).replace(tzinfo=start.tzinfo)
    day_end   = datetime.combine(target_date, time.max).replace(tzinfo=start.tzinfo)
    exdates = set()
    ex_prop = comp.get('EXDATE')
    if ex_prop is not None:
        # normalize to a list of properties
        ex_props = ex_prop if isinstance(ex_prop, list) else [ex_prop]
        for prop in ex_props:
            # each prop has .dts (the list of date‑times)
            for exdt in getattr(prop, "dts", []):
                dt = exdt.dt
                # ensure tz‑aware
                if isinstance(dt, datetime) and dt.tzinfo is None:
                    dt = tz_local.localize(dt)
                exdates.add(dt)
    for occ in rule.between(day_start, day_end, inc=True):
        if occ in overrides:
            print(
                f"🔄 Skipping master occurrence for "
                f"{str(comp.get('SUMMARY','Untitled'))!r} "
                f"on {occ.isoformat()}, override exists"
            )
            continue
        if occ in exdates:
            print(
                f"🔄 Skipping occurrence for "
                f"{str(comp.get('SUMMARY','Untitled'))!r} "
                f"on {occ.isoformat()}, excluded for this day"
            )
            continue
        st_utc = occ
        en_utc = occ + (end - start)
        st = st_utc.astimezone(tz_local)
        en = en_utc.astimezone(tz_local)
        meta = {
            "uid":            uid,
            "calendar_color": color,
            "all_day":        False,
        }
        instances.append((st, en, comp.get("SUMMARY", "Untitled"), meta))

    return instances

def render_cover(
        merger,
        temp_files, 
        cover_src_pdf: str,
        page_w_pt: float,
        page_h_pt: float,
        cover_pdf_path: str = "/tmp/cover.pdf"
    ):
        """
        Embed cover_src_pdf (an existing single-page PDF) as a fully-vector Form XObject,
        scaled to COVER_WIDTH_FRAC of page width and vertically offset by COVER_VERT_FRAC,
        then append to the merger.
        """
        # Configuration fractions
        target_w_frac = float(os.getenv("COVER_WIDTH_FRAC", 0.75))
        v_frac        = float(os.getenv("COVER_VERT_FRAC",   0.25))

        # 1) Compute target width in points
        target_w_pt = page_w_pt * target_w_frac

        # 2) Read & wrap first page of provided PDF as XObject
        reader     = PdfReader(cover_src_pdf)
        page_xobj  = pagexobj(reader.pages[0])

        # 3) Create a new canvas for the cover page
        c = canvas.Canvas(cover_pdf_path, pagesize=(page_w_pt, page_h_pt))
        form = makerl(c._doc, page_xobj)

        # 4) Compute original PDF dims in points
        orig_w_pt = page_xobj.BBox[2] - page_xobj.BBox[0]
        orig_h_pt = page_xobj.BBox[3] - page_xobj.BBox[1]
        # scale to target width
        scale     = target_w_pt / orig_w_pt
        scaled_h  = orig_h_pt * scale

        # 5) Position for centering + offset
        x = (page_w_pt - target_w_pt) / 2.0
        y = (page_h_pt - scaled_h) * (1 - v_frac)

        # 6) Draw the XObject
        c.saveState()
        c.translate(x, y)
        c.scale(scale, scale)
        c.doForm(form)
        c.restoreState()

        # 7) Finish and append
        c.showPage()
        c.save()
        merger.append(cover_pdf_path)
        temp_files.append(cover_pdf_path)

def render_schedule_pdf(timed_events, output_path, date_label, all_day_events=None):
    width, height = get_page_size()
    c = canvas.Canvas(output_path, pagesize=(width, height))

    # Get Layout
    layout = get_layout_config(width, height, START_HOUR, END_HOUR)
    page_left  = layout["page_left"]
    page_right = layout["page_right"]
    heading_size = layout["heading_size"]
    page_top = layout["page_top"]
    element_pad = layout["element_pad"]
    heading_ascent = layout["heading_ascent"]
    mini_text_pad = layout["mini_text_pad"]
    mini_block_gap = layout["mini_block_gap"]
    text_padding = layout["text_padding"]
    grid_left = layout["grid_left"]
    grid_right = layout["grid_right"]
    grid_top = layout["grid_top"]
    page_bottom = layout["page_bottom"]
    hour_height = layout["hour_height"]

    # Pull in feature flags
    minical_mode = os.getenv("DRAW_MINICALS", "full").strip().lower()
    DRAW_MINICALS = minical_mode not in ("false", "0", "no")
    MINICAL_ONLY_CURRENT = (minical_mode == "current")
    DRAW_ALL_DAY  = os.getenv("DRAW_ALL_DAY",  "true").lower() in ("1","true","yes")
    ALLDAY_FROM   = os.getenv("ALLDAY_FROM",   "grid").lower()
    MINICAL_ALIGN = os.getenv("MINICAL_ALIGN", "right").lower()

    # Recompute grid_top so it floats up when we skip the minis or all‑day band
    # Start from the page_top

    # Force right alignment of mini-cals if we're drawing the all-day band
    if DRAW_ALL_DAY:
        MINICAL_ALIGN = "right"

    # Header/title
    c.setFillGray(0)
    title_y = page_top - heading_ascent # Pin ascenders to page_top
    c.setFont("Montserrat-Bold", heading_size)
    c.drawCentredString(width/2, title_y, date_label.strftime('%A, %B %d, %Y'))

    # Line under title
    sep_y = title_y - element_pad
    c.setStrokeGray(0.4)
    c.setLineWidth(1)
    c.line(page_left, sep_y, page_right, sep_y)

    # Mini Calendar Definitions
    mini_w       = 80
    mini_h       = float(os.getenv("MINICAL_HEIGHT", 60))
    gap          = mini_block_gap
    total_w = mini_w + (0 if MINICAL_ONLY_CURRENT else mini_w + gap)

    if MINICAL_ALIGN == "left":
        x_start = page_left
    elif MINICAL_ALIGN == "grid":
        x_start = grid_left
    elif MINICAL_ALIGN == "center":
        x_start = page_left + ((page_right - page_left) - total_w) / 2
    else:  # right
        left_offset = float(os.getenv("MINICAL_OFFSET", 0))
        x_start     = page_right - total_w - left_offset
    y_cal = sep_y - element_pad - mini_h - (2 * mini_text_pad)

    # All Day Events
    band_left = page_left if ALLDAY_FROM == "margin" else grid_left
    if DRAW_MINICALS:
        band_right  = x_start - mini_block_gap
    else:
        band_right = page_right
    band_width  = band_right - band_left
    band_bottom = y_cal + element_pad
    band_top    = y_cal + mini_h + 2*mini_text_pad
    band_height = band_top - band_bottom

    # Label
    label_lines = ["All-Day", "Events"]
    all_day_label_font_size = (band_height * 0.33) / (len(label_lines) * 1.2)
    x_label = band_left + text_padding

    if DRAW_ALL_DAY:
        # Draw label string
        c.setStrokeGray(0.2)
        draw_centered_multiline(
            c,
            label_lines,
            "Montserrat-SemiBold",
            all_day_label_font_size,
            x_label,
            band_bottom,
            band_height,
            line_spacing=1.2
        )

        # Compute label‐column width
        c.setFont("Montserrat-SemiBold", all_day_label_font_size)
        label_w = max(c.stringWidth(line, "Montserrat-SemiBold", all_day_label_font_size)
                        for line in label_lines)
        label_area = label_w + 2*text_padding

        n              = len(all_day_events)
        slots_per_col  = 4
        slot_h         = band_height / slots_per_col
        cols           = 1 if n <= slots_per_col else 2
        capacity       = slots_per_col * cols
        to_draw        = all_day_events[:capacity]
        events_left    = band_left + label_area
        events_width   = band_right - events_left
        slot_w         = events_width / cols
        pad            = 2
        bar_w          = 2

        get_title_font_and_offset, _ = init_text_helpers(hour_height)

        # Draw vertical separator
        sep_x = events_left
        # c.setStrokeGray(0.4)
        c.setStrokeColor(black)
        c.setLineWidth(0.5)
        c.line(sep_x, band_bottom, sep_x, band_top)

        # Draw box
        c.setStrokeColor(black)
        c.setLineWidth(0.5)
        c.roundRect(band_left, band_bottom, band_width, band_height, 4, stroke=1, fill=0)

        # Draw the actual all day events, if they exist
        if all_day_events:

            for idx, (_, _, title, meta) in enumerate(to_draw):
                col = idx // slots_per_col
                row = idx %  slots_per_col

                x = events_left + col * slot_w + (2* pad)
                y = band_top  - (row+1)*slot_h    + pad
                w = slot_w   - pad*3
                h = slot_h   - pad*2

                c.setFillColor(HexColor(meta.get("calendar_color", "#DDDDDD")))
                c.roundRect(x, y, w, h, 4, stroke=0, fill=1)
                c.setFillColor(css_color_to_hex(EVENT_FILL))
                c.setStrokeColor(css_color_to_hex(EVENT_STROKE))
                c.setLineWidth(0.33)
                c.roundRect(x + bar_w, y, w - bar_w, h, 4, stroke=1, fill=1)

                pseudo_min = (h / hour_height) * 60
                fs, baseline = get_title_font_and_offset(pseudo_min)
                c.setFont("Montserrat-Regular", fs)

                inner_w = (w - bar_w) - 4
                txt     = title
                while c.stringWidth(txt + "...", "Montserrat-Regular", fs) > inner_w:
                    txt = txt[:-1]
                if txt != title:
                    txt = txt.rstrip() + "..."

                text_y = y + h - baseline
                c.setFillGray(0)
                c.drawString(x + bar_w + 2, text_y, txt)


    if DRAW_MINICALS:
        today = date_label
        first_of_month = today.replace(day=1)
        if first_of_month.month == 12:
            next_month = first_of_month.replace(year=first_of_month.year+1, month=1)
        else:
            next_month = first_of_month.replace(month=first_of_month.month+1)

        cal = calendar.Calendar(firstweekday=6)
        weeks1 = cal.monthdayscalendar(first_of_month.year, first_of_month.month)
        weeks2 = cal.monthdayscalendar(next_month.year, next_month.month)

        draw_mini_cal(c, first_of_month.year, first_of_month.month,
                    weeks1, x_start, y_cal, mini_w, mini_h,
                    highlight_day=today.day)
        if not MINICAL_ONLY_CURRENT:
            draw_mini_cal(c, next_month.year, next_month.month,
                    weeks2, x_start + mini_w + gap, y_cal, mini_w, mini_h)

    # Main Grid
    render_time_grid(c, date_label, layout)

    # Events
    get_title_font_and_offset, get_time_font_and_offset = \
    init_text_helpers(hour_height)
    events = assign_stacks(timed_events)
    events = sorted(events,
                    key=lambda e: (e["layer_index"], e["start"]))
    # total_width = (1 * width) - grid_left - grid_right
    total_width = grid_right - grid_left
    print(f"📏 total_width available: {total_width:.2f} points")
    for event in events:
        start = event["start"]
        end = event["end"]
        title = event["title"]
        meta = event["meta"]
        width_frac = event["width_frac"]

        grid_start_dt = datetime.combine(date_label, time(START_HOUR, 0)).replace(tzinfo=tz_local)
        grid_end_dt   = datetime.combine(date_label, time(END_HOUR,   0)).replace(tzinfo=tz_local)

        # Handle off-grid starts
        draw_start = max(start, grid_start_dt)
        draw_end   = min(end,   grid_end_dt)

        # if nothing is on‐grid, skip (or promote to all‐day)
        if draw_start >= draw_end:
            continue

        start_eff = draw_start
        end_eff   = draw_end

        y_start = time_to_y(start_eff, layout)
        y_end   = time_to_y(end_eff,   layout)
        y_start_raw = time_to_y(start, layout)
        y_end_raw   = time_to_y(end,   layout)

        box_height = y_start - y_end

        box_width = total_width * width_frac

        box_x = grid_right - box_width  # right-align

        breached_top    = (y_start_raw > layout["grid_top"])
        breached_bottom = (y_end_raw   < layout["grid_bottom"])

        # clamp to grid bounds
        clamped_y_start = min(y_start, layout["grid_top"])
        clamped_y_end   = max(y_end,   layout["grid_bottom"])
        clamped_h       = clamped_y_start - clamped_y_end

        # print(f"📦 Event: '{title}' | box_x: {box_x:.2f} | box_width: {box_width:.2f} | box_height: {box_height:.2f}")

        hex_color = meta.get("calendar_color", "#DDDDDD")
        radius = 3 if box_height < 6 else 4
        color_bar_width = 2

        c.setStrokeColor(css_color_to_hex(EVENT_STROKE))
        c.setLineWidth(.33)
        c.setFillColor(HexColor(hex_color))
        draw_rect_with_optional_round(c, box_x, clamped_y_end, box_width, clamped_h, radius, round_top = not breached_top,round_bottom= not breached_bottom,stroke=0,fill=1)


        c.setFillColor(css_color_to_hex(EVENT_FILL))
        draw_rect_with_optional_round(c, box_x+ color_bar_width, clamped_y_end, box_width - color_bar_width, clamped_h, radius, round_top = not breached_top,round_bottom= not breached_bottom,stroke=1,fill=1)

        # if start.hour < START_HOUR or start.hour >= END_HOUR:
        #     continue
        c.setFillGray(0)
        duration_minutes = (end_eff - start_eff).total_seconds() / 60

        font_size, y_offset = get_title_font_and_offset(duration_minutes)
        c.setFont("Montserrat-Regular", font_size)
        # Prepare labels (moved above ellipsizing)
        time_label = f"{fmt_time(start)} - {fmt_time(end)}"
        title_font_size, title_y_offset = get_title_font_and_offset((end_eff - start_eff).total_seconds()/60)
        time_font_size,  time_y_offset  = get_time_font_and_offset((end_eff - start_eff).total_seconds()/60)

        # Decide hide/move flags for time before ellipsizing
        has_direct_above = False
        above_event = None
        for other in events:
            if (other["layer_index"] == event["layer_index"] + 1
                and start_eff < other["end"] and other["start"] < end_eff
                and abs((other["start"] - start_eff).total_seconds()) <= 30*60):
                has_direct_above = True
                above_event = other
                break
        raw_title_w = c.stringWidth(title, "Montserrat-Regular", title_font_size)
        inline_space = (
            box_width
            - 4
            - 2 * text_padding
            - c.stringWidth(time_label, "Montserrat-Regular", time_font_size)
        )
        should_move_for_title = duration_minutes >= 60 and raw_title_w > inline_space
        hide_time = has_direct_above and duration_minutes < 60
        move_time = (has_direct_above and duration_minutes >= 60) or should_move_for_title

        # Ellipsize title:
        #   reserve space for the time if inline; but always avoid occlusion by a
        #   next-layer box whose start is within 30 min
        title_x_start = box_x + 4 + text_padding
        time_reserve  = 0 if (hide_time or move_time) else \
                        c.stringWidth(time_label, "Montserrat-Regular", time_font_size)
        max_w_time    = box_width - 4 - 2 * text_padding - time_reserve

        # compute occlusion constraint regardless of hide/move
        max_w_occ = max_w_time
        for other in events:
            if (other["layer_index"] == event["layer_index"] + 1
                and start_eff < other["end"] and other["start"] < end_eff
                and (other["start"] - start_eff).total_seconds() < 30*60):
                other_w  = total_width * other["width_frac"]
                other_x  = grid_right - other_w
                avail    = other_x - title_x_start - 2
                max_w_occ = min(max_w_occ, avail)
                break

        final_max_w = max(0, min(max_w_time, max_w_occ))
        display_title = title
        if c.stringWidth(display_title, "Montserrat-Regular", title_font_size) > final_max_w:
            # truncate
            while (
                display_title
                and c.stringWidth(display_title + "...", "Montserrat-Regular", title_font_size)
                    > final_max_w
            ):
                display_title = display_title[:-1]
            display_title = display_title.rstrip() + "..."

        # Draw title
        y_text = y_start - title_y_offset
        c.drawString(box_x + 2 + text_padding, y_text, display_title)
        font_size, y_offset = get_time_font_and_offset(duration_minutes)
        c.setFont("Montserrat-Regular", font_size)
        y_text = y_start - y_offset
        time_label = f"{fmt_time(start)} - {fmt_time(end)}"
        # 1) Find a “directly above” event in the very next layer
        has_direct_above = False
        above_event = None
        for other in events:
            if other["layer_index"] == event["layer_index"] + 1:
                if start_eff < other["end"] and other["start"] < end_eff:
                    delta = (other["start"] - start_eff).total_seconds()
                    if delta < 30 * 60:
                        has_direct_above = True
                        above_event = other
                        break
        # detect if title is too wide for inline (and event ≥ 60 min)
        raw_title_w = c.stringWidth(title, "Montserrat-Regular", title_font_size)
        inline_space = (
            box_width
            - 4
            - 2 * text_padding
            - c.stringWidth(time_label, "Montserrat-Regular", time_font_size)
        )
        should_move_for_title = (
            duration_minutes >= 60
            and raw_title_w > inline_space
        )
        # 2) Print & draw
        hide_time = has_direct_above and duration_minutes < 60
        move_time = (has_direct_above and duration_minutes >= 60) or should_move_for_title

        c.setFont("Montserrat-Regular", time_font_size)

        # Handle edge case where moving the time would force it off the grid
        if move_time:
            # compute the would-be y_time for the moved label
            y_title = y_start - title_y_offset
            y_time  = y_title - (text_padding / 2) - time_y_offset
            # if that y_time falls below grid_bottom, don’t move it
            if y_time < layout["grid_bottom"]:
                move_time = False
                hide_time = True
        if hide_time:
            print(
                f"ℹ️ HIDING time for '{title}' ({int(duration_minutes)} min) "
                f"because above '{above_event['title']}' @ {above_event['start'].strftime('%H:%M')}"
            )
            # no time drawn
        elif move_time:
            print(
                f"ℹ️ MOVING time for '{title}' ({int(duration_minutes)} min) "
                f"due to {'title too long' if should_move_for_title else 'above-event'}"
            )
            y_title = y_start - title_y_offset
            y_time  = y_title - (text_padding / 2) - time_y_offset
            x_time  = box_x + 2 + text_padding
            c.drawString(x_time, y_time, time_label)
        else:
            print(
                f"ℹ️ DRAWING inline time for '{title}' ({int(duration_minutes)} min); no close-above event"
            )
            y_time = y_start - y_offset
            c.drawRightString(box_x + box_width - text_padding, y_time, time_label)

    now = datetime.now(tz_local)
    footer = os.getenv("FOOTER", "E P H E M E R I S")
    if footer == "updated":
        footer_text  = now.strftime("Updated: %Y-%m-%d %H:%M %Z")
    else:
        footer_text = footer
    if footer != "disabled":
        c.setFont("Montserrat-Light", 6)
        c.setFillColor(css_color_to_hex(FOOTER_COLOR))
        c.drawCentredString(width/2, page_bottom, footer_text)

    # # RENDER MARGINS FOR TESTING
    # c.setStrokeGray(0.4)
    # c.setLineWidth(0.5)
    # c.line(page_right, page_top, page_right, page_bottom)
    # c.line(page_left, page_top, page_left, page_bottom)
    # c.line(page_right, page_top, page_left, page_top)
    # c.line(page_right, page_bottom, page_left, page_bottom)

    c.save()
    # if FORMAT == "png":
    #     from pdf2image import convert_from_path
    #     dpi = int(os.getenv("PDF_DPI", 226))
    #     pages = convert_from_path(OUTPUT_PDF, dpi=dpi)

    #     png_path = OUTPUT_PDF.replace(".pdf", ".png")
    #     pages[0].save(png_path, "PNG")
    #     print(f"📷 Wrote PNG → {png_path}")
    # else:
    #     print(f"📄 Wrote PDF → {OUTPUT_PDF}")
if __name__ == "__main__":
    timezone_str = os.getenv("TIMEZONE","UTC")
    tz_local     = tz.gettz(timezone_str)
    OUTPUT_PDF = os.getenv("OUTPUT_PDF","output/ephemeris.pdf")
    # Allow a date‐range via DATE_RANGE, or fall back to TARGET_DATE/single‐day
    dr = os.getenv("DATE_RANGE")  # e.g. "this week", "2025-04-01:2025-04-07"
    if dr:
        date_list = parse_date_range(dr, tz_local)
    else:
        _dt = os.getenv("TARGET_DATE")
        single = _dt or datetime.now(tz_local).strftime("%Y-%m-%d")
        date_list = [datetime.strptime(single, "%Y-%m-%d").date()]

    merger = PdfMerger()
    temp_files = []
    config     = load_config()
    meta       = load_meta()
    raw_events = load_raw_events(config)

    # Prepare anchor for this run
    anchor = f"{date_list[0].isoformat()}:{date_list[-1].isoformat()}"

    # Compute events hash
    new_hash    = compute_events_hash(raw_events)
    last_anchor = meta.get("_last_anchor")
    prev_hash   = meta.get("events_hash")

    # Decide whether to skip
    if not FORCE_REFRESH and last_anchor == anchor and prev_hash == new_hash:
        print(f"🚫 No changes in events, date range ({anchor}) unchanged → skipping generation.")
        sys.exit(0)

    if FORCE_REFRESH:
        print("🔄 FORCE_REFRESH set → forcing full refresh of PDF")
    elif last_anchor != anchor:
        print(f"🔄 Date-range changed: {last_anchor} → {anchor} → regenerating PDF")
    else:
        print(f"✅ Event changes detected (hash {prev_hash} → {new_hash[:8]}..) → regenerating PDF")

    override_map = defaultdict(set)
    for comp, color, tzf, name in raw_events:
        rid_prop = comp.get('RECURRENCE-ID')
        if rid_prop:
            # decode the override’s original start
            rid_dt = comp.decoded('RECURRENCE-ID')
            uid    = comp.get('UID')
            override_map[uid].add(rid_dt)

    counts = Counter(cal_name for _, _, _, cal_name in raw_events)
    print("📦 VEVENT count by calendar:")
    for cal_name, cnt in counts.items():
        print(f"   • {cal_name!r}: {cnt} events")

    if COVER_PAGE:
        page_w, page_h = get_page_size()
        svg = os.getenv("COVER_SVG_PATH", "assets/cover.pdf")
        render_cover(merger, temp_files, svg, page_w, page_h)

    for d in date_list:
        # 1) Build unique_instances for date d:
        unique_instances = []
        seen = set()
        for comp, color, tzf, name in raw_events:
            for start, end, title, meta in expand_event_for_day(comp, color, tzf, d, tz_local):
                # key = (meta.get("uid"), start.isoformat(), title)
                key = (meta.get("uid"))
                if key in seen:
                    print(
                        f"⚠️  Skipping duplicate: "
                        f"UID={meta.get('uid')!r}, start={start.isoformat()}, title={title!r}"
                    )
                    continue
                seen.add(key)
                unique_instances.append((start, end, title, meta))
        # 2) Split & filter:
        all_day_events, rem = split_all_day_events(unique_instances, d, tz_local)
        timed = filter_events_for_day(rem, d)
        # 3) Render to a temp PDF:
        tmp = f"/tmp/schedule_{d.isoformat()}.pdf"
        render_schedule_pdf(timed, tmp, d, all_day_events)
        merger.append(tmp)
        temp_files.append(tmp)

    # 4) Write out the merged multi-page PDF:
    out = os.getenv("OUTPUT_PDF", "output/ephemeris.pdf")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "wb") as f:
        merger.write(f)
    print(f"📄 Wrote multi-day PDF → {out}")

    # Persist metadata
    new_meta = {"_last_anchor": anchor, "events_hash": new_hash}
    save_meta(new_meta)
    print(f"✅ Completed generation for range {anchor}")

    # 5) Clean up
    for t in temp_files:
        os.remove(t)
