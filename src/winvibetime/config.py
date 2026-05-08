from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import AUTO_SAVE_INTERVAL_SECONDS, IDLE_TIMEOUT_SECONDS, MONITOR_INTERVAL_SECONDS
from .storage import app_data_dir


DEFAULT_CONFIG: dict[str, Any] = {
    "first_run_completed": False,
    "minimum_timing_seconds": MONITOR_INTERVAL_SECONDS,
    "auto_save_seconds": AUTO_SAVE_INTERVAL_SECONDS,
    "idle_timeout_seconds": IDLE_TIMEOUT_SECONDS,
    "recover_unsaved_on_startup": True,
    "launch_on_startup": False,
    "debug_tracker": False,
    "export_directory": "exports",
    "ignore_process_names": [
        "explorer.exe",
        "taskmgr.exe",
        "lockapp.exe",
        "logonui.exe",
        "searchhost.exe",
        "startmenuexperiencehost.exe",
        "shellexperiencehost.exe",
    ],
    "ignore_window_title_keywords": [
        "Task Manager",
        "任务管理器",
        "Windows Input Experience",
    ],
    "ignore_exe_path_keywords": [
        "\\Windows\\SystemApps\\",
    ],
}


class ConfigManager:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = self._resolve_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.config = self._load_or_create()

    def _resolve_path(self, path: str | Path | None) -> Path:
        if path is not None:
            return Path(path).expanduser().resolve()

        candidates = [
            Path(sys.argv[0]).resolve().parent / "config.json",
            Path.cwd() / "config.json",
            app_data_dir() / "config.json",
        ]

        for candidate in candidates:
            if candidate.exists():
                return candidate

        for candidate in candidates:
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                return candidate
            except OSError:
                continue

        raise OSError("No writable config.json path available for WinVibeTime.")

    def _load_or_create(self) -> dict[str, Any]:
        if not self.path.exists():
            config = deepcopy(DEFAULT_CONFIG)
            self._write(config)
            return config

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}

        config = deepcopy(DEFAULT_CONFIG)
        if isinstance(raw, dict):
            config.update(raw)

        self._write(config)
        return config

    def _write(self, config: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def save(self) -> None:
        self._write(self.config)

    def reload(self) -> dict[str, Any]:
        self.config = self._load_or_create()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.config)

    def update(self, updates: dict[str, Any]) -> dict[str, Any]:
        merged = deepcopy(DEFAULT_CONFIG)
        merged.update(self.config)
        merged.update(updates)
        self.config = merged
        self._write(self.config)
        return self.snapshot()

    def get_float(self, key: str) -> float:
        value = self.config.get(key, DEFAULT_CONFIG[key])
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(DEFAULT_CONFIG[key])

    def get_int(self, key: str) -> int:
        value = self.config.get(key, DEFAULT_CONFIG[key])
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(DEFAULT_CONFIG[key])

    def get_bool(self, key: str) -> bool:
        value = self.config.get(key, DEFAULT_CONFIG[key])
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def get_list(self, key: str) -> list[str]:
        value = self.config.get(key, DEFAULT_CONFIG[key])
        if not isinstance(value, list):
            return list(DEFAULT_CONFIG[key])
        return [str(item) for item in value if str(item).strip()]

    def minimum_timing_seconds(self) -> float:
        return max(0.2, self.get_float("minimum_timing_seconds"))

    def first_run_completed(self) -> bool:
        return self.get_bool("first_run_completed")

    def auto_save_seconds(self) -> int:
        return max(5, self.get_int("auto_save_seconds"))

    def idle_timeout_seconds(self) -> int:
        return max(10, self.get_int("idle_timeout_seconds"))

    def recover_unsaved_on_startup(self) -> bool:
        return self.get_bool("recover_unsaved_on_startup")

    def launch_on_startup(self) -> bool:
        return self.get_bool("launch_on_startup")

    def debug_tracker(self) -> bool:
        return self.get_bool("debug_tracker")

    def ignore_process_names(self) -> set[str]:
        return {item.lower() for item in self.get_list("ignore_process_names")}

    def ignore_window_title_keywords(self) -> list[str]:
        return [item.lower() for item in self.get_list("ignore_window_title_keywords")]

    def ignore_exe_path_keywords(self) -> list[str]:
        return [item.lower() for item in self.get_list("ignore_exe_path_keywords")]

    def export_directory(self) -> Path:
        raw = str(self.config.get("export_directory", DEFAULT_CONFIG["export_directory"]))
        path = Path(raw)
        if not path.is_absolute():
            path = self.path.parent / path
        path.mkdir(parents=True, exist_ok=True)
        return path

    def export_directory_raw(self) -> str:
        return str(self.config.get("export_directory", DEFAULT_CONFIG["export_directory"]))

    def export_csv_path(self) -> Path:
        today = datetime.now().date().isoformat()
        return self.export_directory() / f"winvibetime_{today}.csv"
