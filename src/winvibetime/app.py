from __future__ import annotations

import argparse
import ctypes
import sys
import time as time_module

from .models import APP_NAME
from .config import ConfigManager
from .single_instance import SingleInstanceGuard
from .storage import DataManager
from .tracker import WindowTracker
from .ui_next.tray import TrayApp, UI_AVAILABLE


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="WinVibeTime foreground window tracker")
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.json. Defaults to the project root or app data directory.",
    )
    parser.add_argument(
        "--debug-tracker",
        action="store_true",
        default=None,
        help="Print tracker activity to stdout. On non-Windows, this runs simulated window data.",
    )
    parser.add_argument(
        "--no-ui",
        action="store_true",
        help="Run the tracker without tray and statistics window.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=None,
        help="Foreground polling interval and minimum billing granularity in seconds.",
    )
    parser.add_argument(
        "--idle-seconds",
        type=int,
        default=None,
        help="Pause timing after this many seconds without user input.",
    )
    parser.add_argument(
        "--save-seconds",
        type=int,
        default=None,
        help="Persist runtime totals every N seconds.",
    )
    return parser.parse_args(argv)


def resolve_runtime_options(config_manager: ConfigManager, args: argparse.Namespace) -> dict[str, object]:
    interval_seconds = (
        args.interval_seconds
        if args.interval_seconds is not None
        else config_manager.minimum_timing_seconds()
    )
    idle_timeout_seconds = (
        args.idle_seconds
        if args.idle_seconds is not None
        else config_manager.idle_timeout_seconds()
    )
    auto_save_seconds = (
        args.save_seconds
        if args.save_seconds is not None
        else config_manager.auto_save_seconds()
    )
    enable_debug = config_manager.debug_tracker() if args.debug_tracker is None else args.debug_tracker

    return {
        "interval_seconds": max(0.2, float(interval_seconds)),
        "idle_timeout_seconds": max(10, int(idle_timeout_seconds)),
        "auto_save_seconds": max(5, int(auto_save_seconds)),
        "enable_debug": bool(enable_debug),
        "recover_unsaved_on_startup": config_manager.recover_unsaved_on_startup(),
        "ignored_process_names": config_manager.ignore_process_names(),
        "ignored_window_title_keywords": config_manager.ignore_window_title_keywords(),
        "ignored_exe_path_keywords": config_manager.ignore_exe_path_keywords(),
    }


def build_tracker(
    data_manager: DataManager,
    config_manager: ConfigManager,
    args: argparse.Namespace,
    simulation_mode: bool,
) -> WindowTracker:
    options = resolve_runtime_options(config_manager, args)
    enable_debug = bool(options.pop("enable_debug"))

    if simulation_mode:
        enable_debug = True

    return WindowTracker(
        data_manager,
        simulation_mode=simulation_mode,
        enable_debug=enable_debug,
        **options,
    )


def run_headless_tracker(args: argparse.Namespace, config_manager: ConfigManager) -> int:
    simulation_mode = sys.platform != "win32"
    data_manager = DataManager()
    tracker = build_tracker(data_manager, config_manager, args, simulation_mode=simulation_mode)

    tracker.start()
    print(
        f"[tracker] headless mode running config={config_manager.path}, press Ctrl+C to stop",
        flush=True,
    )

    try:
        while True:
            time_module.sleep(1.0)
    except KeyboardInterrupt:
        print("\n[tracker] stopping...", flush=True)
    finally:
        tracker.stop()
        data_manager.close()

    return 0


def run_tray_app(args: argparse.Namespace, config_manager: ConfigManager) -> int:
    data_manager = DataManager()
    tracker = build_tracker(data_manager, config_manager, args, simulation_mode=False)
    tray_app = TrayApp(data_manager, tracker, config_manager)
    tray_app.start()
    tray_app.run()
    return 0


def notify_already_running(args: argparse.Namespace) -> None:
    message = f"{APP_NAME} 已在运行。请先退出现有实例。"
    if sys.platform == "win32" and not args.no_ui:
        try:
            ctypes.windll.user32.MessageBoxW(None, message, APP_NAME, 0x40)
            return
        except Exception:
            pass
    print(f"[{APP_NAME}] {message}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    config_manager = ConfigManager(args.config)
    instance_guard = SingleInstanceGuard(APP_NAME)

    if not instance_guard.acquire():
        notify_already_running(args)
        return 1

    try:
        if sys.platform != "win32":
            if args.debug_tracker is None:
                print("[WinVibeTime] non-Windows platform detected, starting simulated tracker debug mode.")
                args.debug_tracker = True
            args.no_ui = True
            return run_headless_tracker(args, config_manager)

        if args.no_ui:
            return run_headless_tracker(args, config_manager)

        if not UI_AVAILABLE:
            print(
                "[WinVibeTime] UI mode requires tkinter, pystray, Pillow, and matplotlib. "
                "Install requirements or run with --no-ui."
            )
            return 1

        return run_tray_app(args, config_manager)
    finally:
        instance_guard.release()
