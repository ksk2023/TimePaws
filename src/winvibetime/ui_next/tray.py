"""System tray integration — same interface as the old TrayApp."""

from __future__ import annotations

import sys
import threading

from . import design_tokens as T
from .main_window import StatisticsWindow
from .settings_window import FirstRunWindow, SettingsWindow
from ..config import ConfigManager
from ..models import APP_NAME
from ..storage import DataManager
from ..system_integration import disable_startup, enable_startup
from ..tracker import WindowTracker

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

UI_AVAILABLE = PYSTRAY_AVAILABLE and PIL_AVAILABLE


class TrayApp:
    def __init__(
        self,
        data_manager: DataManager,
        tracker: WindowTracker,
        config_manager: ConfigManager,
    ) -> None:
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
                pystray.MenuItem(
                    "暂停监控", self._on_pause_requested,
                    enabled=lambda _item: not self.tracker.is_paused(),
                ),
                pystray.MenuItem(
                    "恢复监控", self._on_resume_requested,
                    enabled=lambda _item: self.tracker.is_paused(),
                ),
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
            export_path = self.data_manager.export_today_to_csv(
                self.config_manager.export_csv_path(),
            )
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

        # Dark-themed icon
        draw.rounded_rectangle((2, 2, size - 2, size - 2), radius=14, fill="#0A84FF")
        draw.rounded_rectangle((8, 8, size - 8, size - 8), radius=10, fill="#1C1C1E")

        cx, cy = size // 2, size // 2
        draw.line((cx, 16, cx, cy), fill="#F5F5F7", width=3)
        draw.line((cx, cy, cx + 12, cy + 6), fill="#0A84FF", width=3)
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill="#F5F5F7")

        return image
