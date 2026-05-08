"""
StatisticsWindow v4 — Apple-grade UI with theme switching.

Layout:
    ┌──────────────────────────────────────────────────────────┐
    │  ● ● ●  WinVibeTime — 使用时间追踪    [🌙] [ 刷新 ]    │
    ├──────────────────────────────────────────────────────────┤
    │                [ 今日 | 本周 | 历史 ]                    │
    ├──────────────────────────────────────────────────────────┤
    │   ┌──────────────────────────────────┐  Glass hero      │
    │   └──────────────────────────────────┘                  │
    │   ┌──────────────────────────────────┐  Chart card      │
    │   └──────────────────────────────────┘                  │
    │   ┌──────────────────────────────────┐  Expandable list │
    │   └──────────────────────────────────┘                  │
    └──────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import os
import tkinter as tk
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import customtkinter as ctk

from . import design_tokens as T
from .components import (
    AppleStyleBarChart,
    AppleStyleCalendar,
    CapsuleButton,
    ExpandableAppList,
    GlassTotalCard,
    SegmentedPill,
    _animate_fg,
    _lerp_color,
    compact_duration,
    font,
    format_hours,
)
from ..models import APP_NAME, format_duration
from ..storage import DataManager


# ─── Theme mode cycle ──────────────────────────────────────────────────────

_THEME_CYCLE = ["system", "light", "dark"]
_THEME_ICONS = {
    "system": "⚙ 跟随",
    "light":  "☀ 浅色",
    "dark":   "🌙 深色",
}


def _get_system_theme() -> str:
    """Read Windows registry to detect current app colour scheme."""
    if os.name != "nt":
        return "dark"
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if value == 1 else "dark"
    except Exception:
        return "dark"


# ─── Apply theme once ──────────────────────────────────────────────────────

_THEME_APPLIED = False


def _apply_theme() -> None:
    global _THEME_APPLIED
    if _THEME_APPLIED:
        return
    _THEME_APPLIED = True

    # Initialise with the system theme so the first paint is correct
    initial = _get_system_theme()
    T.set_theme(initial)
    ctk.set_appearance_mode(initial)

    theme_path = Path(__file__).parent / "theme.json"
    if theme_path.exists():
        ctk.set_default_color_theme(str(theme_path))


# ─── Page IDs ──────────────────────────────────────────────────────────────

PAGE_TODAY   = "today"
PAGE_WEEK    = "week"
PAGE_HISTORY = "history"


# ─── Traffic-light dots (decorative macOS accent) ─────────────────────────

class _TrafficLights(ctk.CTkFrame):
    """Three macOS-style coloured dots (red / yellow / green).

    Purely decorative — the native window buttons handle close / minimize /
    maximise.  On hover the dots brighten slightly for a tactile feel.
    """

    def __init__(self, parent: ctk.CTkBaseClass, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._canvas = tk.Canvas(
            self,
            width=T.TRAFFIC_DOT_SIZE * 3 + T.TRAFFIC_DOT_GAP * 2 + 4,
            height=T.TRAFFIC_DOT_SIZE + 4,
            bg=T.BG_PRIMARY, highlightthickness=0, bd=0,
        )
        self._canvas.pack()

        self._colors = [T.TRAFFIC_RED, T.TRAFFIC_YELLOW, T.TRAFFIC_GREEN]
        self._hovered = False
        self._paint()

        self._canvas.bind("<Enter>", self._on_enter)
        self._canvas.bind("<Leave>", self._on_leave)

    def _paint(self) -> None:
        c = self._canvas
        c.delete("all")
        r = T.TRAFFIC_DOT_SIZE / 2
        for i, color in enumerate(self._colors):
            cx = 2 + r + i * (T.TRAFFIC_DOT_SIZE + T.TRAFFIC_DOT_GAP)
            cy = 2 + r
            if self._hovered:
                fill = _lerp_color(color, "#FFFFFF", 0.2)
            else:
                fill = _lerp_color(color, T.BG_PRIMARY if T.is_dark() else "#888888", 0.45)
            c.create_oval(
                cx - r, cy - r, cx + r, cy + r,
                fill=fill, outline="",
            )

    def _on_enter(self, _event: object) -> None:
        self._hovered = True
        self._paint()

    def _on_leave(self, _event: object) -> None:
        self._hovered = False
        self._paint()

    def refresh_theme(self) -> None:
        self._canvas.configure(bg=T.BG_PRIMARY)
        self._paint()


# ─── StatisticsWindow ──────────────────────────────────────────────────────

class StatisticsWindow:
    """Main application window — custom titlebar + segmented tabs + content."""

    def __init__(self, data_manager: DataManager) -> None:
        _apply_theme()

        self.data_manager = data_manager
        self.refresh_job: str | None = None
        self.is_shutting_down = False
        self.toast_windows: list[ctk.CTkToplevel] = []

        # Theme mode state
        self._theme_mode: str = "system"          # "system" | "light" | "dark"
        self._last_sys_theme: str = _get_system_theme()
        self._sys_poll_job: str | None = None

        # History state
        self._history_selected_day = date.today()
        self._history_month_anchor = date.today().replace(day=1)

        # Root window
        self.root = ctk.CTk()
        self.root.title(APP_NAME)
        self.root.geometry(T.WINDOW_DEFAULT_SIZE)
        self.root.minsize(*T.WINDOW_MIN_SIZE)
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        # DWM: dark title bar + rounded corners
        self._apply_dwm_attributes()

        # Build UI
        self._build_layout()
        self._schedule_refresh()

        # Start system-theme polling (fires even in light/dark mode — harmless)
        self._sys_poll_job = self.root.after(5000, self._poll_system_theme)

    # ── Layout ──────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        self._main_frame = ctk.CTkFrame(self.root, fg_color=T.BG_PRIMARY, corner_radius=0)
        self._main_frame.pack(fill="both", expand=True)

        # ── Custom title bar ───────────────────────────────────────────
        self._title_bar = ctk.CTkFrame(
            self._main_frame, fg_color="transparent", height=T.TITLEBAR_HEIGHT,
        )
        self._title_bar.pack(fill="x", padx=T.SP_XL, pady=(T.SP_LG, T.SP_SM))
        self._title_bar.pack_propagate(False)

        # Left cluster: traffic lights + title
        left = ctk.CTkFrame(self._title_bar, fg_color="transparent")
        left.pack(side="left", fill="y")

        self._traffic_lights = _TrafficLights(left)
        self._traffic_lights.pack(side="left", padx=(0, T.SP_SM), anchor="center")

        title_col = ctk.CTkFrame(left, fg_color="transparent")
        title_col.pack(side="left", anchor="center")

        self._title_label = ctk.CTkLabel(
            title_col, text="WinVibeTime",
            font=font(T.SIZE_DISPLAY, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        )
        self._title_label.pack(fill="x")

        self._subtitle_label = ctk.CTkLabel(
            title_col, text="\u4f7f\u7528\u65f6\u95f4\u8ffd\u8e2a",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_TERTIARY, anchor="w",
        )
        self._subtitle_label.pack(fill="x", pady=(2, 0))

        # Right cluster: theme toggle + refresh
        right = ctk.CTkFrame(self._title_bar, fg_color="transparent")
        right.pack(side="right", fill="y")

        self._theme_btn = CapsuleButton(
            right,
            text=_THEME_ICONS[self._theme_mode],
            width=84,
            command=self._toggle_theme,
        )
        self._theme_btn.pack(side="right", anchor="center", padx=(T.SP_XS, 0))

        self._refresh_btn = CapsuleButton(
            right, text="\u5237\u65b0",
            command=self.refresh_view, width=72,
        )
        self._refresh_btn.pack(side="right", anchor="center")

        # ── Separator ──────────────────────────────────────────────────
        self._sep1 = ctk.CTkFrame(
            self._main_frame, height=1,
            fg_color=T.SEPARATOR, corner_radius=0,
        )
        self._sep1.pack(fill="x", padx=T.SP_LG)

        # ── Segmented tab bar ──────────────────────────────────────────
        tab_bar = ctk.CTkFrame(self._main_frame, fg_color="transparent")
        tab_bar.pack(fill="x", pady=T.SP_SM)

        self._segmented = SegmentedPill(
            tab_bar,
            items=[
                (PAGE_TODAY,   "\u4eca\u65e5"),
                (PAGE_WEEK,    "\u672c\u5468"),
                (PAGE_HISTORY, "\u5386\u53f2"),
            ],
            on_select=self._switch_page,
        )
        self._segmented.pack(anchor="center")

        # ── Separator ──────────────────────────────────────────────────
        self._sep2 = ctk.CTkFrame(
            self._main_frame, height=1,
            fg_color=T.SEPARATOR, corner_radius=0,
        )
        self._sep2.pack(fill="x", padx=T.SP_LG)

        # ── Content area ───────────────────────────────────────────────
        self._content = ctk.CTkFrame(
            self._main_frame, fg_color=T.BG_PRIMARY, corner_radius=0,
        )
        self._content.pack(fill="both", expand=True)

        # Build pages
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._build_today_page()
        self._build_week_page()
        self._build_history_page()

        # Show default page
        self._current_page = ""
        self._switch_page(PAGE_TODAY)

    def _switch_page(self, page_id: str) -> None:
        if page_id == self._current_page:
            return

        if self._current_page in self._pages:
            self._pages[self._current_page].pack_forget()

        self._current_page = page_id
        self._segmented.set_active(page_id)

        if page_id in self._pages:
            self._pages[page_id].pack(fill="both", expand=True)
        self.refresh_view()

    # ── Today Page ──────────────────────────────────────────────────────

    def _build_today_page(self) -> None:
        page = ctk.CTkScrollableFrame(
            self._content, fg_color=T.BG_PRIMARY, corner_radius=0,
        )
        self._pages[PAGE_TODAY] = page

        # Date caption
        ctk.CTkLabel(
            page,
            text=datetime.now().strftime("%Y\u5e74%m\u6708%d\u65e5"),
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=T.SP_XL, pady=(T.SP_LG, T.SP_SM))

        # Glass hero card
        self._today_glass = GlassTotalCard(page)
        self._today_glass.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_SM))

        # Chart
        self._today_chart = AppleStyleBarChart(
            page, title="\u5e94\u7528\u4f7f\u7528\u65f6\u957f",
            border_width=1, border_color=T.SEPARATOR,
        )
        self._today_chart.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_SM))
        self._today_chart.configure(height=320)

        # Expandable detail list
        self._today_detail = ExpandableAppList(
            page, title="\u5e94\u7528\u660e\u7ec6",
            border_width=1, border_color=T.SEPARATOR,
        )
        self._today_detail.pack(
            fill="both", expand=True, padx=T.SP_XL, pady=(T.SP_SM, T.SP_XL),
        )
        self._today_detail.configure(height=300)

    # ── Week Page ───────────────────────────────────────────────────────

    def _build_week_page(self) -> None:
        page = ctk.CTkScrollableFrame(
            self._content, fg_color=T.BG_PRIMARY, corner_radius=0,
        )
        self._pages[PAGE_WEEK] = page

        # Date range caption
        today = date.today()
        week_start = today - timedelta(days=today.weekday())
        ctk.CTkLabel(
            page,
            text=f"{week_start.strftime('%m\u6708%d\u65e5')} \u2014 {today.strftime('%m\u6708%d\u65e5')}",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=T.SP_XL, pady=(T.SP_LG, T.SP_SM))

        # Glass hero card
        self._week_glass = GlassTotalCard(page)
        self._week_glass.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_SM))

        # Chart
        self._week_chart = AppleStyleBarChart(
            page, title="\u672c\u5468\u5e94\u7528\u4f7f\u7528\u65f6\u957f",
            border_width=1, border_color=T.SEPARATOR,
        )
        self._week_chart.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_SM))
        self._week_chart.configure(height=320)

        # Expandable detail list
        self._week_detail = ExpandableAppList(
            page, title="\u5e94\u7528\u660e\u7ec6",
            border_width=1, border_color=T.SEPARATOR,
        )
        self._week_detail.pack(
            fill="both", expand=True, padx=T.SP_XL, pady=(T.SP_SM, T.SP_XL),
        )
        self._week_detail.configure(height=300)

    # ── History Page ────────────────────────────────────────────────────

    def _build_history_page(self) -> None:
        page = ctk.CTkScrollableFrame(
            self._content, fg_color=T.BG_PRIMARY, corner_radius=0,
        )
        self._pages[PAGE_HISTORY] = page

        # Hint caption
        ctk.CTkLabel(
            page,
            text="\u9009\u62e9\u65e5\u671f\u67e5\u770b\u5f53\u5929\u4f7f\u7528\u8be6\u60c5",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=T.SP_XL, pady=(T.SP_LG, T.SP_SM))

        # Calendar
        self._calendar = AppleStyleCalendar(
            page,
            on_day_selected=self._on_history_day_selected,
            fetch_day_summary=self._fetch_day_summary,
            border_width=1, border_color=T.SEPARATOR,
        )
        self._calendar.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_SM))

        # Selected day summary
        self._history_summary_frame = ctk.CTkFrame(page, fg_color="transparent")
        self._history_summary_frame.pack(fill="x", padx=T.SP_XL, pady=(0, T.SP_XS))

        self._history_date_label = ctk.CTkLabel(
            self._history_summary_frame, text="",
            font=font(T.SIZE_HEADLINE, T.WEIGHT_BOLD),
            text_color=T.TEXT_PRIMARY, anchor="w",
        )
        self._history_date_label.pack(fill="x")

        self._history_total_label = ctk.CTkLabel(
            self._history_summary_frame,
            text="\u603b\u6d3b\u8dc3\u65f6\u957f: \u2014",
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY, anchor="w",
        )
        self._history_total_label.pack(fill="x", pady=(2, 0))

        # Chart
        self._history_chart = AppleStyleBarChart(
            page, title="\u5f53\u65e5\u4f7f\u7528\u65f6\u957f",
            border_width=1, border_color=T.SEPARATOR,
        )
        self._history_chart.pack(fill="x", padx=T.SP_XL, pady=(T.SP_XS, T.SP_SM))
        self._history_chart.configure(height=260)

        # Expandable detail list
        self._history_detail = ExpandableAppList(
            page, title="\u5f53\u65e5\u660e\u7ec6",
            border_width=1, border_color=T.SEPARATOR,
        )
        self._history_detail.pack(
            fill="both", expand=True, padx=T.SP_XL, pady=(T.SP_XS, T.SP_XL),
        )
        self._history_detail.configure(height=300)

    # ── Theme switching ────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        """Cycle: system → light → dark → system."""
        idx = _THEME_CYCLE.index(self._theme_mode)
        self._apply_theme_mode(_THEME_CYCLE[(idx + 1) % len(_THEME_CYCLE)])

    def _apply_theme_mode(self, mode: str) -> None:
        """Switch to *mode* ('system' | 'light' | 'dark') and refresh UI."""
        self._theme_mode = mode
        self._theme_btn.configure(text=_THEME_ICONS[mode])

        actual = _get_system_theme() if mode == "system" else mode

        if actual == T.current_theme():
            return  # resolved colour didn't change — nothing to redraw

        T.set_theme(actual)
        ctk.set_appearance_mode(actual)
        self._apply_dwm_attributes()
        self._refresh_theme_ui()

    def _poll_system_theme(self) -> None:
        """Called every 2 s; rebuilds UI only when system theme actually changes."""
        if self.is_shutting_down:
            return
        if self._theme_mode == "system":
            detected = _get_system_theme()
            if detected != self._last_sys_theme:
                self._last_sys_theme = detected
                T.set_theme(detected)
                ctk.set_appearance_mode(detected)
                self._apply_dwm_attributes()
                self._refresh_theme_ui()
        self._sys_poll_job = self.root.after(5000, self._poll_system_theme)

    def _refresh_theme_ui(self) -> None:
        """Update persistent widgets and rebuild page contents."""
        self._main_frame.configure(fg_color=T.BG_PRIMARY)
        self._content.configure(fg_color=T.BG_PRIMARY)
        self._sep1.configure(fg_color=T.SEPARATOR)
        self._sep2.configure(fg_color=T.SEPARATOR)
        self._title_label.configure(text_color=T.TEXT_PRIMARY)
        self._subtitle_label.configure(text_color=T.TEXT_TERTIARY)
        self._traffic_lights.refresh_theme()
        self._rebuild_pages()

    def _rebuild_pages(self) -> None:
        """Destroy all pages and rebuild with current theme colours."""
        remembered_page = self._current_page

        for page in self._pages.values():
            page.destroy()
        self._pages.clear()

        self._build_today_page()
        self._build_week_page()
        self._build_history_page()

        self._current_page = ""
        self._switch_page(remembered_page or PAGE_TODAY)

    # ── History callbacks ───────────────────────────────────────────────

    def _on_history_day_selected(self, target_day: date) -> None:
        self._history_selected_day = target_day
        self._history_month_anchor = target_day.replace(day=1)
        self._refresh_history()

    def _fetch_day_summary(self, day: date) -> dict:
        """Return lightweight summary for the calendar popup."""
        key = day.isoformat()
        rows = self.data_manager.fetch_software_totals_for_day(key)
        total = sum(float(r["total_seconds"] or 0) for r in rows)
        apps = [
            (str(r["process_name"]), float(r["total_seconds"] or 0))
            for r in rows[:5]
        ]
        return {"total_seconds": total, "apps": apps}

    # ── Data refresh ────────────────────────────────────────────────────

    def refresh_view(self) -> None:
        if self.is_shutting_down:
            return

        if self._current_page in (PAGE_TODAY, PAGE_WEEK):
            self._refresh_period(self._current_page)
        elif self._current_page == PAGE_HISTORY:
            self._refresh_history()

    def _refresh_period(self, range_name: str) -> None:
        software_rows = self.data_manager.fetch_software_totals(range_name)
        window_rows = self.data_manager.fetch_window_details(range_name)
        grouped_windows: dict[tuple[str, str], list] = defaultdict(list)

        for row in window_rows:
            grouped_windows[(row["process_name"], row["exe_path"] or "")].append(row)

        total_seconds = sum(float(row["total_seconds"] or 0) for row in software_rows)
        app_count = len(software_rows)
        top_app = str(software_rows[0]["process_name"]) if software_rows else "\u2014"

        chart_data = [
            (str(r["process_name"]), float(r["total_seconds"] or 0))
            for r in software_rows[:8]
        ]

        if range_name == PAGE_TODAY:
            self._today_glass.set_data(total_seconds, app_count, top_app)
            self._today_chart.set_data(chart_data)
            self._today_detail.set_data(software_rows, grouped_windows)

        elif range_name == PAGE_WEEK:
            self._week_glass.set_data(total_seconds, app_count, top_app)
            self._week_chart.set_data(chart_data)
            self._week_detail.set_data(software_rows, grouped_windows)

    def _refresh_history(self) -> None:
        import calendar as cal_mod

        anchor = self._history_month_anchor
        last_day = cal_mod.monthrange(anchor.year, anchor.month)[1]
        month_end = date(anchor.year, anchor.month, last_day)

        day_from = anchor.isoformat()
        day_to = month_end.isoformat()
        total_rows = self.data_manager.fetch_daily_totals(day_from, day_to)
        day_totals = {
            str(row["day_key"]): float(row["total_seconds"] or 0)
            for row in total_rows
        }

        self._calendar.update_data(anchor, self._history_selected_day, day_totals)

        # Selected day data
        selected_key = self._history_selected_day.isoformat()
        software_rows = self.data_manager.fetch_software_totals_for_day(selected_key)
        window_rows = self.data_manager.fetch_window_details_for_day(selected_key)
        grouped_windows: dict[tuple[str, str], list] = defaultdict(list)

        for row in window_rows:
            grouped_windows[(row["process_name"], row["exe_path"] or "")].append(row)

        total_seconds = sum(float(row["total_seconds"] or 0) for row in software_rows)

        self._history_date_label.configure(
            text=f"{self._history_selected_day.strftime('%Y-%m-%d')} \u7edf\u8ba1"
        )
        self._history_total_label.configure(
            text=f"\u603b\u6d3b\u8dc3\u65f6\u957f: {format_duration(total_seconds)}"
        )

        chart_data = [
            (str(r["process_name"]), float(r["total_seconds"] or 0))
            for r in software_rows[:8]
        ]
        self._history_chart.set_data(chart_data)
        self._history_detail.set_data(software_rows, grouped_windows)

    # ── Timer-based refresh ─────────────────────────────────────────────

    def _schedule_refresh(self) -> None:
        if self.is_shutting_down:
            return
        self.refresh_job = self.root.after(5000, self._refresh_from_timer)

    def _refresh_from_timer(self) -> None:
        self.refresh_job = None
        if not self.is_shutting_down:
            self.refresh_view()
            self._schedule_refresh()

    # ── Window management ───────────────────────────────────────────────

    def call_in_ui_thread(self, callback: object) -> None:
        if self.is_shutting_down:
            return
        self.root.after(0, callback)

    def show(self) -> None:
        if self.is_shutting_down:
            return
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.refresh_view()

    def hide(self) -> None:
        if self.is_shutting_down:
            return
        self.root.withdraw()

    def run(self) -> None:
        self.root.mainloop()

    def shutdown(self) -> None:
        self.call_in_ui_thread(self._shutdown_impl)

    def show_info(self, title: str, message: str) -> None:
        self.call_in_ui_thread(lambda: self._show_toast(title, message))

    def show_error(self, title: str, message: str) -> None:
        self.call_in_ui_thread(lambda: self._show_toast(title, message, is_error=True))

    # ── Toast notification ──────────────────────────────────────────────

    def _show_toast(
        self, title: str, message: str,
        duration_ms: int = 3500, is_error: bool = False,
    ) -> None:
        if self.is_shutting_down:
            return

        toast = ctk.CTkToplevel(self.root)
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)

        card = ctk.CTkFrame(
            toast,
            corner_radius=T.RADIUS_MD,
            fg_color=T.BG_SECONDARY,
            border_width=1,
            border_color=T.SEPARATOR,
        )
        card.pack(fill="both", expand=True, padx=1, pady=1)

        ctk.CTkLabel(
            card, text=title,
            font=font(T.SIZE_BODY, T.WEIGHT_BOLD),
            text_color=T.DANGER if is_error else T.TEXT_PRIMARY,
            anchor="w",
        ).pack(fill="x", padx=T.SP_MD, pady=(T.SP_SM, T.SP_XXS))

        ctk.CTkLabel(
            card, text=message,
            font=font(T.SIZE_CAPTION),
            text_color=T.TEXT_SECONDARY, anchor="w",
            wraplength=300, justify="left",
        ).pack(fill="x", padx=T.SP_MD, pady=(0, T.SP_SM))

        toast.update_idletasks()
        self.toast_windows.append(toast)
        self._reposition_toasts()

        # Fade-in: start transparent, animate to opaque
        toast.attributes("-alpha", 0.0)
        self._fade_toast_in(toast, 0)

        toast.after(duration_ms, lambda: self._dismiss_toast(toast))

    def _fade_toast_in(self, toast: ctk.CTkToplevel, step: int) -> None:
        steps = 6
        if step > steps:
            return
        try:
            alpha = step / steps
            toast.attributes("-alpha", alpha)
            toast.after(30, self._fade_toast_in, toast, step + 1)
        except Exception:
            pass

    def _dismiss_toast(self, toast: ctk.CTkToplevel) -> None:
        if toast in self.toast_windows:
            self.toast_windows.remove(toast)
        try:
            toast.destroy()
        except Exception:
            pass
        self._reposition_toasts()

    def _reposition_toasts(self) -> None:
        margin = T.SP_LG
        gap = T.SP_SM
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        for i, toast in enumerate(reversed(self.toast_windows)):
            try:
                toast.update_idletasks()
                w = toast.winfo_reqwidth()
                h = toast.winfo_reqheight()
                x = sw - w - margin
                y = sh - ((i + 1) * (h + gap)) - margin
                toast.geometry(f"{w}x{h}+{x}+{y}")
            except Exception:
                continue

    # ── Shutdown ────────────────────────────────────────────────────────

    def _shutdown_impl(self) -> None:
        if self.is_shutting_down:
            return
        self.is_shutting_down = True

        if self.refresh_job is not None:
            try:
                self.root.after_cancel(self.refresh_job)
            except Exception:
                pass
            self.refresh_job = None

        if self._sys_poll_job is not None:
            try:
                self.root.after_cancel(self._sys_poll_job)
            except Exception:
                pass
            self._sys_poll_job = None

        for toast in list(self.toast_windows):
            try:
                toast.destroy()
            except Exception:
                pass
        self.toast_windows.clear()

        self.root.quit()
        self.root.destroy()

    # ── Platform helpers ────────────────────────────────────────────────

    def _apply_dwm_attributes(self) -> None:
        """Set Windows 10/11 DWM dark title bar + Windows 11 rounded corners."""
        if os.name != "nt":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())

            # Dark / light title bar (attribute 20, fallback 19)
            dark_value = ctypes.c_int(1 if T.is_dark() else 0)
            for attr_id in (20, 19):
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr_id,
                    ctypes.byref(dark_value),
                    ctypes.sizeof(dark_value),
                )
                if result == 0:
                    break

            # Rounded corners on Windows 11 (Build 22000+)
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33, DWMWCP_ROUND = 2
            corner_value = ctypes.c_int(2)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33,
                ctypes.byref(corner_value),
                ctypes.sizeof(corner_value),
            )
        except Exception:
            pass
