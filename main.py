#!/usr/bin/env python3
import sys
import os

from dateutil import tz
from datetime import datetime
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyPDF2 import PdfMerger
from collections import defaultdict, Counter


from ephemeris.config import load_config, load_meta, save_meta
from ephemeris.loaders import load_raw_events, load_meta
from ephemeris.utils import parse_date_range
from ephemeris.event_processing import (
    expand_event_for_day,
    split_all_day_events,
    filter_events_for_day,
    compute_events_hash,
)
from ephemeris.renderers import render_cover, render_schedule_pdf
from ephemeris.layout import get_layout_config, get_page_size


def main():
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

if __name__ == '__main__':
    main()
