import calendar
from datetime import datetime
from collections import defaultdict

from reportlab.lib.pagesizes import letter

import ephemeris.settings as settings

def get_layout_config(width, height, start_hour=6, end_hour=17):
    # Raw page margins from environment
    page_left   = settings.PDF_MARGIN_LEFT
    page_right  = width - settings.PDF_MARGIN_RIGHT
    page_top    = height - settings.PDF_MARGIN_TOP
    page_bottom = settings.PDF_MARGIN_BOTTOM

    # Fixed dimensions
    time_label_width = 26  # width reserved for the HH:MM column
    heading_size   = 12
    heading_ascent = heading_size * 0.75
    element_pad      = 8
    text_padding     = 5

    # Mini-calendar block dimensions
    mini_block_h   = settings.MINICAL_HEIGHT
    mini_block_gap = settings.MINICAL_GAP
    mini_text_pad = settings.MINICAL_TEXT_PADDING

    # Buffer below time grid
    bottom_buffer = settings.PDF_GRID_BOTTOM_BUFFER

    # Feature Flags Affecting Grid
    minical_mode = settings.DRAW_MINICALS
    DRAW_MINICALS = minical_mode not in ("false", "0", "no")

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

    if settings.DRAW_ALL_DAY:
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

def pixels_to_points(pixels, dpi):
    return pixels * 72 / dpi

def time_to_y(dt: datetime, layout: dict[str, float]) -> float:
    """
    Convert a datetime to a vertical position inside the grid.
    """
    elapsed = (dt.hour + dt.minute / 60) - layout["start_hour"]
    return layout["grid_top"] - elapsed * layout["hour_height"]

def get_page_size():
    env_size = settings.PDF_PAGE_SIZE
    env_dpi = settings.PDF_DPI
    try:
        px_width, px_height = map(int, env_size.lower().split("x"))
        width_pt = pixels_to_points(px_width, dpi=env_dpi)
        height_pt = pixels_to_points(px_height, dpi=env_dpi)
        return width_pt, height_pt
    except Exception as e:
        print(f"⚠️ Invalid PDF_PAGE_SIZE or PDF_DPI: {e}. Using fallback letter size.")
        return letter
