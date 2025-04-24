from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from loguru import logger

from ephemeris.settings import FONTS_DIR

def init_fonts(fonts_dir: Path | None = None) -> None:
    """
    Register all custom fonts with ReportLab by passing in real file paths.
    Tries the configured FONTS_DIR and falls back to the package-local fonts folder.
    """
    # Candidate directories
    candidates = []
    if fonts_dir:
        candidates.append(Path(fonts_dir))
    candidates.append(Path(FONTS_DIR))  # primary
    candidates.append(Path(__file__).resolve().parent / "fonts")  # fallback

    fonts = [
        ("Montserrat-ExtraLight", "Montserrat-ExtraLight.ttf"),
        ("Montserrat-Regular",    "Montserrat-Regular.ttf"),
        ("Montserrat-Bold",       "Montserrat-Bold.ttf"),
        ("Montserrat-SemiBold",   "Montserrat-SemiBold.ttf"),
        ("Montserrat-Light",      "Montserrat-Light.ttf"),
    ]

    for name, fname in fonts:
        for base in candidates:
            font_path = (base / fname).resolve()
            if font_path.is_file():
                logger.debug("Loading font {} from {}",name, str(font_path))
                pdfmetrics.registerFont(TTFont(name, str(font_path)))
                break
        else:
            msg = (
                f"Font '{fname}' not found in: "
                f"{', '.join(str(p) for p in candidates)}"
            )
            logger.error("{}", msg)
            raise FileNotFoundError(msg)
