from __future__ import annotations

import ctypes
import os
import sys
import threading
import time as time_module
from ctypes import wintypes
from datetime import datetime, timedelta

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ModuleNotFoundError:
    psutil = None
    PSUTIL_AVAILABLE = False

if sys.platform == "win32":
    import win32api
    import win32gui
    import win32process
else:
    win32api = None
    win32gui = None
    win32process = None

from .models import (
    AUTO_SAVE_INTERVAL_SECONDS,
    IDLE_TIMEOUT_SECONDS,
    MONITOR_INTERVAL_SECONDS,
    SUSPEND_GAP_THRESHOLD_SECONDS,
    WindowSnapshot,
    WindowUsage,
    format_duration,
    software_key,
)
from .storage import DataManager, split_by_day


LOCKED_PROCESS_NAMES = {"lockapp.exe", "logonui.exe"}

if sys.platform == "win32":
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    DESKTOP_READOBJECTS = 0x0001
    DESKTOP_SWITCHDESKTOP = 0x0100
    UOI_NAME = 2

    class LASTINPUTINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT),
            ("dwTime", wintypes.DWORD),
        ]

    user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    user32.OpenInputDesktop.restype = wintypes.HANDLE
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    user32.GetUserObjectInformationW.argtypes = [
        wintypes.HANDLE,
        wintypes.INT,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetUserObjectInformationW.restype = wintypes.BOOL
    user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
    user32.GetLastInputInfo.restype = wintypes.BOOL
else:
    user32 = None
    DESKTOP_READOBJECTS = 0
    DESKTOP_SWITCHDESKTOP = 0
    UOI_NAME = 0
    LASTINPUTINFO = None


def platform_tick_seconds() -> float:
    if sys.platform == "win32" and win32api is not None:
        try:
            return float(win32api.GetTickCount64()) / 1000.0
        except AttributeError:
            return float(win32api.GetTickCount()) / 1000.0
        except Exception:
            pass
    return time_module.monotonic()


class WindowTracker:
    def __init__(
        self,
        data_manager: DataManager,
        interval_seconds: float = MONITOR_INTERVAL_SECONDS,
        idle_timeout_seconds: int = IDLE_TIMEOUT_SECONDS,
        auto_save_seconds: int = AUTO_SAVE_INTERVAL_SECONDS,
        enable_debug: bool = True,
        simulation_mode: bool = False,
        recover_unsaved_on_startup: bool = True,
        ignored_process_names: set[str] | None = None,
        ignored_window_title_keywords: list[str] | None = None,
        ignored_exe_path_keywords: list[str] | None = None,
    ) -> None:
        self.data_manager = data_manager
        self.interval_seconds = interval_seconds
        self.idle_timeout_seconds = idle_timeout_seconds
        self.auto_save_seconds = auto_save_seconds
        self.enable_debug = enable_debug
        self.simulation_mode = simulation_mode
        self.recover_unsaved_on_startup = recover_unsaved_on_startup
        self.ignored_process_names = {item.lower() for item in (ignored_process_names or set())}
        self.ignored_window_title_keywords = [item.lower() for item in (ignored_window_title_keywords or [])]
        self.ignored_exe_path_keywords = [item.lower() for item in (ignored_exe_path_keywords or [])]

        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

        self.current_day_key = datetime.now().date().isoformat()
        self.window_stats, self.software_totals = self.data_manager.load_runtime_state(
            self.current_day_key,
            recover_from_activity=self.recover_unsaved_on_startup,
        )

        self.current_snapshot: WindowSnapshot | None = None
        self.last_observation_at: datetime | None = None
        self.last_loop_tick: float | None = None
        self.last_runtime_save_at: datetime | None = None
        self.pause_reason_announced: str | None = None
        self.manual_paused = False

        self.simulation_started_tick = platform_tick_seconds()
        self.simulated_windows = [
            {
                "hwnd": 1001,
                "title": "main.py - WinVibeTime - Visual Studio Code",
                "process_name": "Code.exe",
                "exe_path": r"C:\Program Files\Microsoft VS Code\Code.exe",
            },
            {
                "hwnd": 1002,
                "title": "ChatGPT - Google Chrome",
                "process_name": "chrome.exe",
                "exe_path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            },
            {
                "hwnd": 1003,
                "title": "PowerShell",
                "process_name": "powershell.exe",
                "exe_path": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
            },
            {
                "hwnd": 1004,
                "title": "WeChat",
                "process_name": "WeChat.exe",
                "exe_path": r"C:\Program Files\Tencent\WeChat\WeChat.exe",
            },
        ]

    def start(self) -> None:
        if self.thread is not None and self.thread.is_alive():
            return

        self.stop_event.clear()
        mode = "simulation" if self.simulation_mode else "windows"
        print(
            f"[tracker] started mode={mode} interval={self.interval_seconds:.1f}s "
            f"idle_timeout={self.idle_timeout_seconds}s auto_save={self.auto_save_seconds}s",
            flush=True,
        )
        self.thread = threading.Thread(
            target=self._monitor_loop,
            name="WindowTracker",
            daemon=True,
        )
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=self.interval_seconds + 2.0)

        now = datetime.now()
        pause_reason, pause_cutoff = self._current_pause_state(now)
        with self.lock:
            self._bill_current_window_locked(now, pause_cutoff, suspend_gap=False, loop_gap=0.0)
            self._persist_runtime_state_locked(now, force=True)
            self.current_snapshot = None
            self.last_observation_at = None
            self.last_loop_tick = None
            self.pause_reason_announced = None

        if self.enable_debug and pause_reason is not None:
            print(f"[tracker] stopped while paused reason={pause_reason}", flush=True)

    def get_window_stats(self) -> dict[int, WindowUsage]:
        with self.lock:
            return {
                hwnd: WindowUsage(
                    window_key=usage.window_key,
                    hwnd=usage.hwnd,
                    window_title=usage.window_title,
                    process_name=usage.process_name,
                    exe_path=usage.exe_path,
                    active_seconds=usage.active_seconds,
                    first_seen_at=usage.first_seen_at,
                    last_seen_at=usage.last_seen_at,
                )
                for hwnd, usage in self.window_stats.items()
            }

    def get_software_totals(self) -> dict[tuple[str, str], float]:
        with self.lock:
            return dict(self.software_totals)

    def is_paused(self) -> bool:
        with self.lock:
            return self.manual_paused

    def pause(self) -> None:
        now = datetime.now()
        pause_reason, pause_cutoff = self._current_pause_state(now)

        with self.lock:
            if self.manual_paused:
                return

            self._bill_current_window_locked(now, pause_cutoff, suspend_gap=False, loop_gap=0.0)
            self._persist_runtime_state_locked(now, force=True)
            self.manual_paused = True
            self.current_snapshot = None
            self.last_observation_at = now
            self.pause_reason_announced = "manual"

        if self.enable_debug:
            reason_text = pause_reason or "manual"
            print(f"[tracker] manually paused reason={reason_text}", flush=True)

    def resume(self) -> None:
        now = datetime.now()

        with self.lock:
            if not self.manual_paused:
                return

            self.manual_paused = False
            self.current_snapshot = None
            self.last_observation_at = now
            self.last_loop_tick = platform_tick_seconds()
            self.pause_reason_announced = None

        if self.enable_debug:
            print("[tracker] monitoring resumed", flush=True)

    def persist_now(self) -> None:
        now = datetime.now()
        pause_reason, pause_cutoff = self._current_pause_state(now)

        with self.lock:
            self._bill_current_window_locked(now, pause_cutoff, suspend_gap=False, loop_gap=0.0)
            self._persist_runtime_state_locked(now, force=True)

        if self.enable_debug:
            print(f"[tracker] manual persist complete paused={pause_reason is not None}", flush=True)

    def apply_runtime_settings(
        self,
        *,
        interval_seconds: float | None = None,
        auto_save_seconds: int | None = None,
        idle_timeout_seconds: int | None = None,
        enable_debug: bool | None = None,
        ignored_process_names: set[str] | None = None,
        ignored_window_title_keywords: list[str] | None = None,
        ignored_exe_path_keywords: list[str] | None = None,
    ) -> None:
        with self.lock:
            if interval_seconds is not None:
                self.interval_seconds = max(0.2, float(interval_seconds))
            if auto_save_seconds is not None:
                self.auto_save_seconds = max(5, int(auto_save_seconds))
            if idle_timeout_seconds is not None:
                self.idle_timeout_seconds = max(10, int(idle_timeout_seconds))
            if enable_debug is not None:
                self.enable_debug = bool(enable_debug)
            if ignored_process_names is not None:
                self.ignored_process_names = {item.lower() for item in ignored_process_names}
            if ignored_window_title_keywords is not None:
                self.ignored_window_title_keywords = [item.lower() for item in ignored_window_title_keywords]
            if ignored_exe_path_keywords is not None:
                self.ignored_exe_path_keywords = [item.lower() for item in ignored_exe_path_keywords]

            now = datetime.now()
            self.last_observation_at = now
            self.last_loop_tick = platform_tick_seconds()

        if self.enable_debug:
            print(
                f"[tracker] runtime settings updated interval={self.interval_seconds:.1f}s "
                f"idle_timeout={self.idle_timeout_seconds}s auto_save={self.auto_save_seconds}s "
                f"ignored_processes={len(self.ignored_process_names)}",
                flush=True,
            )

    def _monitor_loop(self) -> None:
        while not self.stop_event.is_set():
            loop_started = platform_tick_seconds()
            loop_gap = 0.0 if self.last_loop_tick is None else max(0.0, loop_started - self.last_loop_tick)
            suspend_gap = loop_gap >= max(SUSPEND_GAP_THRESHOLD_SECONDS, self.interval_seconds * 3)
            self.last_loop_tick = loop_started

            now = datetime.now()
            pause_reason, pause_cutoff = self._current_pause_state(now)
            snapshot = None if pause_reason is not None else self.capture_foreground_window()
            self._handle_observation(snapshot, now, pause_reason, pause_cutoff, suspend_gap, loop_gap)

            remaining = self.interval_seconds - (platform_tick_seconds() - loop_started)
            if remaining > 0:
                self.stop_event.wait(remaining)

    def _handle_observation(
        self,
        snapshot: WindowSnapshot | None,
        now: datetime,
        pause_reason: str | None,
        pause_cutoff: datetime | None,
        suspend_gap: bool,
        loop_gap: float,
    ) -> None:
        with self.lock:
            self._bill_current_window_locked(now, pause_cutoff, suspend_gap, loop_gap)

            if suspend_gap and self.enable_debug:
                print(
                    f"[tracker] resume detected gap={loop_gap:.1f}s, skipped standby/lock gap",
                    flush=True,
                )

            if pause_reason is not None:
                self._announce_pause_locked(pause_reason, snapshot)
                self._persist_runtime_state_locked(now)
                return

            self.pause_reason_announced = None

            if snapshot is None:
                if self.current_snapshot is not None and self.enable_debug:
                    print("[tracker] no foreground window, pause current accumulation", flush=True)
                self.current_snapshot = None
                self.last_observation_at = now
                self._persist_runtime_state_locked(now)
                return

            if self.current_snapshot is None or snapshot.hwnd != self.current_snapshot.hwnd:
                self._activate_window_locked(snapshot, now)
                self._persist_runtime_state_locked(now)
                return

            self.current_snapshot.window_title = snapshot.window_title
            self.current_snapshot.process_name = snapshot.process_name
            self.current_snapshot.exe_path = snapshot.exe_path

            self._print_active_debug_locked(self.current_snapshot)
            self._persist_runtime_state_locked(now)

    def _announce_pause_locked(self, pause_reason: str, snapshot: WindowSnapshot | None) -> None:
        if self.pause_reason_announced == pause_reason or not self.enable_debug:
            return

        active = snapshot or self.current_snapshot
        if active is None:
            print(f"[tracker] paused reason={pause_reason}", flush=True)
        else:
            print(
                f"[tracker] paused reason={pause_reason} title={active.window_title!r} "
                f"app={active.process_name} hwnd=0x{active.hwnd:08X}",
                flush=True,
            )
        self.pause_reason_announced = pause_reason

    def _activate_window_locked(self, snapshot: WindowSnapshot, now: datetime) -> None:
        self.current_snapshot = snapshot
        self.last_observation_at = now
        self.pause_reason_announced = None
        self._ensure_window_usage_locked(snapshot, now)

        if self.enable_debug:
            print(
                f"[tracker] focus changed title={snapshot.window_title!r} "
                f"app={snapshot.process_name} hwnd=0x{snapshot.hwnd:08X}",
                flush=True,
            )

    def _bill_current_window_locked(
        self,
        now: datetime,
        pause_cutoff: datetime | None,
        suspend_gap: bool,
        loop_gap: float,
    ) -> None:
        if self.current_snapshot is None or self.last_observation_at is None:
            self.last_observation_at = now
            return

        if suspend_gap:
            self.last_observation_at = now
            return

        interval_start = self.last_observation_at
        billable_end = now

        if pause_cutoff is not None:
            if interval_start >= pause_cutoff:
                self.last_observation_at = now
                return
            if billable_end > pause_cutoff:
                billable_end = pause_cutoff

        if billable_end > interval_start:
            self._record_usage_locked(self.current_snapshot, interval_start, billable_end)

        self.last_observation_at = now

    def _record_usage_locked(
        self,
        snapshot: WindowSnapshot,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        for segment_start, segment_end in split_by_day(started_at, ended_at):
            duration = (segment_end - segment_start).total_seconds()
            if duration <= 0:
                continue

            day_key = segment_start.date().isoformat()
            if day_key != self.current_day_key:
                self._switch_runtime_day_locked(day_key, segment_start)

            usage = self._ensure_window_usage_locked(snapshot, segment_start)
            usage.window_title = snapshot.window_title or usage.window_title
            usage.process_name = snapshot.process_name
            usage.exe_path = snapshot.exe_path
            usage.active_seconds += duration
            usage.last_seen_at = segment_end.isoformat(timespec="seconds")

            app_key = software_key(snapshot.process_name, snapshot.exe_path)
            self.software_totals[app_key] = self.software_totals.get(app_key, 0.0) + duration

            self.data_manager.record_activity(snapshot, segment_start, segment_end)

    def _switch_runtime_day_locked(self, next_day_key: str, boundary: datetime) -> None:
        self.data_manager.save_runtime_state(
            self.window_stats,
            self.software_totals,
            now=boundary,
            day_key=self.current_day_key,
        )
        self.current_day_key = next_day_key
        self.window_stats, self.software_totals = self.data_manager.load_runtime_state(
            next_day_key,
            recover_from_activity=self.recover_unsaved_on_startup,
        )
        self.last_runtime_save_at = boundary

        if self.enable_debug:
            print(f"[tracker] day rollover -> {next_day_key}", flush=True)

    def _persist_runtime_state_locked(self, now: datetime, force: bool = False) -> None:
        if not force:
            if self.last_runtime_save_at is not None:
                elapsed = (now - self.last_runtime_save_at).total_seconds()
                if elapsed < self.auto_save_seconds:
                    return

        self.data_manager.save_runtime_state(
            self.window_stats,
            self.software_totals,
            now=now,
            day_key=self.current_day_key,
        )
        self.last_runtime_save_at = now

        if self.enable_debug:
            print(
                f"[tracker] persisted runtime snapshot day={self.current_day_key} "
                f"windows={len(self.window_stats)} apps={len(self.software_totals)}",
                flush=True,
            )

    def _ensure_window_usage_locked(self, snapshot: WindowSnapshot, now: datetime) -> WindowUsage:
        usage = self.window_stats.get(snapshot.hwnd)
        if usage is None:
            timestamp = now.isoformat(timespec="seconds")
            usage = WindowUsage(
                window_key=snapshot.window_key,
                hwnd=snapshot.hwnd,
                window_title=snapshot.window_title,
                process_name=snapshot.process_name,
                exe_path=snapshot.exe_path,
                first_seen_at=timestamp,
                last_seen_at=timestamp,
            )
            self.window_stats[snapshot.hwnd] = usage
            return usage

        usage.window_key = snapshot.window_key
        usage.window_title = snapshot.window_title
        usage.process_name = snapshot.process_name
        usage.exe_path = snapshot.exe_path
        return usage

    def _print_active_debug_locked(self, snapshot: WindowSnapshot) -> None:
        if not self.enable_debug:
            return

        usage = self.window_stats.get(snapshot.hwnd)
        window_seconds = usage.active_seconds if usage is not None else 0.0
        software_seconds = self.software_totals.get(software_key(snapshot.process_name, snapshot.exe_path), 0.0)
        print(
            f"[tracker] active title={snapshot.window_title!r} "
            f"app={snapshot.process_name} hwnd=0x{snapshot.hwnd:08X} "
            f"window_total={format_duration(window_seconds)} "
            f"software_total={format_duration(software_seconds)}",
            flush=True,
        )

    def _current_pause_state(self, now: datetime) -> tuple[str | None, datetime | None]:
        if self.manual_paused:
            return "manual", now

        if self.simulation_mode or sys.platform != "win32":
            return None, None

        if self._is_workstation_locked():
            idle_seconds = self._get_user_idle_seconds()
            if idle_seconds is None:
                return "locked", now
            last_input_at = now - timedelta(seconds=idle_seconds)
            return "locked", last_input_at

        idle_seconds = self._get_user_idle_seconds()
        if idle_seconds is None or idle_seconds < self.idle_timeout_seconds:
            return None, None

        pause_cutoff = now - timedelta(seconds=idle_seconds - self.idle_timeout_seconds)
        return "idle", pause_cutoff

    def _get_user_idle_seconds(self) -> float | None:
        if sys.platform != "win32" or LASTINPUTINFO is None or win32api is None:
            return None

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if not user32.GetLastInputInfo(ctypes.byref(info)):
            return None

        try:
            tick_ms = int(win32api.GetTickCount()) & 0xFFFFFFFF
        except Exception:
            return None

        elapsed_ms = (tick_ms - int(info.dwTime)) & 0xFFFFFFFF
        return max(0.0, elapsed_ms / 1000.0)

    def _is_workstation_locked(self) -> bool:
        if sys.platform != "win32" or user32 is None:
            return False

        desktop = user32.OpenInputDesktop(
            0,
            False,
            DESKTOP_READOBJECTS | DESKTOP_SWITCHDESKTOP,
        )
        if not desktop:
            return False

        try:
            needed = wintypes.DWORD()
            user32.GetUserObjectInformationW(desktop, UOI_NAME, None, 0, ctypes.byref(needed))
            if needed.value <= 0:
                return False

            buffer = ctypes.create_unicode_buffer(max(needed.value // ctypes.sizeof(ctypes.c_wchar), 64))
            if not user32.GetUserObjectInformationW(
                desktop,
                UOI_NAME,
                buffer,
                ctypes.sizeof(buffer),
                ctypes.byref(needed),
            ):
                return False

            desktop_name = buffer.value.lower()
            return desktop_name not in {"default"}
        finally:
            user32.CloseDesktop(desktop)

    def capture_foreground_window(self) -> WindowSnapshot | None:
        if self.simulation_mode:
            return self._finalize_snapshot(self._simulate_foreground_window())

        if sys.platform != "win32":
            return None

        try:
            hwnd = int(win32gui.GetForegroundWindow())
        except Exception:
            return None

        if hwnd == 0:
            return None

        try:
            if not win32gui.IsWindow(hwnd) or not win32gui.IsWindowVisible(hwnd):
                return None
        except Exception:
            return None

        try:
            _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        except Exception:
            return None

        if process_id == 0 or process_id == os.getpid():
            return None

        title = ""
        try:
            title = win32gui.GetWindowText(hwnd).strip()
        except Exception:
            title = ""

        process_name = f"pid-{process_id}"
        exe_path = ""
        process_created_at = datetime.fromtimestamp(0)

        if PSUTIL_AVAILABLE and psutil is not None:
            try:
                process = psutil.Process(process_id)
                process_name = process.name() or process_name
                exe_path = process.exe() or ""
                process_created_at = datetime.fromtimestamp(process.create_time())
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess, PermissionError, OSError):
                pass

        if process_name.lower() in LOCKED_PROCESS_NAMES:
            return None

        snapshot = WindowSnapshot(
            window_key=str(hwnd),
            hwnd=hwnd,
            process_id=process_id,
            process_name=process_name,
            exe_path=exe_path,
            window_title=title or "(Untitled window)",
            process_created_at=process_created_at,
        )
        return self._finalize_snapshot(snapshot)

    def _simulate_foreground_window(self) -> WindowSnapshot:
        elapsed_seconds = int(platform_tick_seconds() - self.simulation_started_tick)
        window_data = self.simulated_windows[(elapsed_seconds // 7) % len(self.simulated_windows)]

        return WindowSnapshot(
            window_key=str(window_data["hwnd"]),
            hwnd=int(window_data["hwnd"]),
            process_id=int(window_data["hwnd"]),
            process_name=str(window_data["process_name"]),
            exe_path=str(window_data["exe_path"]),
            window_title=str(window_data["title"]),
            process_created_at=datetime.fromtimestamp(0),
        )

    def _finalize_snapshot(self, snapshot: WindowSnapshot | None) -> WindowSnapshot | None:
        if snapshot is None or self._should_ignore_snapshot(snapshot):
            return None
        return snapshot

    def _should_ignore_snapshot(self, snapshot: WindowSnapshot) -> bool:
        process_name = snapshot.process_name.lower()
        window_title = snapshot.window_title.lower()
        exe_path = snapshot.exe_path.lower()

        if process_name in LOCKED_PROCESS_NAMES:
            return True

        if process_name in self.ignored_process_names:
            return True

        if any(keyword and keyword in window_title for keyword in self.ignored_window_title_keywords):
            return True

        if any(keyword and keyword in exe_path for keyword in self.ignored_exe_path_keywords):
            return True

        return False
