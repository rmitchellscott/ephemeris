import calendar

def get_layout_config(...):
    """Compute grid & mini-cal layout metrics."""
    pass

def get_page_size():
    env_size = os.getenv("PDF_PAGE_SIZE", "1872x1404")  # Default to reMarkable 2
    env_dpi = float(os.getenv("PDF_DPI", "226"))        # Default to reMarkable 2 DPI
    try:
        px_width, px_height = map(int, env_size.lower().split("x"))
        width_pt = pixels_to_points(px_width, dpi=env_dpi)
        height_pt = pixels_to_points(px_height, dpi=env_dpi)
        return width_pt, height_pt
    except Exception as e:
        print(f"⚠️ Invalid PDF_PAGE_SIZE or PDF_DPI: {e}. Using fallback letter size.")
        return letter
