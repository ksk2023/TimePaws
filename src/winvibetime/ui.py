from __future__ import annotations

import calendar
import threading
import tkinter as tk
import tkinter.font
from collections import defaultdict
from datetime import date, datetime, timedelta
from tkinter import messagebox, scrolledtext, ttk
import sys

from .config import ConfigManager, DEFAULT_CONFIG
from .models import APP_NAME, format_duration
from .storage import DataManager
from .system_integration import disable_startup, enable_startup, startup_enabled
from .tracker import WindowTracker

try:
    import customtkinter as ctk

    CUSTOMTKINTER_AVAILABLE = True
except ModuleNotFoundError:
    ctk = None
    CUSTOMTKINTER_AVAILABLE = False

try:
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.figure import Figure
    import matplotlib
    import matplotlib.font_manager as fm

    MATPLOTLIB_AVAILABLE = True
except ModuleNotFoundError:
    FigureCanvasTkAgg = None
    Figure = None
    MATPLOTLIB_AVAILABLE = False

try:
    import pystray

    PYSTRAY_AVAILABLE = True
except ModuleNotFoundError:
    pystray = None
    PYSTRAY_AVAILABLE = False

try:
    from PIL import Image, ImageDraw

    PIL_AVAILABLE = True
except ModuleNotFoundError:
    Image = None
    ImageDraw = None
    PIL_AVAILABLE = False


TKINTER_AVAILABLE = True
UI_AVAILABLE = TKINTER_AVAILABLE and MATPLOTLIB_AVAILABLE and PYSTRAY_AVAILABLE and PIL_AVAILABLE

# --- Claude-inspired palette ---
_BG = "#F7F5F2"
_BG_SECONDARY = "#EFEDE8"
_CARD_BG = "#FFFFFF"
_TEXT_PRIMARY = "#2D2B28"
_TEXT_SECONDARY = "#6B6966"
_TEXT_TERTIARY = "#9B9894"
_ACCENT = "#C96442"
_ACCENT_HOVER = "#A8503A"
_ACCENT_LIGHT = "#FDF0EB"
_SEPARATOR = "#E8E5E0"
_SELECTED = "#FDF0EB"
_SELECTED_BORDER = "#C96442"
_TODAY_BG = "#F5EDE8"
_DANGER = "#D64045"
_SUCCESS = "#3A8F5C"
_CORNER = 12

# --- Cross-platform font detection ---
_CJK_FONT_CANDIDATES = [
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "SimHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "Source Han Sans SC",
]
_UI_FONT_CANDIDATES = [
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "Segoe UI",
    "PingFang SC",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
]
_MONO_FONT_CANDIDATES = [
    "Cascadia Code",
    "Consolas",
    "Menlo",
    "Ubuntu Mono",
    "DejaVu Sans Mono",
]


def _detect_font(candidates: list[str], fallback: str) -> str:
    """Pick the first available font from *candidates*, or return *fallback*."""
    try:
        _root = tk.Tk()
        _root.withdraw()
        available = set(tk.font.families(_root))
        _root.destroy()
        for name in candidates:
            if name in available:
                return name
    except Exception:
        pass
    return fallback


# Lazy-init: resolved on first use by StatisticsWindow.__init__
_FONT: str = ""
_FONT_MONO: str = ""
_FONTS_RESOLVED = False


def _resolve_fonts() -> None:
    global _FONT, _FONT_MONO, _FONTS_RESOLVED
    if _FONTS_RESOLVED:
        return
    _FONT = _detect_font(_UI_FONT_CANDIDATES, "TkDefaultFont")
    _FONT_MONO = _detect_font(_MONO_FONT_CANDIDATES, "TkFixedFont")
    # Configure matplotlib CJK font
    if MATPLOTLIB_AVAILABLE:
        mpl_font = _detect_font(_CJK_FONT_CANDIDATES, "")
        if mpl_font:
            matplotlib.rcParams["font.sans-serif"] = [mpl_font] + matplotlib.rcParams.get("font.sans-serif", [])
        else:
            matplotlib.rcParams["font.sans-serif"] = [_FONT] + matplotlib.rcParams.get("font.sans-serif", [])
        matplotlib.rcParams["axes.unicode_minus"] = False
    _FONTS_RESOLVED = True


def default_ignore_config() -> dict[str, list[str]]:
    return {
        "ignore_process_names": list(DEFAULT_CONFIG["ignore_process_names"]),
        "ignore_window_title_keywords": list(DEFAULT_CONFIG["ignore_window_title_keywords"]),
        "ignore_exe_path_keywords": list(DEFAULT_CONFIG["ignore_exe_path_keywords"]),
    }


def compact_duration(total_seconds: float) -> str:
    seconds = max(0, int(round(float(total_seconds))))
    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{seconds}s"


def weekday_label(value: date) -> str:
    weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return weekday_names[value.weekday()]


def month_start(value: date) -> date:
    return value.replace(day=1)


def shift_month(value: date, delta: int) -> date:
    month_index = (value.year * 12 + (value.month - 1)) + delta
    year, month_offset = divmod(month_index, 12)
    month = month_offset + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


class StatisticsWindow:
    def __init__(self, data_manager: DataManager) -> None:
        if not TKINTER_AVAILABLE or not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("Tkinter UI dependencies are not available.")

        _resolve_fonts()

        if CUSTOMTKINTER_AVAILABLE:
            ctk.set_appearance_mode("light")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()

        self.data_manager = data_manager
        self.refresh_job: str | None = None
        self.is_shutting_down = False
        self.period_views: dict[str, dict[str, object]] = {}
        self.history_view: dict[str, object] | None = None
        self.toast_windows: list[tk.Toplevel] = []
        self.history_selected_day = datetime.now().date()
        self.history_month_anchor = month_start(self.history_selected_day)

        self.root.title(APP_NAME)
        self.root.geometry("1280x920")
        self.root.minsize(800, 600)
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.hide)

        self._configure_style()
        self._build_layout()
        self._schedule_refresh()

    def _configure_style(self) -> None:
        if CUSTOMTKINTER_AVAILABLE:
            self.root.configure(fg_color=_BG)
        else:
            self.root.configure(bg=_BG)
        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "WinVibe.Treeview",
            background=_CARD_BG,
            foreground=_TEXT_PRIMARY,
            fieldbackground=_CARD_BG,
            rowheight=32,
            borderwidth=0,
            font=(_FONT, 11),
        )
        style.configure(
            "WinVibe.Treeview.Heading",
            background=_BG_SECONDARY,
            foreground=_TEXT_SECONDARY,
            relief="flat",
            padding=(10, 8),
            font=(_FONT, 11, "bold"),
        )
        style.map(
            "WinVibe.Treeview",
            background=[("selected", _SELECTED)],
            foreground=[("selected", _TEXT_PRIMARY)],
        )
        try:
            style.layout("WinVibe.Notebook", style.layout("TNotebook"))
            style.layout("WinVibe.Notebook.Tab", style.layout("TNotebook.Tab"))
        except tk.TclError:
            pass
        style.configure(
            "WinVibe.Notebook",
            background=_BG,
            borderwidth=0,
            tabmargins=(0, 0, 0, 0),
        )
        style.configure(
            "WinVibe.Notebook.Tab",
            padding=(16, 8),
            font=(_FONT, 12),
            background=_BG_SECONDARY,
            foreground=_TEXT_SECONDARY,
        )
        style.map(
            "WinVibe.Notebook.Tab",
            background=[("selected", _CARD_BG)],
            foreground=[("selected", _ACCENT)],
        )

    def _build_layout(self) -> None:
        container = self._make_frame(self.root, fg=_BG)
        container.pack(fill="both", expand=True, padx=20, pady=(16, 12))

        header = self._make_frame(container, fg=_BG)
        header.pack(fill="x", pady=(0, 4))

        title = self._make_label(header, "WinVibeTime", font=(_FONT, 20, "bold"), color=_TEXT_PRIMARY)
        title.pack(side="left")

        refresh_button = self._make_button(header, "刷新", command=self.refresh_view, width=72)
        refresh_button.pack(side="right")

        subtitle_text = "追踪你的应用使用时间，了解每一天的效率分布"
        subtitle = self._make_label(container, subtitle_text, font=(_FONT, 11), color=_TEXT_SECONDARY)
        subtitle.pack(fill="x", pady=(0, 12))

        notebook = ttk.Notebook(container, style="WinVibe.Notebook")
        notebook.pack(fill="both", expand=True)
        self.notebook = notebook

        for range_name, label in (("today", "今日"), ("week", "本周")):
            tab_host = self._make_frame(notebook, fg=_BG)
            notebook.add(tab_host, text=f" {label} ")
            self.period_views[range_name] = self._build_period_tab(tab_host, label)

        history_host = self._make_frame(notebook, fg=_BG)
        notebook.add(history_host, text=" 历史 ")
        self.history_view = self._build_history_tab(history_host)

    def _build_period_tab(self, parent: tk.Misc, label: str) -> dict[str, object]:
        # Scrollable wrapper
        outer = tk.Frame(parent, bg=_BG, highlightthickness=0)
        outer.pack(fill="both", expand=True)

        vscroll = ttk.Scrollbar(outer, orient="vertical")
        vscroll.pack(side="right", fill="y")

        scroll_canvas = tk.Canvas(outer, bg=_BG, highlightthickness=0, bd=0)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        scroll_canvas.configure(yscrollcommand=vscroll.set)
        vscroll.configure(command=scroll_canvas.yview)

        content = tk.Frame(scroll_canvas, bg=_BG)
        content_window = scroll_canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_configure(_event: object = None) -> None:
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def _on_canvas_configure(event: object) -> None:
            scroll_canvas.itemconfigure(content_window, width=event.width)

        content.bind("<Configure>", _on_content_configure)
        scroll_canvas.bind("<Configure>", _on_canvas_configure)
        self._bind_mousewheel(scroll_canvas)

        # Summary
        summary = self._make_frame(content, fg=_CARD_BG)
        summary.pack(fill="x", padx=8, pady=(8, 10))

        summary_label = self._make_label(summary, f"{label}概览", font=(_FONT, 15, "bold"), color=_TEXT_PRIMARY)
        summary_label.pack(anchor="w", padx=16, pady=(12, 2))

        total_label = self._make_label(summary, "总活跃时长: 0s", font=(_FONT, 11), color=_TEXT_SECONDARY)
        total_label.pack(anchor="w", padx=16, pady=(0, 12))

        # Chart
        chart_card = self._make_frame(content, fg=_CARD_BG)
        chart_card.pack(fill="x", padx=8, pady=(0, 10))

        figure = Figure(figsize=(7, 3), dpi=100)
        figure.subplots_adjust(left=0.18, right=0.92, top=0.88, bottom=0.15)
        axis = figure.add_subplot(111)
        figure.patch.set_facecolor(_CARD_BG)
        axis.set_facecolor(_CARD_BG)

        canvas = FigureCanvasTkAgg(figure, master=chart_card)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=12)

        # App detail list
        list_card = self._make_frame(content, fg=_CARD_BG)
        list_card.pack(fill="x", padx=8, pady=(0, 8))

        list_title = self._make_label(list_card, "应用明细", font=(_FONT, 14, "bold"), color=_TEXT_PRIMARY)
        list_title.pack(anchor="w", padx=16, pady=(12, 8))

        tree_host = tk.Frame(list_card, bg=_CARD_BG, highlightthickness=0)
        tree_host.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("duration", "hwnd", "path")
        tree = ttk.Treeview(
            tree_host,
            columns=columns,
            show="tree headings",
            style="WinVibe.Treeview",
            height=12,
        )
        tree.heading("#0", text="应用 / 窗口")
        tree.heading("duration", text="时长")
        tree.heading("hwnd", text="HWND")
        tree.heading("path", text="路径")

        tree.column("#0", width=220, minwidth=120, stretch=True)
        tree.column("duration", width=80, minwidth=60, stretch=False, anchor="e")
        tree.column("hwnd", width=80, minwidth=60, stretch=False, anchor="center")
        tree.column("path", width=240, minwidth=80, stretch=True)

        scrollbar = ttk.Scrollbar(tree_host, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)

        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._bind_mousewheel(tree)

        return {
            "label": label,
            "total_label": total_label,
            "figure": figure,
            "axis": axis,
            "canvas": canvas,
            "tree": tree,
        }

    def _build_history_tab(self, parent: tk.Misc) -> dict[str, object]:
        # Scrollable wrapper
        outer = tk.Frame(parent, bg=_BG, highlightthickness=0)
        outer.pack(fill="both", expand=True)

        vscroll = ttk.Scrollbar(outer, orient="vertical")
        vscroll.pack(side="right", fill="y")

        scroll_canvas = tk.Canvas(outer, bg=_BG, highlightthickness=0, bd=0)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        scroll_canvas.configure(yscrollcommand=vscroll.set)
        vscroll.configure(command=scroll_canvas.yview)

        content = tk.Frame(scroll_canvas, bg=_BG)
        content_window = scroll_canvas.create_window((0, 0), window=content, anchor="nw")

        def _on_content_configure(_event: object = None) -> None:
            scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))

        def _on_canvas_configure(event: object) -> None:
            scroll_canvas.itemconfigure(content_window, width=event.width)

        content.bind("<Configure>", _on_content_configure)
        scroll_canvas.bind("<Configure>", _on_canvas_configure)
        self._bind_mousewheel(scroll_canvas)

        # Navigation
        nav_card = self._make_frame(content, fg=_CARD_BG)
        nav_card.pack(fill="x", padx=8, pady=(8, 10))

        nav_row = tk.Frame(nav_card, bg=_CARD_BG, highlightthickness=0)
        nav_row.pack(fill="x", padx=16, pady=(10, 2))

        prev_button = self._make_button(nav_row, "<", lambda: self._shift_history_month(-1), width=40)
        prev_button.pack(side="left")

        month_label = self._make_label(nav_row, "", (_FONT, 15, "bold"), _TEXT_PRIMARY)
        month_label.pack(side="left", padx=12)

        next_button = self._make_button(nav_row, ">", lambda: self._shift_history_month(1), width=40)
        next_button.pack(side="left")

        jump_today_button = self._make_button(nav_row, "今天", self._jump_history_today, width=60)
        jump_today_button.pack(side="right")

        hint_label = self._make_label(
            nav_card,
            "点击日期查看当天详情",
            (_FONT, 10),
            _TEXT_TERTIARY,
        )
        hint_label.pack(anchor="w", padx=16, pady=(0, 8))

        # Calendar grid
        calendar_card = self._make_frame(content, fg=_CARD_BG)
        calendar_card.pack(fill="x", padx=8, pady=(0, 10))

        calendar_host = tk.Frame(calendar_card, bg=_CARD_BG, highlightthickness=0)
        calendar_host.pack(fill="x", padx=8, pady=8)
        for column in range(7):
            calendar_host.grid_columnconfigure(column, weight=1, uniform="cal")

        for column in range(7):
            header = tk.Label(
                calendar_host,
                text=weekday_label(date(2026, 4, column + 13)),
                font=(_FONT, 10, "bold"),
                fg=_TEXT_TERTIARY,
                bg=_CARD_BG,
                pady=4,
            )
            header.grid(row=0, column=column, sticky="ew", padx=2, pady=(0, 4))

        day_buttons: list[tk.Widget] = []
        for index in range(42):
            button = tk.Button(
                calendar_host,
                text="",
                justify="center",
                anchor="center",
                relief="flat",
                bd=0,
                font=(_FONT, 10),
                padx=2,
                pady=4,
                cursor="hand2",
            )
            row = (index // 7) + 1
            column = index % 7
            button.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=2,
                pady=2,
            )
            day_buttons.append(button)

        # Selected day summary
        summary = self._make_frame(content, fg=_CARD_BG)
        summary.pack(fill="x", padx=8, pady=(0, 10))

        selected_label = self._make_label(summary, "", (_FONT, 15, "bold"), _TEXT_PRIMARY)
        selected_label.pack(anchor="w", padx=16, pady=(12, 2))

        total_label = self._make_label(summary, "总活跃时长: 0s", (_FONT, 11), _TEXT_SECONDARY)
        total_label.pack(anchor="w", padx=16, pady=(0, 12))

        # Chart
        chart_card = self._make_frame(content, fg=_CARD_BG)
        chart_card.pack(fill="x", padx=8, pady=(0, 10))

        figure = Figure(figsize=(7, 3), dpi=100)
        figure.subplots_adjust(left=0.18, right=0.92, top=0.88, bottom=0.15)
        axis = figure.add_subplot(111)
        figure.patch.set_facecolor(_CARD_BG)
        axis.set_facecolor(_CARD_BG)

        canvas = FigureCanvasTkAgg(figure, master=chart_card)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=12, pady=12)

        # Detail list
        list_card = self._make_frame(content, fg=_CARD_BG)
        list_card.pack(fill="x", padx=8, pady=(0, 8))

        list_title = self._make_label(list_card, "当日明细", (_FONT, 14, "bold"), _TEXT_PRIMARY)
        list_title.pack(anchor="w", padx=16, pady=(12, 8))

        tree_host = tk.Frame(list_card, bg=_CARD_BG, highlightthickness=0)
        tree_host.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        columns = ("duration", "hwnd", "path")
        tree = ttk.Treeview(
            tree_host,
            columns=columns,
            show="tree headings",
            style="WinVibe.Treeview",
            height=10,
        )
        tree.heading("#0", text="应用 / 窗口")
        tree.heading("duration", text="时长")
        tree.heading("hwnd", text="HWND")
        tree.heading("path", text="路径")

        tree.column("#0", width=220, minwidth=120, stretch=True)
        tree.column("duration", width=80, minwidth=60, stretch=False, anchor="e")
        tree.column("hwnd", width=80, minwidth=60, stretch=False, anchor="center")
        tree.column("path", width=240, minwidth=80, stretch=True)

        scrollbar = ttk.Scrollbar(tree_host, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self._bind_mousewheel(tree)

        return {
            "month_label": month_label,
            "calendar_buttons": day_buttons,
            "selected_label": selected_label,
            "total_label": total_label,
            "figure": figure,
            "axis": axis,
            "canvas": canvas,
            "tree": tree,
        }

    def _make_frame(self, parent: tk.Misc, fg: str) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkFrame(parent, fg_color=fg, corner_radius=_CORNER)
        return tk.Frame(parent, bg=fg, bd=0, highlightthickness=0)

    def _make_label(self, parent: tk.Misc, text: str, font: tuple[str, int, str] | tuple[str, int], color: str) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkLabel(parent, text=text, font=font, text_color=color, anchor="w")
        return tk.Label(parent, text=text, font=font, fg=color, bg=parent.cget("bg"), anchor="w")

    def _make_button(self, parent: tk.Misc, text: str, command: object, width: int = 120) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkButton(
                parent,
                text=text,
                command=command,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                corner_radius=8,
                width=width,
                height=32,
                font=(_FONT, 11),
            )
        return ttk.Button(parent, text=text, command=command, width=max(6, width // 10))

    def _bind_mousewheel(self, widget: tk.Misc) -> None:
        """Bind smooth mousewheel scrolling to a widget (Canvas or Treeview)."""
        def _on_mousewheel(event: tk.Event) -> None:
            if isinstance(widget, tk.Canvas):
                widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
            else:
                widget.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _on_linux_scroll_up(event: tk.Event) -> None:
            if isinstance(widget, tk.Canvas):
                widget.yview_scroll(-3, "units")
            else:
                widget.yview_scroll(-3, "units")

        def _on_linux_scroll_down(event: tk.Event) -> None:
            if isinstance(widget, tk.Canvas):
                widget.yview_scroll(3, "units")
            else:
                widget.yview_scroll(3, "units")

        widget.bind("<MouseWheel>", _on_mousewheel)
        widget.bind("<Button-4>", _on_linux_scroll_up)
        widget.bind("<Button-5>", _on_linux_scroll_down)

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
        self.call_in_ui_thread(lambda: messagebox.showerror(title, message, parent=self.root))

    def _show_toast(self, title: str, message: str, duration_ms: int = 3200) -> None:
        if self.is_shutting_down:
            return

        toast = tk.Toplevel(self.root)
        toast.overrideredirect(True)
        toast.configure(bg=_TEXT_PRIMARY)

        try:
            toast.attributes("-topmost", True)
        except tk.TclError:
            pass

        card = tk.Frame(toast, bg=_TEXT_PRIMARY, bd=0, highlightthickness=0)
        card.pack(fill="both", expand=True, padx=1, pady=1)

        inner = tk.Frame(card, bg="#3D3830", bd=0, highlightthickness=0)
        inner.pack(fill="both", expand=True)

        title_label = tk.Label(
            inner,
            text=title,
            font=(_FONT, 11, "bold"),
            fg="#FFFFFF",
            bg="#3D3830",
            anchor="w",
        )
        title_label.pack(fill="x", padx=14, pady=(12, 3))

        message_label = tk.Label(
            inner,
            text=message,
            font=(_FONT, 10),
            fg="#E8E5E0",
            bg="#3D3830",
            justify="left",
            anchor="w",
            wraplength=280,
        )
        message_label.pack(fill="x", padx=14, pady=(0, 12))

        toast.update_idletasks()
        self.toast_windows.append(toast)
        self._reposition_toasts()
        toast.after(duration_ms, lambda: self._dismiss_toast(toast))

    def _dismiss_toast(self, toast: tk.Toplevel) -> None:
        if toast in self.toast_windows:
            self.toast_windows.remove(toast)
        try:
            toast.destroy()
        except tk.TclError:
            pass
        self._reposition_toasts()

    def _reposition_toasts(self) -> None:
        margin_x = 24
        margin_y = 24
        gap_y = 12
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        for index, toast in enumerate(reversed(self.toast_windows)):
            try:
                toast.update_idletasks()
                width = toast.winfo_reqwidth()
                height = toast.winfo_reqheight()
                x = screen_width - width - margin_x
                y = screen_height - ((index + 1) * (height + gap_y)) - margin_y
                toast.geometry(f"{width}x{height}+{x}+{y}")
            except tk.TclError:
                continue

    def _shutdown_impl(self) -> None:
        if self.is_shutting_down:
            return
        self.is_shutting_down = True
        if self.refresh_job is not None:
            try:
                self.root.after_cancel(self.refresh_job)
            except tk.TclError:
                pass
            self.refresh_job = None
        for toast in list(self.toast_windows):
            try:
                toast.destroy()
            except tk.TclError:
                pass
        self.toast_windows.clear()
        self.root.quit()
        self.root.destroy()

    def _schedule_refresh(self) -> None:
        if self.is_shutting_down:
            return
        self.refresh_job = self.root.after(5000, self._refresh_from_timer)

    def _refresh_from_timer(self) -> None:
        self.refresh_job = None
        if not self.is_shutting_down:
            self.refresh_view()
            self._schedule_refresh()

    def refresh_view(self) -> None:
        if self.is_shutting_down:
            return

        for range_name in ("today", "week"):
            self._refresh_period(range_name)
        self._refresh_history_view()

    def _refresh_period(self, range_name: str) -> None:
        software_rows = self.data_manager.fetch_software_totals(range_name)
        window_rows = self.data_manager.fetch_window_details(range_name)
        grouped_windows: dict[tuple[str, str], list[object]] = defaultdict(list)

        for row in window_rows:
            grouped_windows[(row["process_name"], row["exe_path"] or "")].append(row)

        total_seconds = sum(float(row["total_seconds"] or 0) for row in software_rows)
        period_view = self.period_views[range_name]

        total_label = period_view["total_label"]
        total_label.configure(text=f"总活跃时长: {format_duration(total_seconds)}")

        title = "今日应用使用时长" if range_name == "today" else "本周应用使用时长"
        self._render_chart(period_view["axis"], period_view["canvas"], software_rows, title)
        self._render_tree(period_view["tree"], software_rows, grouped_windows)

    def _refresh_history_view(self) -> None:
        if self.history_view is None:
            return

        month_end = shift_month(self.history_month_anchor, 1) - timedelta(days=1)
        day_from = self.history_month_anchor.isoformat()
        day_to = month_end.isoformat()
        total_rows = self.data_manager.fetch_daily_totals(day_from, day_to)
        totals_by_day = {str(row["day_key"]): float(row["total_seconds"] or 0) for row in total_rows}

        month_label = self.history_view["month_label"]
        month_label.configure(text=self.history_month_anchor.strftime("%Y 年 %m 月"))

        first_weekday = self.history_month_anchor.weekday()
        grid_start = self.history_month_anchor - timedelta(days=first_weekday)

        for index, button in enumerate(self.history_view["calendar_buttons"]):
            current_day = grid_start + timedelta(days=index)
            total_seconds = totals_by_day.get(current_day.isoformat(), 0.0)
            day_str = str(current_day.day)
            dur_str = compact_duration(total_seconds) if total_seconds > 0 else ""
            text = f"{day_str}\n{dur_str}" if dur_str else day_str

            is_selected = current_day == self.history_selected_day
            is_today = current_day == datetime.now().date()
            is_current_month = current_day.month == self.history_month_anchor.month

            bg_color = _CARD_BG
            fg_color = _TEXT_PRIMARY
            active_bg = _SELECTED
            active_fg = _TEXT_PRIMARY

            if is_selected:
                bg_color = _SELECTED
                fg_color = _ACCENT
            elif is_today:
                bg_color = _TODAY_BG
                fg_color = _ACCENT
            elif not is_current_month:
                bg_color = _BG
                fg_color = _TEXT_TERTIARY

            button.configure(command=lambda value=current_day: self._select_history_day(value))

            try:
                button.configure(
                    text=text,
                    bg=bg_color,
                    fg=fg_color,
                    activebackground=active_bg,
                    activeforeground=active_fg,
                    highlightthickness=1 if is_selected else 0,
                    highlightbackground=_SELECTED_BORDER if is_selected else bg_color,
                )
            except tk.TclError:
                continue

        selected_day_key = self.history_selected_day.isoformat()
        software_rows = self.data_manager.fetch_software_totals_for_day(selected_day_key)
        window_rows = self.data_manager.fetch_window_details_for_day(selected_day_key)
        grouped_windows: dict[tuple[str, str], list[object]] = defaultdict(list)

        for row in window_rows:
            grouped_windows[(row["process_name"], row["exe_path"] or "")].append(row)

        total_seconds = sum(float(row["total_seconds"] or 0) for row in software_rows)
        self.history_view["selected_label"].configure(
            text=f"{self.history_selected_day.strftime('%Y-%m-%d')} 统计"
        )
        self.history_view["total_label"].configure(text=f"总活跃时长: {format_duration(total_seconds)}")
        self._render_chart(
            self.history_view["axis"],
            self.history_view["canvas"],
            software_rows,
            f"{self.history_selected_day.strftime('%Y-%m-%d')} 应用使用时长",
        )
        self._render_tree(self.history_view["tree"], software_rows, grouped_windows)

    def _select_history_day(self, target_day: date) -> None:
        self.history_selected_day = target_day
        self.history_month_anchor = month_start(target_day)
        self.refresh_view()

    def _shift_history_month(self, delta_months: int) -> None:
        next_selected = shift_month(self.history_selected_day, delta_months)
        self.history_selected_day = next_selected
        self.history_month_anchor = month_start(next_selected)
        self.refresh_view()

    def _jump_history_today(self) -> None:
        self._select_history_day(datetime.now().date())

    def _render_chart(self, axis: object, canvas: object, software_rows: list[object], title: str) -> None:
        axis.clear()
        axis.set_facecolor(_CARD_BG)

        # Font for CJK text in charts — rcParams handles the global default,
        # but we also pass FontProperties for elements that bypass rcParams.
        _chart_fp = None
        if MATPLOTLIB_AVAILABLE:
            from matplotlib.font_manager import FontProperties
            cjk = _detect_font(_CJK_FONT_CANDIDATES, _FONT if _FONT != "TkDefaultFont" else "")
            if cjk:
                _chart_fp = FontProperties(family=cjk)

        def _fp_kw() -> dict:
            return {"fontproperties": _chart_fp} if _chart_fp else {}

        if not software_rows:
            axis.text(0.5, 0.5, "暂无数据", ha="center", va="center", fontsize=13, color=_TEXT_SECONDARY, **_fp_kw())
            axis.set_xticks([])
            axis.set_yticks([])
            canvas.draw_idle()
            return

        top_rows = software_rows[:8]
        labels = [str(row["process_name"]) for row in reversed(top_rows)]
        values = [float(row["total_seconds"] or 0) / 3600.0 for row in reversed(top_rows)]
        colors = [
            "#C96442", "#8B6C5C", "#3A8F5C", "#D4944C",
            "#D64045", "#7B6BA0", "#5A9EA0", "#C47A8A",
        ]

        bars = axis.barh(labels, values, color=colors[: len(labels)], edgecolor="none", height=0.55)
        axis.set_title(title, loc="left", fontsize=13, fontweight="bold", color=_TEXT_PRIMARY, pad=10, **_fp_kw())
        axis.set_xlabel("小时", color=_TEXT_SECONDARY, fontsize=10, **_fp_kw())
        axis.tick_params(axis="x", colors=_TEXT_SECONDARY, labelsize=9)
        axis.tick_params(axis="y", colors=_TEXT_PRIMARY, labelsize=10)
        if _chart_fp:
            for tick_label in axis.get_yticklabels():
                tick_label.set_fontproperties(_chart_fp)
        axis.grid(axis="x", linestyle="-", linewidth=0.4, alpha=0.12, color=_TEXT_SECONDARY)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.spines["left"].set_visible(False)
        axis.spines["bottom"].set_color(_SEPARATOR)

        for bar, hours in zip(bars, values):
            axis.text(
                bar.get_width() + 0.02,
                bar.get_y() + bar.get_height() / 2,
                f"{hours:.1f}h",
                va="center",
                ha="left",
                fontsize=9,
                color=_TEXT_SECONDARY,
            )

        canvas.draw_idle()

    def _render_tree(
        self,
        tree: ttk.Treeview,
        software_rows: list[object],
        grouped_windows: dict[tuple[str, str], list[object]],
    ) -> None:
        for item in tree.get_children():
            tree.delete(item)

        for software_row in software_rows:
            process_name = str(software_row["process_name"])
            exe_path = str(software_row["exe_path"] or "")
            app_key = (process_name, exe_path)
            total_seconds = float(software_row["total_seconds"] or 0)

            parent_id = tree.insert(
                "",
                "end",
                text=process_name,
                values=(format_duration(total_seconds), "", exe_path or "-"),
                open=True,
            )

            for window_row in grouped_windows.get(app_key, []):
                hwnd = int(window_row["hwnd"])
                tree.insert(
                    parent_id,
                    "end",
                    text=str(window_row["window_title"] or "(无标题)"),
                    values=(
                        format_duration(float(window_row["total_seconds"] or 0)),
                        f"0x{hwnd:08X}",
                        exe_path or "-",
                    ),
                )


class SettingsWindow:
    def __init__(
        self,
        parent: tk.Misc,
        config_manager: ConfigManager,
        on_save: object,
    ) -> None:
        self.parent = parent
        self.config_manager = config_manager
        self.on_save = on_save

        if CUSTOMTKINTER_AVAILABLE:
            self.window = ctk.CTkToplevel(parent)
            self.window.configure(fg_color=_BG)
        else:
            self.window = tk.Toplevel(parent, bg=_BG)

        self.window.title(f"{APP_NAME} 设置")
        self.window.geometry("860x800")
        self.window.minsize(640, 560)
        self.window.withdraw()
        self.window.protocol("WM_DELETE_WINDOW", self.hide)

        self.minimum_timing_var = tk.StringVar()
        self.auto_save_var = tk.StringVar()
        self.idle_timeout_var = tk.StringVar()
        self.export_directory_var = tk.StringVar()
        self.recover_unsaved_var = tk.BooleanVar(value=True)
        self.launch_on_startup_var = tk.BooleanVar(value=False)
        self.debug_tracker_var = tk.BooleanVar(value=False)

        self._build_layout()
        self.load_from_manager()

    def _build_layout(self) -> None:
        container = self._make_frame(self.window, fg=_BG)
        container.pack(fill="both", expand=True, padx=20, pady=16)

        header = self._make_frame(container, fg=_BG)
        header.pack(fill="x", pady=(0, 12))

        self._make_label(header, "设置", (_FONT, 18, "bold"), _TEXT_PRIMARY).pack(anchor="w")
        self._make_label(
            header,
            "保存后立即生效，部分设置在下次启动时生效",
            (_FONT, 11),
            _TEXT_SECONDARY,
        ).pack(anchor="w", pady=(4, 0))

        form_card = self._make_frame(container, fg=_CARD_BG)
        form_card.pack(fill="x", pady=(0, 12))

        form = tk.Frame(form_card, bg=_CARD_BG, highlightthickness=0)
        form.pack(fill="x", padx=16, pady=16)
        for column in range(2):
            form.grid_columnconfigure(column, weight=1)

        self._add_entry_row(form, 0, "最小计时间隔（秒）", self.minimum_timing_var)
        self._add_entry_row(form, 1, "自动保存间隔（秒）", self.auto_save_var)
        self._add_entry_row(form, 2, "空闲暂停阈值（秒）", self.idle_timeout_var)
        self._add_entry_row(form, 3, "CSV 导出目录", self.export_directory_var)

        toggles = tk.Frame(form_card, bg=_CARD_BG, highlightthickness=0)
        toggles.pack(fill="x", padx=16, pady=(0, 16))

        self._make_checkbutton(toggles, "启动时恢复未保存的数据", self.recover_unsaved_var).pack(anchor="w", pady=(0, 8))
        self.startup_checkbox = self._make_checkbutton(toggles, "开机自动启动", self.launch_on_startup_var)
        self.startup_checkbox.pack(anchor="w", pady=(0, 8))
        self._make_checkbutton(toggles, "调试模式", self.debug_tracker_var).pack(anchor="w")

        if sys.platform != "win32":
            try:
                self.startup_checkbox.configure(state="disabled")
            except Exception:
                pass

        lists_card = self._make_frame(container, fg=_CARD_BG)
        lists_card.pack(fill="both", expand=True)

        self._make_label(lists_card, "忽略规则", (_FONT, 15, "bold"), _TEXT_PRIMARY).pack(anchor="w", padx=16, pady=(12, 8))

        list_host = tk.Frame(lists_card, bg=_CARD_BG, highlightthickness=0)
        list_host.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        for column in range(3):
            list_host.grid_columnconfigure(column, weight=1)

        self.process_text = self._add_text_group(list_host, 0, "忽略进程名", "每行一个，如 explorer.exe")
        self.title_text = self._add_text_group(list_host, 1, "忽略标题关键字", "每行一个关键字")
        self.path_text = self._add_text_group(list_host, 2, "忽略路径关键字", "每行一个路径片段")

        actions = self._make_frame(container, fg=_BG)
        actions.pack(fill="x", pady=(10, 0))

        self._make_button(actions, "重新加载", self.load_from_manager, width=90).pack(side="left")
        self._make_button(actions, "关闭", self.hide, width=72).pack(side="right")
        self._make_button(actions, "保存", self.save_and_apply, width=90).pack(side="right", padx=(0, 8))

    def _make_frame(self, parent: tk.Misc, fg: str) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkFrame(parent, fg_color=fg, corner_radius=_CORNER)
        return tk.Frame(parent, bg=fg, bd=0, highlightthickness=0)

    def _make_label(self, parent: tk.Misc, text: str, font: tuple[str, int, str] | tuple[str, int], color: str) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkLabel(parent, text=text, font=font, text_color=color, anchor="w")
        return tk.Label(parent, text=text, font=font, fg=color, bg=parent.cget("bg"), anchor="w")

    def _make_button(self, parent: tk.Misc, text: str, command: object, width: int = 120) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkButton(
                parent,
                text=text,
                command=command,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                corner_radius=8,
                width=width,
                height=32,
                font=(_FONT, 11),
            )
        return ttk.Button(parent, text=text, command=command, width=max(6, width // 10))

    def _make_entry(self, parent: tk.Misc, textvariable: tk.StringVar) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkEntry(parent, textvariable=textvariable, height=32, font=(_FONT, 11))
        return ttk.Entry(parent, textvariable=textvariable)

    def _make_checkbutton(self, parent: tk.Misc, text: str, variable: tk.BooleanVar) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkCheckBox(parent, text=text, variable=variable, font=(_FONT, 11))
        return ttk.Checkbutton(parent, text=text, variable=variable)

    def _add_entry_row(self, parent: tk.Misc, row: int, label_text: str, variable: tk.StringVar) -> None:
        label = self._make_label(parent, label_text, (_FONT, 11, "bold"), _TEXT_PRIMARY)
        label.grid(row=row, column=0, sticky="w", pady=(4, 4), padx=(0, 12))

        entry = self._make_entry(parent, variable)
        entry.grid(row=row, column=1, sticky="ew", pady=(4, 4))

    def _add_text_group(self, parent: tk.Misc, column: int, title: str, hint: str) -> scrolledtext.ScrolledText:
        card = tk.Frame(parent, bg=_CARD_BG, highlightthickness=0)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0))
        card.grid_rowconfigure(2, weight=1)

        self._make_label(card, title, (_FONT, 12, "bold"), _TEXT_PRIMARY).pack(anchor="w")
        self._make_label(card, hint, (_FONT, 10), _TEXT_SECONDARY).pack(anchor="w", pady=(2, 6))

        text_widget = scrolledtext.ScrolledText(card, height=12, wrap="word", font=(_FONT_MONO, 10))
        text_widget.pack(fill="both", expand=True)
        return text_widget

    def _set_text_widget(self, widget: scrolledtext.ScrolledText, lines: list[str]) -> None:
        widget.delete("1.0", "end")
        widget.insert("1.0", "\n".join(lines))

    def _get_text_lines(self, widget: scrolledtext.ScrolledText) -> list[str]:
        return [line.strip() for line in widget.get("1.0", "end").splitlines() if line.strip()]

    def load_from_manager(self) -> None:
        self.config_manager.reload()
        self.minimum_timing_var.set(str(self.config_manager.minimum_timing_seconds()))
        self.auto_save_var.set(str(self.config_manager.auto_save_seconds()))
        self.idle_timeout_var.set(str(self.config_manager.idle_timeout_seconds()))
        self.export_directory_var.set(self.config_manager.export_directory_raw())
        self.recover_unsaved_var.set(self.config_manager.recover_unsaved_on_startup())
        launch_on_startup = self.config_manager.launch_on_startup()
        if sys.platform == "win32":
            try:
                launch_on_startup = startup_enabled()
            except Exception:
                launch_on_startup = self.config_manager.launch_on_startup()
        self.launch_on_startup_var.set(launch_on_startup)
        self.debug_tracker_var.set(self.config_manager.debug_tracker())
        self._set_text_widget(self.process_text, sorted(self.config_manager.get_list("ignore_process_names")))
        self._set_text_widget(self.title_text, self.config_manager.get_list("ignore_window_title_keywords"))
        self._set_text_widget(self.path_text, self.config_manager.get_list("ignore_exe_path_keywords"))

    def save_and_apply(self) -> None:
        try:
            minimum_timing = max(0.2, float(self.minimum_timing_var.get().strip()))
            auto_save = max(5, int(self.auto_save_var.get().strip()))
            idle_timeout = max(10, int(self.idle_timeout_var.get().strip()))
        except ValueError:
            messagebox.showerror(APP_NAME, "数值格式不正确，请检查输入", parent=self.window)
            return

        updates = {
            "minimum_timing_seconds": minimum_timing,
            "auto_save_seconds": auto_save,
            "idle_timeout_seconds": idle_timeout,
            "recover_unsaved_on_startup": bool(self.recover_unsaved_var.get()),
            "launch_on_startup": bool(self.launch_on_startup_var.get()),
            "debug_tracker": bool(self.debug_tracker_var.get()),
            "export_directory": self.export_directory_var.get().strip() or "exports",
            "ignore_process_names": self._get_text_lines(self.process_text),
            "ignore_window_title_keywords": self._get_text_lines(self.title_text),
            "ignore_exe_path_keywords": self._get_text_lines(self.path_text),
        }

        try:
            self.on_save(updates)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"保存失败：\n{exc}", parent=self.window)
            return

        messagebox.showinfo(APP_NAME, "设置已保存", parent=self.window)
        self.hide()

    def show(self) -> None:
        self.load_from_manager()
        self.window.deiconify()
        self.window.lift()
        self.window.focus_force()

    def hide(self) -> None:
        self.window.withdraw()


class FirstRunWindow:
    def __init__(
        self,
        parent: tk.Misc,
        config_manager: ConfigManager,
        on_apply: object,
        on_skip: object,
        notify: object,
    ) -> None:
        self.parent = parent
        self.config_manager = config_manager
        self.on_apply = on_apply
        self.on_skip = on_skip
        self.notify = notify

        if CUSTOMTKINTER_AVAILABLE:
            self.window = ctk.CTkToplevel(parent)
            self.window.configure(fg_color=_BG)
        else:
            self.window = tk.Toplevel(parent, bg=_BG)

        self.window.title(f"欢迎使用 {APP_NAME}")
        self.window.geometry("580x420")
        self.window.minsize(520, 380)
        self.window.withdraw()
        self.window.protocol("WM_DELETE_WINDOW", self.skip)

        self.launch_on_startup_var = tk.BooleanVar(value=False)
        self.debug_tracker_var = tk.BooleanVar(value=False)
        self.keep_default_ignore_var = tk.BooleanVar(value=True)

        self._build_layout()
        self.load_defaults()

    def _build_layout(self) -> None:
        container = self._make_frame(self.window, fg=_BG)
        container.pack(fill="both", expand=True, padx=20, pady=20)

        card = self._make_frame(container, fg=_CARD_BG)
        card.pack(fill="both", expand=True)

        self._make_label(card, "欢迎使用 WinVibeTime", (_FONT, 18, "bold"), _TEXT_PRIMARY).pack(anchor="w", padx=24, pady=(24, 8))
        self._make_label(
            card,
            "选择你的偏好设置，之后可以随时在托盘菜单中修改",
            (_FONT, 11),
            _TEXT_SECONDARY,
        ).pack(anchor="w", padx=24, pady=(0, 16))

        choices = tk.Frame(card, bg=_CARD_BG, highlightthickness=0)
        choices.pack(fill="x", padx=24, pady=(0, 12))

        self.startup_checkbox = self._make_checkbutton(choices, "开机自动启动", self.launch_on_startup_var)
        self.startup_checkbox.pack(anchor="w", pady=(0, 8))
        self._make_checkbutton(choices, "调试模式", self.debug_tracker_var).pack(anchor="w", pady=(0, 8))
        self._make_checkbutton(choices, "保留默认忽略列表", self.keep_default_ignore_var).pack(anchor="w")

        if sys.platform != "win32":
            try:
                self.startup_checkbox.configure(state="disabled")
            except Exception:
                pass

        tips = self._make_frame(card, fg=_BG)
        tips.pack(fill="x", padx=24, pady=(8, 20))

        self._make_label(
            tips,
            "默认忽略列表会排除系统窗口，让统计结果更清晰",
            (_FONT, 10),
            _TEXT_SECONDARY,
        ).pack(anchor="w", padx=12, pady=10)

        actions = self._make_frame(container, fg=_BG)
        actions.pack(fill="x", pady=(12, 0))

        self._make_button(actions, "稍后设置", self.skip, width=90).pack(side="left")
        self._make_button(actions, "开始使用", self.apply, width=100).pack(side="right")

    def _make_frame(self, parent: tk.Misc, fg: str) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkFrame(parent, fg_color=fg, corner_radius=_CORNER)
        return tk.Frame(parent, bg=fg, bd=0, highlightthickness=0)

    def _make_label(self, parent: tk.Misc, text: str, font: tuple[str, int, str] | tuple[str, int], color: str) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkLabel(parent, text=text, font=font, text_color=color, anchor="w", justify="left")
        return tk.Label(parent, text=text, font=font, fg=color, bg=parent.cget("bg"), anchor="w", justify="left")

    def _make_button(self, parent: tk.Misc, text: str, command: object, width: int = 120) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkButton(
                parent,
                text=text,
                command=command,
                fg_color=_ACCENT,
                hover_color=_ACCENT_HOVER,
                corner_radius=8,
                width=width,
                height=32,
                font=(_FONT, 11),
            )
        return ttk.Button(parent, text=text, command=command, width=max(6, width // 10))

    def _make_checkbutton(self, parent: tk.Misc, text: str, variable: tk.BooleanVar) -> tk.Misc:
        if CUSTOMTKINTER_AVAILABLE:
            return ctk.CTkCheckBox(parent, text=text, variable=variable, font=(_FONT, 11))
        return ttk.Checkbutton(parent, text=text, variable=variable)

    def load_defaults(self) -> None:
        self.config_manager.reload()
        launch_on_startup = self.config_manager.launch_on_startup()
        if sys.platform == "win32":
            try:
                launch_on_startup = startup_enabled()
            except Exception:
                launch_on_startup = self.config_manager.launch_on_startup()

        current_ignore = default_ignore_config()
        keep_default_ignore = all(
            self.config_manager.get_list(key) == current_ignore[key]
            for key in current_ignore
        )

        self.launch_on_startup_var.set(launch_on_startup)
        self.debug_tracker_var.set(self.config_manager.debug_tracker())
        self.keep_default_ignore_var.set(keep_default_ignore)

    def show(self) -> None:
        self.load_defaults()
        self.window.deiconify()
        self.window.transient(self.parent)
        self.window.grab_set()
        self.window.lift()
        self.window.focus_force()

    def hide(self) -> None:
        try:
            self.window.grab_release()
        except Exception:
            pass
        self.window.withdraw()

    def apply(self) -> None:
        updates: dict[str, object] = {
            "first_run_completed": True,
            "launch_on_startup": bool(self.launch_on_startup_var.get()),
            "debug_tracker": bool(self.debug_tracker_var.get()),
        }

        if self.keep_default_ignore_var.get():
            updates.update(default_ignore_config())
        else:
            updates.update(
                {
                    "ignore_process_names": [],
                    "ignore_window_title_keywords": [],
                    "ignore_exe_path_keywords": [],
                }
            )

        try:
            self.on_apply(updates)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"设置失败：\n{exc}", parent=self.window)
            return

        self.hide()
        self.notify(APP_NAME, "偏好已保存，可随时在设置中修改")

    def skip(self) -> None:
        try:
            self.on_skip({"first_run_completed": True})
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"保存失败：\n{exc}", parent=self.window)
            return
        self.hide()
        self.notify(APP_NAME, "已跳过引导，可稍后在设置中修改")


class TrayApp:
    def __init__(self, data_manager: DataManager, tracker: WindowTracker, config_manager: ConfigManager) -> None:
        if not UI_AVAILABLE:
            raise RuntimeError("Tray UI dependencies are not available.")

        self.data_manager = data_manager
        self.tracker = tracker
        self.config_manager = config_manager
        self.statistics_window = StatisticsWindow(data_manager)
        self.settings_window = SettingsWindow(
            self.statistics_window.root,
            config_manager,
            self._persist_and_apply_preferences,
        )
        self.first_run_window = FirstRunWindow(
            self.statistics_window.root,
            config_manager,
            self._persist_and_apply_preferences,
            self._persist_and_apply_preferences,
            self.statistics_window.show_info,
        )

        self._stop_lock = threading.Lock()
        self._stop_requested = False
        self._cleanup_done = False

        self.icon = pystray.Icon(
            APP_NAME,
            self._build_icon_image(),
            APP_NAME,
            menu=pystray.Menu(
                pystray.MenuItem("查看统计", self._on_show_statistics),
                pystray.MenuItem("设置", self._on_show_settings),
                pystray.MenuItem("暂停监控", self._on_pause_requested, enabled=lambda _item: not self.tracker.is_paused()),
                pystray.MenuItem("恢复监控", self._on_resume_requested, enabled=lambda _item: self.tracker.is_paused()),
                pystray.MenuItem("导出今日 CSV", self._on_export_today_csv),
                pystray.MenuItem("退出", self._on_exit_requested),
            ),
        )

    def start(self) -> None:
        self.tracker.start()
        self.icon.run_detached()
        self.statistics_window.root.after(700, self._maybe_show_first_run_window)

    def run(self) -> None:
        try:
            self.statistics_window.run()
        finally:
            self._cleanup_resources()

    def stop(self) -> None:
        with self._stop_lock:
            if self._stop_requested:
                return
            self._stop_requested = True

        try:
            self.icon.stop()
        except Exception:
            pass

        self.tracker.stop()
        self.statistics_window.shutdown()

    def _cleanup_resources(self) -> None:
        with self._stop_lock:
            if self._cleanup_done:
                return
            self._cleanup_done = True

        try:
            self.icon.stop()
        except Exception:
            pass

        self.tracker.stop()
        self.data_manager.close()

    def _on_show_statistics(self, _icon: object, _item: object) -> None:
        self.statistics_window.call_in_ui_thread(self.statistics_window.show)

    def _on_show_settings(self, _icon: object, _item: object) -> None:
        self.statistics_window.call_in_ui_thread(self.settings_window.show)

    def _on_pause_requested(self, _icon: object, _item: object) -> None:
        self.tracker.pause()
        self._refresh_menu()
        self.statistics_window.call_in_ui_thread(self.statistics_window.refresh_view)
        self.statistics_window.show_info(APP_NAME, "监控已暂停")

    def _on_resume_requested(self, _icon: object, _item: object) -> None:
        self.tracker.resume()
        self._refresh_menu()
        self.statistics_window.call_in_ui_thread(self.statistics_window.refresh_view)
        self.statistics_window.show_info(APP_NAME, "监控已恢复")

    def _on_export_today_csv(self, _icon: object, _item: object) -> None:
        try:
            self.tracker.persist_now()
            export_path = self.data_manager.export_today_to_csv(self.config_manager.export_csv_path())
        except Exception as exc:
            self.statistics_window.show_error(APP_NAME, f"导出失败:\n{exc}")
            return

        self.statistics_window.show_info(APP_NAME, f"已导出到：\n{export_path}")

    def _on_exit_requested(self, _icon: object, _item: object) -> None:
        self.stop()

    def _refresh_menu(self) -> None:
        try:
            self.icon.update_menu()
        except Exception:
            pass

    def _persist_and_apply_preferences(self, updates: dict[str, object]) -> None:
        if sys.platform == "win32" and "launch_on_startup" in updates:
            if bool(updates["launch_on_startup"]):
                enable_startup()
            else:
                disable_startup()

        self.config_manager.update(updates)
        self.tracker.apply_runtime_settings(
            interval_seconds=self.config_manager.minimum_timing_seconds(),
            auto_save_seconds=self.config_manager.auto_save_seconds(),
            idle_timeout_seconds=self.config_manager.idle_timeout_seconds(),
            enable_debug=self.config_manager.debug_tracker(),
            ignored_process_names=self.config_manager.ignore_process_names(),
            ignored_window_title_keywords=self.config_manager.ignore_window_title_keywords(),
            ignored_exe_path_keywords=self.config_manager.ignore_exe_path_keywords(),
        )
        self._refresh_menu()
        self.statistics_window.call_in_ui_thread(self.statistics_window.refresh_view)

    def _maybe_show_first_run_window(self) -> None:
        if self.config_manager.first_run_completed():
            return
        self.first_run_window.show()

    def _build_icon_image(self) -> Image.Image:
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        draw.rounded_rectangle((2, 2, size - 2, size - 2), radius=14, fill="#007AFF")
        draw.rounded_rectangle((8, 8, size - 8, size - 8), radius=10, fill="#FFFFFF")

        cx, cy = size // 2, size // 2
        draw.line((cx, 16, cx, cy), fill="#1D1D1F", width=3)
        draw.line((cx, cy, cx + 12, cy + 6), fill="#007AFF", width=3)
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill="#1D1D1F")

        return image
