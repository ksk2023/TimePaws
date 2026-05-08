from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


APP_NAME = "WinVibeTime"
DB_NAME = "winvibetime.db"

MONITOR_INTERVAL_SECONDS = 1.0
AUTO_SAVE_INTERVAL_SECONDS = 30
IDLE_TIMEOUT_SECONDS = 60
SUSPEND_GAP_THRESHOLD_SECONDS = 5.0


@dataclass
class WindowSnapshot:
    window_key: str
    hwnd: int
    process_id: int
    process_name: str
    exe_path: str
    window_title: str
    process_created_at: datetime


@dataclass
class WindowUsage:
    window_key: str
    hwnd: int
    window_title: str
    process_name: str
    exe_path: str
    active_seconds: float = 0.0
    first_seen_at: str = ""
    last_seen_at: str = ""


def software_key(process_name: str, exe_path: str) -> tuple[str, str]:
    return process_name, exe_path or ""


def format_duration(total_seconds: float) -> str:
    seconds = max(0, int(round(total_seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def format_datetime(value: str) -> str:
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    return parsed.strftime("%m-%d %H:%M:%S")
