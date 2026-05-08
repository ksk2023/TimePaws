"""
WinVibeTime Design System v3 — macOS Sonoma / Ventura inspired
==============================================================

Supports runtime dark ↔ light theme switching via ``set_theme()``.

Visual hierarchy:

    Layer 0  Window / titlebar bg    BG_PRIMARY
    Layer 1  Sidebar / nav           BG_SECONDARY
    Layer 2  Content card            BG_ELEVATED
    Layer 3  Hover / interactive     BG_HOVER
    Layer 4  Active / pressed        BG_ACTIVE

Typography scale (Segoe UI Variable / SF Pro / Inter):

    JUMBO       36  Bold     Hero numbers
    DISPLAY     24  Bold     Page title ("WinVibeTime")
    TITLE       18  Semibold Section title
    HEADLINE    15  Medium   Card title / KPI label
    BODY        13  Regular  Primary body text
    CAPTION     11  Regular  Secondary / helper text
    MICRO       10  Regular  Timestamps, footnotes

Spacing rhythm (4 px grid):

    XXS  4   XS  8   SM  12   MD  16   LG  24   XL  32   XXL  48

Corner radii:

    SM  8   MD  12   LG  16   FULL  9999

Accent blue is reserved for: active nav indicator, primary CTA,
selected calendar day ring, chart highlight bar.
"""

from __future__ import annotations


# ═══════════════════════════════════════════════════════════════════════════
#  Theme palettes
# ═══════════════════════════════════════════════════════════════════════════

_DARK = {
    # Backgrounds
    "BG_PRIMARY":        "#1C1C1E",
    "BG_SECONDARY":      "#2C2C2E",
    "BG_ELEVATED":       "#2C2C2E",
    "BG_HOVER":          "#3A3A3C",
    "BG_ACTIVE":         "#48484A",
    "BG_INPUT":          "#1C1C1E",
    # Text
    "TEXT_PRIMARY":       "#F5F5F7",
    "TEXT_SECONDARY":     "#A1A1A6",
    "TEXT_TERTIARY":      "#636366",
    "TEXT_INVERSE":       "#1C1C1E",
    # Accent
    "ACCENT":            "#0A84FF",
    "ACCENT_HOVER":      "#409CFF",
    "ACCENT_MUTED_HEX":  "#1A2E44",
    # Separators
    "SEPARATOR":         "#38383A",
    "SEPARATOR_LIGHT":   "#2C2C2E",
    # Semantic
    "DANGER":            "#FF453A",
    "SUCCESS":           "#30D158",
    "WARNING":           "#FFD60A",
    # Calendar
    "CAL_TODAY_RING":    "#0A84FF",
    "CAL_SELECTED_BG":   "#0A84FF",
    "CAL_OTHER_MONTH":   "#48484A",
    # Glass morphism
    "GLASS_BG":          "#2E2E33",
    "GLASS_BORDER":      "#48484D",
    # Segmented control
    "SEGMENTED_BG":      "#2C2C2E",
    "SEGMENTED_ACTIVE_BG": "#48484A",
    # Titlebar
    "TITLEBAR_BG":       "#1C1C1E",
}

_LIGHT = {
    # Backgrounds
    "BG_PRIMARY":        "#F2F2F7",
    "BG_SECONDARY":      "#FFFFFF",
    "BG_ELEVATED":       "#FFFFFF",
    "BG_HOVER":          "#E5E5EA",
    "BG_ACTIVE":         "#D1D1D6",
    "BG_INPUT":          "#FFFFFF",
    # Text
    "TEXT_PRIMARY":       "#1C1C1E",
    "TEXT_SECONDARY":     "#8E8E93",
    "TEXT_TERTIARY":      "#AEAEB2",
    "TEXT_INVERSE":       "#FFFFFF",
    # Accent
    "ACCENT":            "#007AFF",
    "ACCENT_HOVER":      "#0A84FF",
    "ACCENT_MUTED_HEX":  "#D6EAFF",
    # Separators
    "SEPARATOR":         "#D1D1D6",
    "SEPARATOR_LIGHT":   "#E5E5EA",
    # Semantic
    "DANGER":            "#FF3B30",
    "SUCCESS":           "#34C759",
    "WARNING":           "#FFCC00",
    # Calendar
    "CAL_TODAY_RING":    "#007AFF",
    "CAL_SELECTED_BG":   "#007AFF",
    "CAL_OTHER_MONTH":   "#D1D1D6",
    # Glass morphism
    "GLASS_BG":          "#F0F0F5",
    "GLASS_BORDER":      "#D1D1D6",
    # Segmented control
    "SEGMENTED_BG":      "#E5E5EA",
    "SEGMENTED_ACTIVE_BG": "#FFFFFF",
    # Titlebar
    "TITLEBAR_BG":       "#F2F2F7",
}


# ═══════════════════════════════════════════════════════════════════════════
#  Theme state + switching
# ═══════════════════════════════════════════════════════════════════════════

_current_theme: str = "dark"


def set_theme(theme: str) -> None:
    """Switch **all** module-level colour constants to *dark* or *light*.

    Components that import ``design_tokens as T`` and read ``T.BG_PRIMARY``
    etc. will automatically see the new values on next access.  Canvas-based
    widgets still need an explicit redraw after calling this function.
    """
    global _current_theme
    _current_theme = theme
    palette = _DARK if theme == "dark" else _LIGHT
    g = globals()
    for key, value in palette.items():
        g[key] = value


def current_theme() -> str:
    """Return ``'dark'`` or ``'light'``."""
    return _current_theme


def is_dark() -> bool:
    return _current_theme == "dark"


# ═══════════════════════════════════════════════════════════════════════════
#  Module-level colour constants — initialised from *dark* palette
# ═══════════════════════════════════════════════════════════════════════════

# Backgrounds
BG_PRIMARY       = _DARK["BG_PRIMARY"]
BG_SECONDARY     = _DARK["BG_SECONDARY"]
BG_ELEVATED      = _DARK["BG_ELEVATED"]
BG_HOVER         = _DARK["BG_HOVER"]
BG_ACTIVE        = _DARK["BG_ACTIVE"]
BG_INPUT         = _DARK["BG_INPUT"]

# Text
TEXT_PRIMARY      = _DARK["TEXT_PRIMARY"]
TEXT_SECONDARY    = _DARK["TEXT_SECONDARY"]
TEXT_TERTIARY     = _DARK["TEXT_TERTIARY"]
TEXT_INVERSE      = _DARK["TEXT_INVERSE"]

# Accent
ACCENT            = _DARK["ACCENT"]
ACCENT_HOVER      = _DARK["ACCENT_HOVER"]
ACCENT_MUTED      = "rgba(10,132,255,0.15)"   # CSS ref only
ACCENT_MUTED_HEX  = _DARK["ACCENT_MUTED_HEX"]

# Separators
SEPARATOR         = _DARK["SEPARATOR"]
SEPARATOR_LIGHT   = _DARK["SEPARATOR_LIGHT"]

# Semantic
DANGER            = _DARK["DANGER"]
SUCCESS           = _DARK["SUCCESS"]
WARNING           = _DARK["WARNING"]

# Calendar
CAL_TODAY_RING    = _DARK["CAL_TODAY_RING"]
CAL_SELECTED_BG   = _DARK["CAL_SELECTED_BG"]
CAL_OTHER_MONTH   = _DARK["CAL_OTHER_MONTH"]

# Chart palette (theme-agnostic — vivid on both backgrounds)
CHART_COLORS = [
    "#0A84FF",  # Blue (dominant app)
    "#5E5CE6",  # Indigo
    "#30D158",  # Green
    "#FF9F0A",  # Orange
    "#FF453A",  # Red
    "#BF5AF2",  # Purple
    "#64D2FF",  # Teal
    "#FF375F",  # Pink
]

# Glass morphism
GLASS_BG          = _DARK["GLASS_BG"]
GLASS_BORDER      = _DARK["GLASS_BORDER"]

# Segmented control
SEGMENTED_HEIGHT      = 36
SEGMENTED_BG          = _DARK["SEGMENTED_BG"]
SEGMENTED_ACTIVE_BG   = _DARK["SEGMENTED_ACTIVE_BG"]

# Titlebar
TITLEBAR_BG       = _DARK["TITLEBAR_BG"]


# ═══════════════════════════════════════════════════════════════════════════
#  Typography
# ═══════════════════════════════════════════════════════════════════════════

FONT_FAMILIES = [
    "Segoe UI Variable",
    "Segoe UI",
    "SF Pro Display",
    "SF Pro Text",
    "Inter",
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Noto Sans CJK SC",
    "Helvetica Neue",
]

FONT_MONO_FAMILIES = [
    "Cascadia Code",
    "SF Mono",
    "JetBrains Mono",
    "Consolas",
    "Menlo",
    "Ubuntu Mono",
    "DejaVu Sans Mono",
]

# Font sizes
SIZE_JUMBO     = 38
SIZE_DISPLAY   = 26
SIZE_TITLE     = 19
SIZE_HEADLINE  = 16
SIZE_BODY      = 14
SIZE_CAPTION   = 13
SIZE_MICRO     = 11

# Font weights
WEIGHT_BOLD    = "bold"
WEIGHT_NORMAL  = "normal"


# ═══════════════════════════════════════════════════════════════════════════
#  Spacing (4 px grid)
# ═══════════════════════════════════════════════════════════════════════════

SP_XXS  = 4
SP_XS   = 8
SP_SM   = 12
SP_MD   = 16
SP_LG   = 24
SP_XL   = 32
SP_XXL  = 48


# ═══════════════════════════════════════════════════════════════════════════
#  Corner Radius
# ═══════════════════════════════════════════════════════════════════════════

RADIUS_SM   = 8
RADIUS_MD   = 12
RADIUS_LG   = 16
RADIUS_FULL = 9999


# ═══════════════════════════════════════════════════════════════════════════
#  Shadows (CSS-like specs — CTk simulates via layering)
# ═══════════════════════════════════════════════════════════════════════════

SHADOW_CARD  = {"offset_y": 2, "blur": 8,  "color": "#00000033"}
SHADOW_MODAL = {"offset_y": 8, "blur": 32, "color": "#00000066"}


# ═══════════════════════════════════════════════════════════════════════════
#  App Color / Emoji Map (process name → soft colour / emoji)
# ═══════════════════════════════════════════════════════════════════════════

APP_COLOR_MAP: dict[str, str] = {
    "chrome":           "#4285F4",
    "msedge":           "#3B9AE1",
    "firefox":          "#FF7139",
    "safari":           "#006CFF",
    "code":             "#007ACC",
    "devenv":           "#8661C5",
    "idea64":           "#FC801D",
    "pycharm64":        "#21D789",
    "sublime_text":     "#FF9800",
    "explorer":         "#FFB900",
    "cmd":              "#4D4D4D",
    "powershell":       "#012456",
    "windowsterminal":  "#4D4D4D",
    "slack":            "#611F69",
    "discord":          "#5865F2",
    "teams":            "#6264A7",
    "telegram":         "#0088CC",
    "wechat":           "#07C160",
    "spotify":          "#1DB954",
    "notion":           "#787774",
    "obsidian":         "#7C3AED",
    "figma":            "#A259FF",
    "photoshop":        "#31A8FF",
    "word":             "#2B579A",
    "excel":            "#217346",
    "powerpoint":       "#B7472A",
    "outlook":          "#0078D4",
    "onenote":          "#7719AA",
}

APP_EMOJI_MAP: dict[str, str] = {
    "chrome":           "\U0001f310",   # 🌐
    "msedge":           "\U0001f30a",   # 🌊
    "firefox":          "\U0001f98a",   # 🦊
    "safari":           "\U0001f9ed",   # 🧭
    "code":             "\U0001f4bb",   # 💻
    "devenv":           "\U0001f52e",   # 🔮
    "explorer":         "\U0001f4c1",   # 📁
    "cmd":              "\u2b1b",       # ⬛
    "powershell":       "\U0001f537",   # 🔷
    "windowsterminal":  "\u2b1b",       # ⬛
    "slack":            "\U0001f4ac",   # 💬
    "discord":          "\U0001f3ae",   # 🎮
    "teams":            "\U0001f465",   # 👥
    "telegram":         "\u2708\ufe0f", # ✈️
    "wechat":           "\U0001f49a",   # 💚
    "spotify":          "\U0001f3b5",   # 🎵
    "notion":           "\U0001f4dd",   # 📝
    "figma":            "\U0001f3a8",   # 🎨
    "word":             "\U0001f4c4",   # 📄
    "excel":            "\U0001f4ca",   # 📊
    "powerpoint":       "\U0001f4fd\ufe0f",  # 📽️
}


# ═══════════════════════════════════════════════════════════════════════════
#  Animation timing (milliseconds)
# ═══════════════════════════════════════════════════════════════════════════

ANIM_HOVER_MS    = 150       # Hover colour transition
ANIM_PRESS_MS    = 80        # Press feedback
ANIM_FADE_MS     = 200       # Opacity-like fade
ANIM_SLIDE_MS    = 250       # Slide expand / collapse

# Micro-interaction parameters
MICRO_HOVER_STEPS  = 5       # Steps for colour transition
MICRO_HOVER_INTERVAL = 30    # ms per step  (~150 ms total)
MICRO_PRESS_DARKEN = 0.12    # Darken factor on press


# ═══════════════════════════════════════════════════════════════════════════
#  Titlebar (macOS-style)
# ═══════════════════════════════════════════════════════════════════════════

TITLEBAR_HEIGHT   = 52
TRAFFIC_RED       = "#FF5F57"
TRAFFIC_YELLOW    = "#FEBC2E"
TRAFFIC_GREEN     = "#28C840"
TRAFFIC_DOT_SIZE  = 12       # px diameter
TRAFFIC_DOT_GAP   = 8        # px between dots


# ═══════════════════════════════════════════════════════════════════════════
#  Layout
# ═══════════════════════════════════════════════════════════════════════════

WINDOW_DEFAULT_SIZE = "1100x780"
WINDOW_MIN_SIZE     = (800, 600)
TREE_ROW_HEIGHT     = 44
CHART_BAR_HEIGHT    = 28
CHART_BAR_GAP       = 8
CHART_BAR_RADIUS    = 6
CALENDAR_CELL_SIZE  = 64
