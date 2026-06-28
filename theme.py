# -*- coding: utf-8 -*-
"""
Visual theme configurations for the Hardware Spec Scanner.
Contains premium dark-mode colors, font choices, and UI constants.
Font sizes auto-scale based on system DPI for consistent rendering
across displays with different scaling factors (100%, 125%, 150%, etc.).
"""

import ctypes

# ==============================================================================
# DPI-Aware Font Scaling
# ==============================================================================

def _get_system_dpi_scale():
    """
    Detects the system DPI scale factor.
    Returns a float: 1.0 for 96 DPI (100%), 1.25 for 120 DPI (125%), etc.
    Falls back to 1.0 if detection fails.
    """
    try:
        # Try Per-Monitor DPI V2 first (Windows 10 1703+)
        awareness = ctypes.c_int()
        ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
        # Get the DPI for the primary monitor
        hdc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(hdc, 88)  # LOGPIXELSX = 88
        ctypes.windll.user32.ReleaseDC(0, hdc)
        if dpi > 0:
            return dpi / 96.0
    except Exception:
        pass

    try:
        # Fallback: use SystemParametersInfo or a simple GetDpiForSystem (Win10 1607+)
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi > 0:
            return dpi / 96.0
    except Exception:
        pass

    return 1.0


def _scaled_font_size(base_size):
    """
    Returns a DPI-scaled font size as an integer.
    Tkinter/CTk font sizes are in points; on high-DPI screens with
    Per-Monitor DPI awareness, we need to compensate because
    CustomTkinter's internal scaling handles widget sizing but
    NOT raw tkinter Canvas text or certain label font sizes.
    """
    # CustomTkinter handles its own widget scaling via widget_scaling,
    # so for CTk widgets we keep the base size. But we still need to ensure
    # the base size itself is reasonable for the display resolution.
    # On very high-res screens (>= 150% scale), bump font sizes slightly
    # to ensure readability.
    scale = DPI_SCALE
    if scale >= 1.75:
        # 175%+ scaling: fonts need a slight boost for readability
        adjusted = int(base_size * 1.15)
    elif scale >= 1.5:
        # 150% scaling: minor boost
        adjusted = int(base_size * 1.08)
    else:
        adjusted = base_size
    return max(adjusted, base_size)  # Never go smaller than base


# Compute once at import time
DPI_SCALE = _get_system_dpi_scale()

# ==============================================================================
# Color Palette (AihuiShou / LuDaShi inspired modern dark neon theme)
# ==============================================================================
BG_MAIN = "#0F0F12"         # Deep space dark background
BG_SIDEBAR = "#15151B"      # Sleek side panel background
BG_CARD = "#1D1D26"         # Premium card container background
BG_CARD_HOVER = "#262632"   # Hover state for card containers

# Accents & Gradients
COLOR_ACCENT = "#00D2FF"    # Radiant Cyan
COLOR_SECONDARY = "#0078FF" # Electric Blue
COLOR_SUCCESS = "#2ECC71"   # Emerald Green (normal status)
COLOR_WARNING = "#F1C40F"   # Sun Flower Yellow (warning status)
COLOR_DANGER = "#E74C3C"    # Alizarin Red (critical status)

# Text Colors
TEXT_PRIMARY = "#FFFFFF"    # Primary white text
TEXT_SECONDARY = "#8E8E9F"  # Secondary muted grey text
TEXT_ACCENT = "#00D2FF"     # Cyan text for highlighting

# ==============================================================================
# Fonts (DPI-Adaptive)
# ==============================================================================
# Font family priority: "Microsoft YaHei UI" provides excellent CJK rendering
# with ClearType antialiasing on Windows. Falls back to "Segoe UI" for Latin.
_FONT_FAMILY = "Microsoft YaHei UI"
_FONT_MONO_FAMILY = "Consolas"

FONT_TITLE = (_FONT_FAMILY, _scaled_font_size(20), "bold")
FONT_SUBTITLE = (_FONT_FAMILY, _scaled_font_size(14), "bold")
FONT_BODY = (_FONT_FAMILY, _scaled_font_size(11))
FONT_BODY_BOLD = (_FONT_FAMILY, _scaled_font_size(11), "bold")
FONT_CAPTION = (_FONT_FAMILY, _scaled_font_size(9))
FONT_MONO = (_FONT_MONO_FAMILY, _scaled_font_size(10))

# Inline font helpers for Canvas text and special widgets
FONT_GAUGE_VALUE = (_FONT_FAMILY, _scaled_font_size(20), "bold")
FONT_LOGO = (_FONT_FAMILY, _scaled_font_size(24), "bold")

# Card Styling Constants
CORNER_RADIUS = 12
BORDER_WIDTH = 1
BORDER_COLOR = "#2D2D3D"
