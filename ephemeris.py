import sys
import os
from datetime import datetime
from collections import Counter, defaultdict

from PyPDF2 import PdfMerger
from loguru import logger

import ephemeris.settings as settings
from ephemeris.fonts import init_fonts
from ephemeris.config import load_config
from ephemeris.meta import load_meta, save_meta
from ephemeris.calendar_loader import load_raw_events
from ephemeris.event_processing import (
    expand_event_for_day,
    split_all_day_events,
    filter_events_for_day,
    compute_events_hash,
)
from ephemeris.layout import get_page_size
from ephemeris.utils import parse_date_range
from ephemeris.renderers import render_cover, render_schedule_pdf, export_pdf_to_png
from ephemeris.logger import configure_logging


def main():
    # 0) Set up logs
    configure_logging()
    # 1) Initialize fonts once
    init_fonts()

    # 2) Determine local timezone
    tz_local = settings.TZ_LOCAL
    logger.debug("Timezone: {}", settings.TIMEZONE)

    # 3) Build list of dates to render
    dr = settings.DATE_RANGE

    date_list = parse_date_range(dr, tz_local)

    # 4) Prepare PDF merger and temp files
    merger = PdfMerger()
    temp_files = []

    # 5) Load config, metadata, and events
    config = load_config()
    meta   = load_meta()
    raw_events = load_raw_events(config["calendars"])

    # 6) Compute anchor & hash for change detection
    anchor    = f"{date_list[0].isoformat()}:{date_list[-1].isoformat()}"
    new_hash  = compute_events_hash(raw_events)
    last_anchor = meta.get("_last_anchor")
    prev_hash   = meta.get("events_hash")

    if not settings.FORCE_REFRESH and last_anchor == anchor and prev_hash == new_hash:
        logger.info("No changes for {}, skipping generation.", anchor)
        sys.exit(0)

    if settings.FORCE_REFRESH:
        logger.info("FORCE_REFRESH set, refreshing...")
    elif last_anchor != anchor:
        logger.info("Date-range changed: {} → {}, refreshing...", last_anchor, anchor)
    else:
        logger.info("Events changed, refreshing...")

    # 7) Build override map
    from ephemeris.event_processing import build_override_map
    override_map = build_override_map(raw_events)

    counts = Counter(cal_name for _, _, _, cal_name in raw_events)
    logger.debug("Event count by celender:")
    for cal_name, cnt in counts.items():
        logger.debug("   • {}: {} events", cal_name, cnt)

    # 8) Optionally render cover
    if settings.COVER_PAGE:
        logger.debug("Rendering cover page")
        w, h = get_page_size()
        cover_src = settings.DEFAULT_COVER
        render_cover(merger, temp_files, cover_src, w, h)

    # 9) Per-day expansion & rendering
    for d in date_list:
        logger.info("Processing {}",d)
        # expand & dedupe
        instances = []
        seen = set()
        for comp, color, tzf, name in raw_events:
            for st, en, title, meta_info in expand_event_for_day(comp, color, tzf, d, tz_local, override_map):
                uid = meta_info.get("uid")
                if uid in seen:
                    logger.opt(Colors=True).debug("<yellow>Skipping duplicate: {}, {}. (UID: {})", title, start.isoformat(), uid)
                    continue
                seen.add(uid)
                instances.append((st, en, title, meta_info))

        # split and filter
        all_day, rest = split_all_day_events(instances, d, tz_local)
        timed = filter_events_for_day(rest, d)

        # render schedule
        tmp = f"/tmp/schedule_{d.isoformat()}.pdf"
        render_schedule_pdf(timed, tmp, d, all_day_events=all_day, tz_local=settings.TZ_LOCAL)
        logger.debug("Rendered {}",d)
        merger.append(tmp)
        temp_files.append(tmp)

    # 10) Write merged PDF
    out_path = settings.OUTPUT_PDF
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        merger.write(f)
    logger.info("Wrote PDF to {}", out_path)
    
    if settings.FORMAT in ('png', 'both'):
        png_dir = export_pdf_to_png(
            pdf_path=out_path,
            date_list=date_list,
            cover=settings.COVER_PAGE,
            output_dir=settings.OUTPUT_PNG,
            dpi=settings.PDF_DPI,
        )
        logger.info("Exported PNGs to {}", png_dir)

        # If the user only wants PNGs, remove the PDF:
        if settings.FORMAT == 'png':
            os.remove(out_path)
            logger.info("Removed merged PDF at {}", out_path)

    # 11) Persist metadata
    save_meta({"_last_anchor": anchor, "events_hash": new_hash})
    logger.info("✅ Completed generation for {}", anchor)

    # 12) Clean up
    for fpath in temp_files:
        os.remove(fpath)

if __name__ == '__main__':
    main()
