"""
Reusable UI components — Apple-grade quality.

All widgets are built on customtkinter with hand-tuned styling.
"""

from __future__ import annotations

import calendar
import math
import tkinter as tk
from datetime import date, datetime, timedelta
from typing import Callable

import customtkinter as ctk

from . import design_tokens as T


# ─── Helpers ────────────────────────────────────────────────────────────────

_FONT_CACHE: str = ""
_MONO_FONT_CACHE: str = ""


def _resolve_fonts() -> None:
    """Detect regular + mono font families using the running Tk interpreter."""
    global _FONT_CACHE, _MONO_FONT_CACHE
    try:
        # tk.font.families() with no argument uses the already-running Tk
        # interpreter — no need to spawn and destroy a hidden root window.
        available = set(tk.font.families())
        for name in T.FONT_FAMILIES:
            if name in available:
                _FONT_CACHE = name
                break
        for name in T.FONT_MONO_FAMILIES:
            if name in available:
                _MONO_FONT_CACHE = name
                break
    except Exception:
        pass
    if not _FONT_CACHE:
        _FONT_CACHE = "TkDefaultFont"
    if not _MONO_FONT_CACHE:
        _MONO_FONT_CACHE = "TkFixedFont"


def font(size: int = T.SIZE_BODY, weight: str = T.WEIGHT_NORMAL) -> tuple:
    if not _FONT_CACHE:
        _resolve_fonts()
    return (_FONT_CACHE, size, weight)


def mono_font(size: int = T.SIZE_BODY, weight: str = T.WEIGHT_NORMAL) -> tuple:
    """Monospace / tabular-number font (Cascadia Code, SF Mono, Consolas …)."""
    if not _MONO_FONT_CACHE:
        _resolve_fonts()
    return (_MONO_FONT_CACHE, size, weight)


def compact_duration(total_seconds: float) -> str:
    seconds = max(0, int(round(float(total_seconds))))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def format_hours(total_seconds: float) -> str:
    hours = total_seconds / 3600.0
    if hours >= 1:
        return f"{hours:.1f}h"
    minutes = total_seconds / 60.0
    if minutes >= 1:
        return f"{minutes:.0f}m"
    return f"{int(total_seconds)}s"


# ─── Micro-interaction helpers ─────────────────────────────────────────────

def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linearly interpolate between two hex colours."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = min(255, max(0, int(r1 + (r2 - r1) * t)))
    g = min(255, max(0, int(g1 + (g2 - g1) * t)))
    b = min(255, max(0, int(b1 + (b2 - b1) * t)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken(hex_color: str, factor: float = 0.12) -> str:
    """Darken a hex colour by *factor* (0–1)."""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    r = max(0, int(r * (1 - factor)))
    g = max(0, int(g * (1 - factor)))
    b = max(0, int(b * (1 - factor)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _animate_fg(
    widget: ctk.CTkBaseClass,
    from_color: str,
    to_color: str,
    attr: str = "fg_color",
    steps: int = T.MICRO_HOVER_STEPS,
    interval: int = T.MICRO_HOVER_INTERVAL,
) -> None:
    """Smooth colour transition on a CTk widget via ``configure()``.

    Cancels any in-flight animation for the same (widget, attr) pair before
    starting a new one — prevents callback pile-up when the mouse moves fast.
    """
    cancel_key = f"_anim_ids_{attr}"
    # Cancel previous pending steps
    for after_id in getattr(widget, cancel_key, []):
        try:
            widget.after_cancel(after_id)
        except Exception:
            pass
    ids: list = []
    for i in range(1, steps + 1):
        t = i / steps
        color = _lerp_color(from_color, to_color, t)
        ids.append(
            widget.after(i * interval, lambda c=color: widget.configure(**{attr: c}))
        )
    setattr(widget, cancel_key, ids)


# ─── Capsule Button ────────────────────────────────────────────────────────

class CapsuleButton(ctk.CTkButton):
    """Pill-shaped button with accent border on hover and press darkening."""

    def __init__(self, parent: ctk.CTkBaseClass, **kwargs):
        kwargs.setdefault("corner_radius", T.RADIUS_FULL)
        kwargs.setdefault("fg_color", T.BG_HOVER)
        kwargs.setdefault("hover_color", T.BG_ACTIVE)
        kwargs.setdefault("text_color", T.TEXT_PRIMARY)
        kwargs.setdefault("font", font(T.SIZE_CAPTION))
        kwargs.setdefault("height", 32)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", T.SEPARATOR)
        self._rest_border = kwargs["border_color"]
        self._rest_fg = kwargs["fg_color"]
        super().__init__(parent, **kwargs)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_enter(self, _event: object) -> None:
        _animate_fg(self, self._rest_border, T.ACCENT, attr="border_color")

    def _on_leave(self, _event: object) -> None:
        self.configure(border_color=self._rest_border)

    def _on_press(self, _event: object) -> None:
        self.configure(fg_color=_darken(self._rest_fg, T.MICRO_PRESS_DARKEN))

    def _on_release(self, _event: object) -> None:
        self.configure(fg_color=self._rest_fg)


# ─── Segmented Pill (Apple-style Segmented Control) ───────────────────────

class SegmentedPill(ctk.CTkFrame):
    """Rounded track with pill-shaped active indicator — mimics macOS segmented control."""

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        items: list[tuple[str, str]],
        on_select: Callable[[str], None],
        **kwargs,
    ):
        kwargs.setdefault("corner_radius", T.RADIUS_SM)
        kwargs.setdefault("fg_color", T.SEGMENTED_BG)
        super().__init__(parent, **kwargs)

        self._on_select = on_select
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._active_id: str = ""

        pad = 3
        for item_id, label in items:
            btn = ctk.CTkButton(
                self,
                text=label,
                corner_radius=T.RADIUS_SM - 2,
                fg_color="transparent",
                hover_color=T.BG_HOVER,
                text_color=T.TEXT_SECONDARY,
                font=font(T.SIZE_BODY),
                height=T.SEGMENTED_HEIGHT - pad * 2,
                width=80,
                command=lambda _id=item_id: self._handle_click(_id),
            )
            btn.pack(side="left", padx=pad, pady=pad)
            self._buttons[item_id] = btn

    def _handle_click(self, item_id: str) -> None:
        self.set_active(item_id)
        self._on_select(item_id)

    def set_active(self, item_id: str) -> None:
        if self._active_id == item_id:
            return
        if self._active_id in self._buttons:
            self._buttons[self._active_id].configure(
                fg_color="transparent",
                text_color=T.TEXT_SECONDARY,
            )
        self._active_id = item_id
        if item_id in self._buttons:
            self._buttons[item_id].configure(
                fg_color=T.SEGMENTED_ACTIVE_BG,
                text_color=T.TEXT_PRIMARY,
            )


# ─── Glass Total Card (glassmorphism hero) ────────────────────────────────

class GlassTotalCard(ctk.CTkFrame):
    """Frosted-glass hero card displaying total active duration prominently.

    Micro-interactions: border brightens on hover (subtle glow).
    """

    def __init__(self, parent: ctk.CTkBaseClass, **kwargs):
        kwargs.setdefault("corner_radius", T.RADIUS_LG)
        kwargs.setdefault("fg_color", T.GLASS_BG)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", T.GLASS_BORDER)
        self._rest_border = kwargs["border_color"]
        super().__init__(parent, **kwargs)

        # Large duration
        self._value_label = ctk.CTkLabel(
            self, text="\u2014",
            font=font(T.SIZE_JUMBO, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY,
            anchor="w",
        )
        self._value_label.pack(fill="x", padx=T.SP_LG, pady=(T.SP_LG, T.SP_XXS))

        # Subtitle
        ctk.CTkLabel(
            self, text="\u603b\u6d3b\u8dc3\u65f6\u957f",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY,
            anchor="w",
        ).pack(fill="x", padx=T.SP_LG, pady=(0, T.SP_SM))

        # Meta line (app count · top app)
        self._meta_label = ctk.CTkLabel(
            self, text="",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_TERTIARY,
            anchor="w",
        )
        self._meta_label.pack(fill="x", padx=T.SP_LG, pady=(0, T.SP_LG))

        # Hover glow
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event: object) -> None:
        _animate_fg(self, self._rest_border, T.ACCENT_HOVER, attr="border_color")

    def _on_leave(self, _event: object) -> None:
        self.configure(border_color=self._rest_border)

    def set_data(self, total_seconds: float, app_count: int, top_app: str) -> None:
        sig = (round(total_seconds), app_count, top_app)
        if sig == getattr(self, "_data_sig", None):
            return
        self._data_sig = sig
        self._value_label.configure(text=compact_duration(total_seconds))
        parts: list[str] = []
        if app_count > 0:
            parts.append(f"{app_count} \u4e2a\u5e94\u7528")
        if top_app and top_app != "\u2014":
            parts.append(f"\u6700\u5e38\u7528  {top_app}")
        self._meta_label.configure(text="  \u00b7  ".join(parts))


# ─── Apple-Style Bar Chart ────────────────────────────────────────────────

class AppleStyleBarChart(ctk.CTkFrame):
    """Canvas-rendered horizontal bar chart with emoji icons, gradient bars,
    hover tooltips, and monospace duration labels.

    Colour / icon for each app is resolved via ``T.APP_COLOR_MAP`` /
    ``T.APP_EMOJI_MAP`` (matched on lowercase process name minus .exe).
    Unknown apps fall back to ``T.CHART_COLORS`` and a neutral ``\u25aa`` dot.
    """

    _ROW_H = 38
    _BAR_H = 20

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        title: str = "",
        **kwargs,
    ):
        super().__init__(
            parent,
            corner_radius=T.RADIUS_MD,
            fg_color=T.BG_ELEVATED,
            **kwargs,
        )

        if title:
            ctk.CTkLabel(
                self, text=title,
                font=font(T.SIZE_HEADLINE, T.WEIGHT_BOLD),
                text_color=T.TEXT_PRIMARY, anchor="w",
            ).pack(fill="x", padx=T.SP_LG, pady=(T.SP_MD, T.SP_XS))

        self._canvas = tk.Canvas(
            self, bg=T.BG_ELEVATED, highlightthickness=0, bd=0,
            cursor="hand2",
        )
        self._canvas.pack(
            fill="both", expand=True,
            padx=T.SP_LG, pady=(T.SP_XS, T.SP_MD),
        )

        self._data: list[tuple[str, float]] = []
        self._hovered_row: int = -1

        self._paint_after_id: str | None = None
        self._canvas.bind("<Configure>", self._on_configure)
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)

    # ── public ─────────────────────────────────────────────────────────

    def _on_configure(self, _event: object) -> None:
        """Debounce resize events — repaint at most once per 40 ms."""
        if self._paint_after_id is not None:
            try:
                self.after_cancel(self._paint_after_id)
            except Exception:
                pass
        self._paint_after_id = self.after(40, self._paint)

    def set_data(self, data: list[tuple[str, float]]) -> None:
        sig = tuple((n, round(v)) for n, v in data[:8])
        if sig == getattr(self, "_data_sig", None):
            return
        self._data_sig = sig
        self._data = data[:8]
        self._hovered_row = -1
        self._paint()

    def refresh_theme(self) -> None:
        """Re-apply current theme colours and redraw."""
        self._canvas.configure(bg=T.BG_ELEVATED)
        self.configure(fg_color=T.BG_ELEVATED)
        self._paint()

    # ── colour / icon helpers ──────────────────────────────────────────

    @staticmethod
    def _app_key(name: str) -> str:
        return name.lower().replace(".exe", "")

    @classmethod
    def _get_color(cls, name: str, index: int) -> str:
        key = cls._app_key(name)
        return T.APP_COLOR_MAP.get(key, T.CHART_COLORS[index % len(T.CHART_COLORS)])

    @classmethod
    def _get_emoji(cls, name: str) -> str:
        return T.APP_EMOJI_MAP.get(cls._app_key(name), "\u25aa")

    @staticmethod
    def _lighten(hex_color: str, factor: float = 0.18) -> str:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    # ── rendering ──────────────────────────────────────────────────────

    def _paint(self) -> None:
        c = self._canvas
        c.delete("all")

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return

        if not self._data:
            c.create_text(
                w // 2, h // 2,
                text="\u6682\u65e0\u6570\u636e",
                fill=T.TEXT_TERTIARY, font=font(T.SIZE_BODY),
            )
            return

        max_val = max(v for _, v in self._data) or 1.0

        # layout columns
        emoji_x = 16
        name_x = 36
        name_w = 120
        bar_left = name_x + name_w + T.SP_SM
        dur_w = 64
        bar_right = w - dur_w - T.SP_SM
        bar_w_max = max(bar_right - bar_left, 20)
        bar_r = self._BAR_H / 2

        total_h = len(self._data) * self._ROW_H
        y_start = max(0, (h - total_h) // 2)

        for i, (label, value) in enumerate(self._data):
            y_top = y_start + i * self._ROW_H
            yc = y_top + self._ROW_H / 2

            # hover row highlight
            if i == self._hovered_row:
                self._round_rect(
                    c, 4, y_top + 2, w - 4, y_top + self._ROW_H - 2,
                    T.RADIUS_SM, fill=T.BG_HOVER, outline="",
                )

            # emoji
            c.create_text(
                emoji_x, yc, text=self._get_emoji(label),
                font=font(T.SIZE_BODY), anchor="w",
            )

            # app name
            disp = label if len(label) <= 14 else label[:12] + "\u2026"
            c.create_text(
                name_x, yc, text=disp,
                fill=T.TEXT_SECONDARY, font=font(T.SIZE_CAPTION), anchor="w",
            )

            # bar track
            by1 = yc - self._BAR_H / 2
            by2 = yc + self._BAR_H / 2
            self._round_rect(
                c, bar_left, by1, bar_right, by2,
                bar_r, fill=T.BG_HOVER, outline="",
            )

            # bar fill (base colour)
            fill_w = max(bar_r * 2, (value / max_val) * bar_w_max)
            color = self._get_color(label, i)
            bx2 = bar_left + fill_w
            self._round_rect(
                c, bar_left, by1, bx2, by2,
                bar_r, fill=color, outline="",
            )

            # gradient highlight — lighter top portion
            lighter = self._lighten(color, 0.22)
            hl_h = self._BAR_H * 0.42
            hl_r = min(bar_r, hl_h / 2)
            self._round_rect(
                c, bar_left, by1, bx2, by1 + hl_h,
                hl_r, fill=lighter, outline="",
            )

            # duration (monospace)
            c.create_text(
                w - T.SP_SM, yc, text=format_hours(value),
                fill=T.TEXT_SECONDARY, font=mono_font(T.SIZE_CAPTION),
                anchor="e",
            )

            # hover tooltip
            if i == self._hovered_row and value > 0:
                secs = int(value)
                hrs, rem = divmod(secs, 3600)
                mins, s = divmod(rem, 60)
                detail = (
                    f"{hrs}\u5c0f\u65f6 {mins}\u5206\u949f {s}\u79d2"
                    if hrs else f"{mins}\u5206\u949f {s}\u79d2"
                )
                tid = c.create_text(0, 0, text=detail, font=font(T.SIZE_MICRO))
                bb = c.bbox(tid)
                c.delete(tid)
                if bb:
                    tw = bb[2] - bb[0] + T.SP_MD
                    th = bb[3] - bb[1] + T.SP_XS
                    tx = bar_left + fill_w / 2
                    ty = by1 - th / 2 - 4
                    tx = max(tw / 2 + 4, min(tx, w - tw / 2 - 4))
                    if ty - th / 2 < 4:
                        ty = by2 + th / 2 + 4
                    self._round_rect(
                        c, tx - tw / 2, ty - th / 2, tx + tw / 2, ty + th / 2,
                        4, fill=T.BG_ACTIVE, outline=T.SEPARATOR,
                    )
                    c.create_text(
                        tx, ty, text=detail,
                        fill=T.TEXT_PRIMARY, font=font(T.SIZE_MICRO),
                    )

    # ── hit testing ────────────────────────────────────────────────────

    def _row_at(self, y: float) -> int:
        if not self._data:
            return -1
        h = self._canvas.winfo_height()
        total_h = len(self._data) * self._ROW_H
        y_start = max(0, (h - total_h) // 2)
        row = int((y - y_start) / self._ROW_H)
        return row if 0 <= row < len(self._data) else -1

    def _on_motion(self, event: tk.Event) -> None:
        row = self._row_at(event.y)
        if row != self._hovered_row:
            self._hovered_row = row
            self._paint()

    def _on_leave(self, _event: tk.Event) -> None:
        if self._hovered_row != -1:
            self._hovered_row = -1
            self._paint()

    # ── canvas helper ──────────────────────────────────────────────────

    @staticmethod
    def _round_rect(
        canvas: tk.Canvas,
        x1: float, y1: float, x2: float, y2: float,
        r: float, **kwargs,
    ) -> int:
        r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2,
            x1 + r, y2, x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1, x1 + r, y1,
        ]
        return canvas.create_polygon(pts, smooth=True, **kwargs)


# ─── Expandable App List (replaces AppDetailCard + AppDetailList) ─────────

_ANIM_STEPS = 6
_ANIM_MS    = 25   # ~150 ms total


class _AppCard(ctk.CTkFrame):
    """Single expandable app row with emoji icon, slide animation,
    and recessed sub-cards for window details."""

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        app_name: str,
        total_seconds: float,
        exe_path: str,
        color: str,
        emoji: str,
        windows: list[dict],
        **kwargs,
    ):
        super().__init__(
            parent,
            corner_radius=T.RADIUS_SM,
            fg_color=T.BG_ELEVATED,
            **kwargs,
        )

        self._expanded = False
        self._windows = windows
        self._animating = False

        # ── Header row ──
        header = ctk.CTkFrame(self, fg_color="transparent", cursor="hand2")
        header.pack(fill="x", padx=T.SP_MD, pady=(T.SP_SM, T.SP_XS))

        # Emoji icon
        emoji_label = ctk.CTkLabel(
            header, text=emoji or "▪",
            font=font(T.SIZE_TITLE),
            width=28,
        )
        emoji_label.pack(side="left", padx=(0, T.SP_SM))

        # App name
        name_label = ctk.CTkLabel(
            header, text=app_name,
            font=font(T.SIZE_BODY, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        )
        name_label.pack(side="left", fill="x", expand=True)

        # Duration (large mono)
        dur_label = ctk.CTkLabel(
            header, text=compact_duration(total_seconds),
            font=mono_font(T.SIZE_HEADLINE, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="e",
        )
        dur_label.pack(side="right", padx=(T.SP_SM, 0))

        # Chevron
        self._chevron = ctk.CTkLabel(
            header, text="›",
            font=font(T.SIZE_HEADLINE),
            text_color=T.TEXT_TERTIARY, width=20,
        )
        self._chevron.pack(side="right")

        # Exe path (grey micro)
        if exe_path:
            display_path = exe_path if len(exe_path) <= 70 else "…" + exe_path[-68:]
            ctk.CTkLabel(
                self, text=display_path,
                font=font(T.SIZE_MICRO),
                text_color=T.TEXT_TERTIARY, anchor="w",
            ).pack(fill="x", padx=(T.SP_MD + 28 + T.SP_SM, T.SP_MD), pady=(0, T.SP_XS))

        # Click bindings
        for widget in (header, emoji_label, name_label, dur_label, self._chevron):
            widget.bind("<Button-1>", lambda _e: self._toggle())

        # Hover micro-interaction (smooth bg transition)
        self.bind("<Enter>", self._on_card_enter)
        self.bind("<Leave>", self._on_card_leave)

        # ── Detail section (built once, animated in/out) ──
        self._detail_frame = ctk.CTkFrame(self, fg_color="transparent")

        if windows:
            # Thin separator
            ctk.CTkFrame(
                self._detail_frame, fg_color=T.SEPARATOR, height=1,
            ).pack(fill="x", padx=T.SP_MD, pady=(0, T.SP_XS))

            for win in windows:
                sub = ctk.CTkFrame(
                    self._detail_frame,
                    corner_radius=T.RADIUS_SM,
                    fg_color=T.BG_PRIMARY,
                    border_width=1,
                    border_color=T.SEPARATOR_LIGHT,
                )
                sub.pack(fill="x", padx=(T.SP_LG, T.SP_MD), pady=2)

                inner = ctk.CTkFrame(sub, fg_color="transparent")
                inner.pack(fill="x", padx=T.SP_SM, pady=T.SP_XXS)

                title = win.get("window_title", "(无标题)")
                if len(title) > 55:
                    title = title[:53] + "…"

                ctk.CTkLabel(
                    inner, text=title,
                    font=font(T.SIZE_CAPTION),
                    text_color=T.TEXT_SECONDARY, anchor="w",
                ).pack(side="left", fill="x", expand=True)

                win_seconds = float(win.get("total_seconds", 0))
                ctk.CTkLabel(
                    inner, text=compact_duration(win_seconds),
                    font=mono_font(T.SIZE_CAPTION),
                    text_color=T.TEXT_TERTIARY, anchor="e",
                ).pack(side="right", padx=(T.SP_XS, 0))

                hwnd_val = win.get("hwnd", 0)
                if hwnd_val:
                    ctk.CTkLabel(
                        inner, text=f"HWND {hwnd_val}",
                        font=mono_font(T.SIZE_MICRO),
                        text_color=T.TEXT_TERTIARY, anchor="e",
                    ).pack(side="right", padx=(T.SP_XS, 0))

    # ── Hover ──

    def _on_card_enter(self, _event: object) -> None:
        self.configure(fg_color=T.BG_HOVER)

    def _on_card_leave(self, _event: object) -> None:
        self.configure(fg_color=T.BG_ELEVATED)

    # ── Animation ──

    def _toggle(self) -> None:
        if not self._windows or self._animating:
            return
        if self._expanded:
            self._collapse()
        else:
            self._expand()

    def _expand(self) -> None:
        self._expanded = True
        self._animating = True
        self._chevron.configure(text="⌄")
        self._detail_frame.pack(fill="x", pady=(0, T.SP_XS))
        # Defer height measurement to next idle tick so the pack layout
        # completes before we read winfo_reqheight — avoids update_idletasks()
        # which would flush all pending events synchronously and stutter.
        self.after_idle(self._start_expand_anim)

    def _start_expand_anim(self) -> None:
        target_h = self._detail_frame.winfo_reqheight()
        self._detail_frame.pack_propagate(False)
        self._detail_frame.configure(height=0)
        self._anim_step(0, target_h, _ANIM_STEPS, expanding=True)

    def _collapse(self) -> None:
        self._expanded = False
        self._animating = True
        self._chevron.configure(text="›")

        current_h = self._detail_frame.winfo_height()
        self._detail_frame.pack_propagate(False)
        self._anim_step(0, current_h, _ANIM_STEPS, expanding=False)

    def _anim_step(self, step: int, total_h: int, steps: int, expanding: bool) -> None:
        if step > steps:
            if expanding:
                self._detail_frame.pack_propagate(True)
            else:
                self._detail_frame.pack_forget()
                self._detail_frame.pack_propagate(True)
            self._animating = False
            return

        t = step / steps
        if expanding:
            # ease-out: 1 - (1-t)²
            frac = 1.0 - (1.0 - t) ** 2
            h = int(total_h * frac)
        else:
            # ease-in: (1-t)²
            frac = (1.0 - t) ** 2
            h = int(total_h * frac)

        self._detail_frame.configure(height=max(h, 1))
        self.after(_ANIM_MS, self._anim_step, step + 1, total_h, steps, expanding)


class ExpandableAppList(ctk.CTkFrame):
    """Expandable app card list with search + sort toolbar.

    Drop-in replacement for the old AppDetailList — same ``set_data()`` API.
    """

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        title: str = "应用明细",
        **kwargs,
    ):
        super().__init__(
            parent,
            corner_radius=T.RADIUS_MD,
            fg_color=T.BG_ELEVATED,
            **kwargs,
        )

        self._title_text = title
        self._sort_desc = True        # True = longest first
        self._search_var = tk.StringVar()
        self._search_after_id: str | None = None
        self._software_rows: list = []
        self._grouped_windows: dict = {}

        # ── Toolbar ──
        toolbar = ctk.CTkFrame(self, fg_color="transparent")
        toolbar.pack(fill="x", padx=T.SP_MD, pady=(T.SP_SM, T.SP_XS))

        ctk.CTkLabel(
            toolbar, text=title,
            font=font(T.SIZE_HEADLINE, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        ).pack(side="left")

        # Sort toggle
        self._sort_btn = CapsuleButton(
            toolbar, text="时长 ↓", width=70,
            command=self._toggle_sort,
        )
        self._sort_btn.pack(side="right", padx=(T.SP_XS, 0))

        # Search box
        search_entry = ctk.CTkEntry(
            toolbar, width=180,
            placeholder_text="搜索应用…",
            textvariable=self._search_var,
            corner_radius=T.RADIUS_SM,
            fg_color=T.BG_INPUT,
            border_color=T.SEPARATOR,
            border_width=1,
            font=font(T.SIZE_CAPTION),
        )
        search_entry.pack(side="right", padx=(T.SP_XS, 0))
        self._search_var.trace_add("write", self._on_search_changed)

        # ── Scrollable area ──
        self._scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent", corner_radius=0,
        )
        self._scroll.pack(fill="both", expand=True, padx=T.SP_XXS, pady=(0, T.SP_XS))

    # ── Public API ──

    def set_data(
        self,
        software_rows: list,
        grouped_windows: dict,
    ) -> None:
        # Only rebuild widgets when the data actually changed.
        # Fingerprint: sorted (process_name, rounded_seconds) pairs.
        new_sig = tuple(
            (str(r["process_name"]), round(float(r["total_seconds"] or 0)))
            for r in sorted(software_rows, key=lambda r: str(r["process_name"]))
        )
        if new_sig == getattr(self, "_data_sig", None):
            return
        self._data_sig = new_sig
        self._software_rows = list(software_rows)
        self._grouped_windows = dict(grouped_windows)
        self._rebuild_cards()

    # ── Internal ──

    def _toggle_sort(self) -> None:
        self._sort_desc = not self._sort_desc
        self._sort_btn.configure(text="时长 ↓" if self._sort_desc else "时长 ↑")
        self._rebuild_cards()

    def _on_search_changed(self, *_args: object) -> None:
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
        self._search_after_id = self.after(300, self._rebuild_cards)

    def _rebuild_cards(self) -> None:
        self._search_after_id = None

        for child in self._scroll.winfo_children():
            child.destroy()

        query = self._search_var.get().strip().lower()
        rows = self._software_rows

        if query:
            filtered = []
            for row in rows:
                pname = str(row["process_name"]).lower()
                epath = str(row["exe_path"] or "").lower()
                app_key = (str(row["process_name"]), str(row["exe_path"] or ""))
                win_match = any(
                    query in str(w.get("window_title", "")).lower()
                    for w in self._grouped_windows.get(app_key, [])
                )
                if query in pname or query in epath or win_match:
                    filtered.append(row)
            rows = filtered

        rows = sorted(
            rows,
            key=lambda r: float(r["total_seconds"] or 0),
            reverse=self._sort_desc,
        )

        if not rows:
            ctk.CTkLabel(
                self._scroll,
                text="暂无应用数据" if not query else "无匹配结果",
                font=font(T.SIZE_BODY),
                text_color=T.TEXT_TERTIARY,
            ).pack(pady=T.SP_XL)
            return

        for row in rows:
            process_name = str(row["process_name"])
            exe_path = str(row["exe_path"] or "")
            total_seconds = float(row["total_seconds"] or 0)

            pname_lower = process_name.lower().replace(".exe", "")
            color = T.APP_COLOR_MAP.get(pname_lower, T.CHART_COLORS[0])
            emoji = T.APP_EMOJI_MAP.get(pname_lower, "")

            app_key = (process_name, exe_path)
            windows = []
            for w in self._grouped_windows.get(app_key, []):
                windows.append({
                    "window_title": str(w["window_title"] or "(无标题)"),
                    "hwnd": int(w["hwnd"]),
                    "total_seconds": float(w["total_seconds"] or 0),
                })

            card = _AppCard(
                self._scroll,
                app_name=process_name,
                total_seconds=total_seconds,
                exe_path=exe_path,
                color=color,
                emoji=emoji,
                windows=windows,
            )
            card.pack(fill="x", pady=(0, T.SP_XXS))


# ─── Apple-Style Calendar ──────────────────────────────────────────────────

class AppleStyleCalendar(ctk.CTkFrame):
    """Canvas-rendered month calendar with hover circles, usage bars,
    and a floating detail popup on click.

    Animations / visual states
    ──────────────────────────
    • **Normal day**      — number in TEXT_PRIMARY (current month) or
                            TEXT_TERTIARY (other months).  No background.
    • **Hover**           — rounded-rect fill in BG_HOVER drawn behind
                            the number.  Instant on enter, cleared on leave.
    • **Today**           — solid ACCENT circle behind the number,
                            white bold text.  Circle persists on hover.
    • **Selected ≠ today** — ACCENT_MUTED circle + thin ACCENT ring,
                            accent-coloured bold text.
    • **Usage bar**       — thin (3 px) rounded bar at the cell bottom,
                            width ∝ usage / month-max, colour = ACCENT.
    • **Popup appear**    — CTkToplevel placed at screen coords below
                            the clicked cell (or above if near bottom).
                            Dismiss via ✕ button or clicking another day.
    """

    WEEKDAY_LABELS = ["一", "二", "三", "四", "五", "六", "日"]
    _GRID_ROWS = 6
    _CELL_H = 54

    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        on_day_selected: Callable[[date], None],
        fetch_day_summary: Callable[[date], dict] | None = None,
        **kwargs,
    ):
        super().__init__(
            parent,
            corner_radius=T.RADIUS_MD,
            fg_color=T.BG_ELEVATED,
            **kwargs,
        )

        self._on_day_selected = on_day_selected
        self._fetch_day_summary = fetch_day_summary

        self._month_anchor = date.today().replace(day=1)
        self._selected_day = date.today()
        self._day_totals: dict[str, float] = {}

        self._hovered_idx: int = -1
        self._cells: list[date] = []
        self._popup: ctk.CTkToplevel | None = None
        self._popup_day: date | None = None

        # ── Navigation bar ─────────────────────────────────────────────
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=T.SP_MD, pady=(T.SP_MD, T.SP_SM))

        self._month_label = ctk.CTkLabel(
            nav, text="",
            font=font(T.SIZE_TITLE, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY,
        )
        self._month_label.pack(side="left")

        right_nav = ctk.CTkFrame(nav, fg_color="transparent")
        right_nav.pack(side="right")

        ctk.CTkButton(
            right_nav, text="\u2039", width=32, height=32,
            corner_radius=T.RADIUS_FULL,
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_SECONDARY,
            font=font(T.SIZE_TITLE, T.WEIGHT_BOLD),
            command=lambda: self._shift_month(-1),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            right_nav, text="\u203a", width=32, height=32,
            corner_radius=T.RADIUS_FULL,
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_SECONDARY,
            font=font(T.SIZE_TITLE, T.WEIGHT_BOLD),
            command=lambda: self._shift_month(1),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            right_nav, text="\u4eca\u5929", width=48, height=28,
            corner_radius=T.RADIUS_SM,
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.ACCENT,
            font=font(T.SIZE_CAPTION),
            command=self._jump_today,
        ).pack(side="left", padx=(T.SP_XS, 0))

        # ── Weekday header ─────────────────────────────────────────────
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=T.SP_SM, pady=(0, T.SP_XXS))
        for c in range(7):
            hdr.grid_columnconfigure(c, weight=1, uniform="cal")
        for c, lbl in enumerate(self.WEEKDAY_LABELS):
            ctk.CTkLabel(
                hdr, text=lbl,
                font=font(T.SIZE_MICRO),
                text_color=T.TEXT_TERTIARY,
                anchor="center",
            ).grid(row=0, column=c, sticky="ew")

        # ── Canvas grid ────────────────────────────────────────────────
        self._canvas = tk.Canvas(
            self, bg=T.BG_ELEVATED, highlightthickness=0, bd=0,
            height=self._CELL_H * self._GRID_ROWS,
            cursor="hand2",
        )
        self._canvas.pack(fill="both", expand=True,
                          padx=T.SP_SM, pady=(0, T.SP_MD))

        self._canvas.bind("<Configure>", lambda _e: self._render())
        self._canvas.bind("<Motion>", self._on_motion)
        self._canvas.bind("<Leave>", self._on_leave)
        self._canvas.bind("<Button-1>", self._on_click)

        # Clean up popup if calendar is destroyed
        self.bind("<Destroy>", self._on_destroy)

    # ── Public API ─────────────────────────────────────────────────────

    def update_data(
        self,
        month_anchor: date,
        selected_day: date,
        day_totals: dict[str, float],
    ) -> None:
        self._month_anchor = month_anchor
        self._selected_day = selected_day
        self._day_totals = day_totals
        self._dismiss_popup()
        self._render()

    def refresh_theme(self) -> None:
        """Re-apply current theme colours and redraw."""
        self._canvas.configure(bg=T.BG_ELEVATED)
        self.configure(fg_color=T.BG_ELEVATED)
        self._render()

    # ── Canvas rendering ───────────────────────────────────────────────

    def _render(self) -> None:
        c = self._canvas
        c.delete("all")

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 10:
            return

        self._month_label.configure(
            text=self._month_anchor.strftime("%Y\u5e74 %m\u6708"),
        )

        cell_w = w / 7
        cell_h = h / self._GRID_ROWS
        first_wd = self._month_anchor.weekday()
        grid_start = self._month_anchor - timedelta(days=first_wd)
        today = date.today()
        max_total = max(self._day_totals.values(), default=0) or 1.0

        self._cells = []
        for idx in range(self._GRID_ROWS * 7):
            row = idx // 7
            col = idx % 7
            day = grid_start + timedelta(days=idx)
            self._cells.append(day)

            x1 = col * cell_w
            y1 = row * cell_h
            cx = x1 + cell_w / 2
            cy = y1 + cell_h / 2 - 4

            is_today = day == today
            is_sel = day == self._selected_day
            is_month = day.month == self._month_anchor.month
            total = self._day_totals.get(day.isoformat(), 0.0)

            # ── hover highlight ──
            if idx == self._hovered_idx and not is_sel and not is_today:
                pad = 3
                self._round_rect(
                    c, x1 + pad, y1 + pad,
                    x1 + cell_w - pad, y1 + cell_h - pad,
                    T.RADIUS_SM, fill=T.BG_HOVER, outline="",
                )

            # ── circle (today / selected) ──
            r = min(cell_w, cell_h) * 0.32
            if is_today:
                c.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    fill=T.ACCENT, outline="",
                )
                txt_fill = "#FFFFFF"
                txt_wt = T.WEIGHT_BOLD
            elif is_sel:
                c.create_oval(
                    cx - r, cy - r, cx + r, cy + r,
                    fill=T.ACCENT_MUTED_HEX,
                    outline=T.ACCENT, width=1.5,
                )
                txt_fill = T.ACCENT
                txt_wt = T.WEIGHT_BOLD
            elif not is_month:
                txt_fill = T.TEXT_TERTIARY
                txt_wt = T.WEIGHT_NORMAL
            else:
                txt_fill = T.TEXT_PRIMARY
                txt_wt = T.WEIGHT_NORMAL

            # ── day number ──
            c.create_text(
                cx, cy, text=str(day.day),
                fill=txt_fill, font=font(T.SIZE_BODY, txt_wt),
            )

            # ── usage bar ──
            if total > 0 and is_month:
                bar_max = cell_w * 0.6
                bar_w = max(4, (total / max_total) * bar_max)
                bh = 3
                by = y1 + cell_h - 8
                bx = cx - bar_w / 2
                self._round_rect(
                    c, bx, by, bx + bar_w, by + bh,
                    bh / 2, fill=T.ACCENT, outline="",
                )

    @staticmethod
    def _round_rect(
        canvas: tk.Canvas,
        x1: float, y1: float, x2: float, y2: float,
        r: float, **kwargs,
    ) -> int:
        r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
        pts = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2,
            x1 + r, y2, x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1, x1 + r, y1,
        ]
        return canvas.create_polygon(pts, smooth=True, **kwargs)

    # ── Hit testing & mouse events ─────────────────────────────────────

    def _cell_at(self, x: float, y: float) -> int:
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        if w < 1 or h < 1:
            return -1
        col = int(x / (w / 7))
        row = int(y / (h / self._GRID_ROWS))
        if 0 <= col < 7 and 0 <= row < self._GRID_ROWS:
            return row * 7 + col
        return -1

    def _on_motion(self, event: tk.Event) -> None:
        idx = self._cell_at(event.x, event.y)
        if idx != self._hovered_idx:
            self._hovered_idx = idx
            self._render()

    def _on_leave(self, _event: tk.Event) -> None:
        if self._hovered_idx != -1:
            self._hovered_idx = -1
            self._render()

    def _on_click(self, event: tk.Event) -> None:
        idx = self._cell_at(event.x, event.y)
        if idx < 0 or idx >= len(self._cells):
            return

        clicked = self._cells[idx]

        # Toggle popup when re-clicking the same day
        if self._popup is not None and self._popup_day == clicked:
            self._dismiss_popup()
            return

        self._selected_day = clicked
        self._dismiss_popup()
        self._show_popup(idx, clicked)
        self._render()
        self._on_day_selected(clicked)

    # ── Floating detail popup ──────────────────────────────────────────

    def _show_popup(self, cell_idx: int, day: date) -> None:
        if not self._fetch_day_summary:
            return

        summary = self._fetch_day_summary(day)
        total: float = summary.get("total_seconds", 0)
        apps: list[tuple[str, float]] = summary.get("apps", [])
        if total <= 0:
            return

        # ── screen position ──
        w = self._canvas.winfo_width()
        h = self._canvas.winfo_height()
        cell_w = w / 7
        cell_h = h / self._GRID_ROWS
        col = cell_idx % 7
        row = cell_idx // 7

        root_x = self._canvas.winfo_rootx()
        root_y = self._canvas.winfo_rooty()
        anchor_x = root_x + int(col * cell_w + cell_w / 2)
        anchor_y = root_y + int((row + 1) * cell_h) + 4

        popup_w = 260
        screen_w = self.winfo_toplevel().winfo_screenwidth()
        screen_h = self.winfo_toplevel().winfo_screenheight()

        # ── build popup ──
        self._popup_day = day
        popup = ctk.CTkToplevel()
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        self._popup = popup

        card = ctk.CTkFrame(
            popup,
            corner_radius=T.RADIUS_MD,
            fg_color=T.BG_SECONDARY,
            border_width=1,
            border_color=T.SEPARATOR,
        )
        card.pack(fill="both", expand=True, padx=1, pady=1)

        # header — date + close button
        hdr = ctk.CTkFrame(card, fg_color="transparent")
        hdr.pack(fill="x", padx=T.SP_SM, pady=(T.SP_SM, 0))

        ctk.CTkLabel(
            hdr,
            text=day.strftime("%m\u6708%d\u65e5"),
            font=font(T.SIZE_BODY, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            hdr, text="\u2715", width=24, height=24,
            corner_radius=T.RADIUS_FULL,
            fg_color="transparent", hover_color=T.BG_HOVER,
            text_color=T.TEXT_TERTIARY,
            font=font(T.SIZE_CAPTION),
            command=self._dismiss_popup,
        ).pack(side="right")

        # total duration
        ctk.CTkLabel(
            card,
            text=f"\u603b\u65f6\u957f  {compact_duration(total)}",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=T.SP_MD, pady=(T.SP_XXS, T.SP_XS))

        # app list
        if apps:
            ctk.CTkFrame(
                card, height=1, fg_color=T.SEPARATOR, corner_radius=0,
            ).pack(fill="x", padx=T.SP_SM, pady=(0, T.SP_XS))

            for i, (name, secs) in enumerate(apps[:5]):
                app_row = ctk.CTkFrame(card, fg_color="transparent")
                app_row.pack(fill="x", padx=T.SP_MD, pady=1)

                color = T.CHART_COLORS[i % len(T.CHART_COLORS)]
                ctk.CTkLabel(
                    app_row, text="\u25cf",
                    font=font(T.SIZE_MICRO), text_color=color, width=14,
                ).pack(side="left")

                disp = name if len(name) <= 20 else name[:18] + "\u2026"
                ctk.CTkLabel(
                    app_row, text=disp,
                    font=font(T.SIZE_CAPTION),
                    text_color=T.TEXT_PRIMARY, anchor="w",
                ).pack(side="left", fill="x", expand=True)

                ctk.CTkLabel(
                    app_row, text=compact_duration(secs),
                    font=font(T.SIZE_CAPTION),
                    text_color=T.TEXT_TERTIARY, anchor="e",
                ).pack(side="right")

        # bottom pad
        ctk.CTkFrame(card, fg_color="transparent", height=T.SP_XS).pack()

        # ── position & clamp ──
        popup.update_idletasks()
        ph = popup.winfo_reqheight()
        px = anchor_x - popup_w // 2
        py = anchor_y

        px = max(8, min(px, screen_w - popup_w - 8))
        if py + ph > screen_h - 40:
            py = root_y + int(row * cell_h) - ph - 4

        popup.geometry(f"{popup_w}x{ph}+{px}+{py}")

    def _dismiss_popup(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
            self._popup_day = None

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            self._dismiss_popup()

    # ── Month navigation ───────────────────────────────────────────────

    def _shift_month(self, delta: int) -> None:
        idx = (self._month_anchor.year * 12
               + (self._month_anchor.month - 1)) + delta
        y, m = divmod(idx, 12)
        new_anchor = date(y, m + 1, 1)
        day_num = min(self._selected_day.day,
                      calendar.monthrange(y, m + 1)[1])
        new_selected = date(y, m + 1, day_num)
        self._dismiss_popup()
        self._on_day_selected(new_selected)

    def _jump_today(self) -> None:
        self._dismiss_popup()
        self._on_day_selected(date.today())
