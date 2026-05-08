from __future__ import annotations

import csv
import os
import sqlite3
import threading
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Iterable

from .models import APP_NAME, DB_NAME, WindowSnapshot, WindowUsage, format_duration


def app_data_dir() -> Path:
    candidates: list[Path] = []

    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / APP_NAME)

    candidates.append(Path.home() / ".winvibetime" / APP_NAME)
    candidates.append(Path.cwd() / "data" / APP_NAME)

    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except OSError:
            continue

    raise OSError("No writable app data directory available for WinVibeTime.")


def database_path() -> Path:
    return app_data_dir() / DB_NAME


def split_by_day(started_at: datetime, ended_at: datetime) -> Iterable[tuple[datetime, datetime]]:
    cursor = started_at
    while cursor.date() < ended_at.date():
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min)
        yield cursor, next_midnight
        cursor = next_midnight
    yield cursor, ended_at


class DataManager:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or database_path()
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._setup()

    def _setup(self) -> None:
        with self.lock:
            self.conn.executescript(
                """
                PRAGMA journal_mode = WAL;
                PRAGMA synchronous = NORMAL;

                CREATE TABLE IF NOT EXISTS window_registry (
                    window_key TEXT PRIMARY KEY,
                    hwnd INTEGER NOT NULL,
                    process_id INTEGER NOT NULL,
                    process_name TEXT NOT NULL,
                    exe_path TEXT NOT NULL,
                    process_created_at TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_window_title TEXT NOT NULL,
                    total_seconds REAL NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS activity_slices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    day_key TEXT NOT NULL,
                    window_key TEXT NOT NULL,
                    hwnd INTEGER NOT NULL,
                    process_id INTEGER NOT NULL,
                    process_name TEXT NOT NULL,
                    exe_path TEXT NOT NULL,
                    window_title TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT NOT NULL,
                    duration_seconds REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_activity_day_key
                ON activity_slices(day_key);

                CREATE INDEX IF NOT EXISTS idx_activity_process_day
                ON activity_slices(process_name, day_key);

                CREATE INDEX IF NOT EXISTS idx_activity_window_day
                ON activity_slices(window_key, day_key);

                CREATE TABLE IF NOT EXISTS runtime_window_totals (
                    day_key TEXT NOT NULL,
                    process_name TEXT NOT NULL,
                    exe_path TEXT NOT NULL,
                    window_key TEXT NOT NULL,
                    hwnd INTEGER NOT NULL,
                    window_title TEXT NOT NULL,
                    total_seconds REAL NOT NULL DEFAULT 0,
                    first_seen_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    PRIMARY KEY(day_key, window_key)
                );

                CREATE INDEX IF NOT EXISTS idx_runtime_window_day_process
                ON runtime_window_totals(day_key, process_name);

                CREATE TABLE IF NOT EXISTS runtime_app_totals (
                    day_key TEXT NOT NULL,
                    process_name TEXT NOT NULL,
                    exe_path TEXT NOT NULL,
                    total_seconds REAL NOT NULL DEFAULT 0,
                    last_updated TEXT NOT NULL,
                    PRIMARY KEY(day_key, process_name, exe_path)
                );

                CREATE INDEX IF NOT EXISTS idx_runtime_app_day_process
                ON runtime_app_totals(day_key, process_name);
                """
            )
            self.conn.commit()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    def record_activity(
        self,
        snapshot: WindowSnapshot,
        started_at: datetime,
        ended_at: datetime,
    ) -> None:
        if ended_at <= started_at:
            return

        with self.lock:
            with self.conn:
                for segment_start, segment_end in split_by_day(started_at, ended_at):
                    duration = (segment_end - segment_start).total_seconds()
                    if duration <= 0:
                        continue

                    started_text = segment_start.isoformat(timespec="seconds")
                    ended_text = segment_end.isoformat(timespec="seconds")
                    day_key = segment_start.date().isoformat()
                    title = snapshot.window_title or "(Untitled window)"

                    self.conn.execute(
                        """
                        INSERT INTO activity_slices (
                            day_key,
                            window_key,
                            hwnd,
                            process_id,
                            process_name,
                            exe_path,
                            window_title,
                            started_at,
                            ended_at,
                            duration_seconds
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            day_key,
                            snapshot.window_key,
                            snapshot.hwnd,
                            snapshot.process_id,
                            snapshot.process_name,
                            snapshot.exe_path,
                            title,
                            started_text,
                            ended_text,
                            duration,
                        ),
                    )

                    self.conn.execute(
                        """
                        INSERT INTO window_registry (
                            window_key,
                            hwnd,
                            process_id,
                            process_name,
                            exe_path,
                            process_created_at,
                            first_seen_at,
                            last_seen_at,
                            last_window_title,
                            total_seconds
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(window_key) DO UPDATE SET
                            last_seen_at = excluded.last_seen_at,
                            last_window_title = excluded.last_window_title,
                            total_seconds = window_registry.total_seconds + excluded.total_seconds
                        """,
                        (
                            snapshot.window_key,
                            snapshot.hwnd,
                            snapshot.process_id,
                            snapshot.process_name,
                            snapshot.exe_path,
                            snapshot.process_created_at.isoformat(timespec="seconds"),
                            started_text,
                            ended_text,
                            title,
                            duration,
                        ),
                    )

    def save_runtime_state(
        self,
        window_stats: dict[int, WindowUsage],
        software_totals: dict[tuple[str, str], float],
        now: datetime | None = None,
        day_key: str | None = None,
    ) -> None:
        saved_at = now or datetime.now()
        resolved_day_key = day_key or saved_at.date().isoformat()
        saved_text = saved_at.isoformat(timespec="seconds")

        window_rows = [
            (
                resolved_day_key,
                usage.process_name,
                usage.exe_path,
                usage.window_key,
                usage.hwnd,
                usage.window_title or "(Untitled window)",
                float(usage.active_seconds),
                usage.first_seen_at or saved_text,
                usage.last_seen_at or saved_text,
            )
            for usage in window_stats.values()
            if usage.active_seconds > 0
        ]
        app_rows = [
            (
                resolved_day_key,
                process_name,
                exe_path,
                float(total_seconds),
                saved_text,
            )
            for (process_name, exe_path), total_seconds in software_totals.items()
            if total_seconds > 0
        ]

        with self.lock:
            with self.conn:
                if window_rows:
                    self.conn.executemany(
                        """
                        INSERT INTO runtime_window_totals (
                            day_key,
                            process_name,
                            exe_path,
                            window_key,
                            hwnd,
                            window_title,
                            total_seconds,
                            first_seen_at,
                            last_updated
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(day_key, window_key) DO UPDATE SET
                            process_name = excluded.process_name,
                            exe_path = excluded.exe_path,
                            hwnd = excluded.hwnd,
                            window_title = excluded.window_title,
                            total_seconds = MAX(runtime_window_totals.total_seconds, excluded.total_seconds),
                            first_seen_at = MIN(runtime_window_totals.first_seen_at, excluded.first_seen_at),
                            last_updated = excluded.last_updated
                        """,
                        window_rows,
                    )

                if app_rows:
                    self.conn.executemany(
                        """
                        INSERT INTO runtime_app_totals (
                            day_key,
                            process_name,
                            exe_path,
                            total_seconds,
                            last_updated
                        )
                        VALUES (?, ?, ?, ?, ?)
                        ON CONFLICT(day_key, process_name, exe_path) DO UPDATE SET
                            total_seconds = MAX(runtime_app_totals.total_seconds, excluded.total_seconds),
                            last_updated = excluded.last_updated
                        """,
                        app_rows,
                    )

    def load_runtime_state(
        self,
        day_key: str | None = None,
        recover_from_activity: bool = True,
    ) -> tuple[dict[int, WindowUsage], dict[tuple[str, str], float]]:
        resolved_day_key = day_key or datetime.now().date().isoformat()

        with self.lock:
            window_rows = self.conn.execute(
                """
                SELECT
                    window_key,
                    hwnd,
                    process_name,
                    exe_path,
                    window_title,
                    total_seconds,
                    first_seen_at,
                    last_updated
                FROM runtime_window_totals
                WHERE day_key = ?
                ORDER BY total_seconds DESC, last_updated DESC
                """,
                (resolved_day_key,),
            ).fetchall()
            app_rows = self.conn.execute(
                """
                SELECT
                    process_name,
                    exe_path,
                    total_seconds
                FROM runtime_app_totals
                WHERE day_key = ?
                ORDER BY total_seconds DESC, process_name COLLATE NOCASE
                """,
                (resolved_day_key,),
            ).fetchall()

        windows = {
            int(row["hwnd"]): WindowUsage(
                window_key=row["window_key"],
                hwnd=int(row["hwnd"]),
                window_title=row["window_title"] or "(Untitled window)",
                process_name=row["process_name"],
                exe_path=row["exe_path"] or "",
                active_seconds=float(row["total_seconds"] or 0),
                first_seen_at=row["first_seen_at"] or "",
                last_seen_at=row["last_updated"] or "",
            )
            for row in window_rows
        }
        software = {
            (row["process_name"], row["exe_path"] or ""): float(row["total_seconds"] or 0)
            for row in app_rows
        }

        if recover_from_activity:
            recovered_windows, recovered_software = self._recover_state_from_activity_slices(resolved_day_key)
            for hwnd, recovered_usage in recovered_windows.items():
                current_usage = windows.get(hwnd)
                if current_usage is None or recovered_usage.active_seconds > current_usage.active_seconds:
                    windows[hwnd] = recovered_usage

            for app_key, recovered_seconds in recovered_software.items():
                software[app_key] = max(software.get(app_key, 0.0), recovered_seconds)

        return windows, software

    def get_today_stats(self) -> dict[str, object]:
        day_key = datetime.now().date().isoformat()
        app_rows = self._fetch_runtime_app_rows(day_key, day_key)
        window_rows = self._fetch_runtime_window_rows(day_key, day_key)

        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for row in app_rows:
            grouped[(row["process_name"], row["exe_path"])] = {
                "app_name": row["process_name"],
                "exe_path": row["exe_path"] or "",
                "total_seconds": float(row["total_seconds"] or 0),
                "windows": [],
            }

        for row in window_rows:
            app_key = (row["process_name"], row["exe_path"] or "")
            app_bucket = grouped.setdefault(
                app_key,
                {
                    "app_name": row["process_name"],
                    "exe_path": row["exe_path"] or "",
                    "total_seconds": 0.0,
                    "windows": [],
                },
            )
            app_bucket["windows"].append(
                {
                    "window_title": row["window_title"] or "(Untitled window)",
                    "hwnd": int(row["hwnd"]),
                    "total_seconds": float(row["total_seconds"] or 0),
                    "last_updated": row["last_updated"] or "",
                }
            )

        apps = sorted(
            grouped.values(),
            key=lambda item: float(item["total_seconds"]),
            reverse=True,
        )
        return {
            "date": day_key,
            "apps": apps,
            "total_seconds": sum(float(item["total_seconds"]) for item in apps),
        }

    def get_app_total(self, app_name: str) -> float:
        with self.lock:
            row = self.conn.execute(
                """
                SELECT COALESCE(SUM(total_seconds), 0) AS total_seconds
                FROM runtime_app_totals
                WHERE process_name = ?
                """,
                (app_name,),
            ).fetchone()
        if row is None:
            return 0.0
        return float(row["total_seconds"] or 0)

    def export_today_to_csv(self, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        stats = self.get_today_stats()

        with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "date",
                    "scope",
                    "app_name",
                    "exe_path",
                    "window_title",
                    "hwnd",
                    "total_seconds",
                    "formatted_duration",
                    "last_updated",
                ]
            )

            for app in stats["apps"]:
                writer.writerow(
                    [
                        stats["date"],
                        "app",
                        app["app_name"],
                        app["exe_path"],
                        "",
                        "",
                        app["total_seconds"],
                        format_duration(float(app["total_seconds"])),
                        "",
                    ]
                )

                for window in app["windows"]:
                    writer.writerow(
                        [
                            stats["date"],
                            "window",
                            app["app_name"],
                            app["exe_path"],
                            window["window_title"],
                            f"0x{int(window['hwnd']):08X}",
                            window["total_seconds"],
                            format_duration(float(window["total_seconds"])),
                            window["last_updated"],
                        ]
                    )

        return output_path

    def _scope_sql(self, range_name: str) -> tuple[str, list[str]]:
        today = datetime.now().date()
        if range_name == "today":
            return "day_key = ?", [today.isoformat()]

        week_start = today - timedelta(days=today.weekday())
        return "day_key BETWEEN ? AND ?", [week_start.isoformat(), today.isoformat()]

    def fetch_software_totals(self, range_name: str) -> list[sqlite3.Row]:
        where_sql, params = self._scope_sql(range_name)
        with self.lock:
            cursor = self.conn.execute(
                f"""
                SELECT
                    process_name,
                    exe_path,
                    COUNT(DISTINCT window_key) AS window_count,
                    SUM(duration_seconds) AS total_seconds
                FROM activity_slices
                WHERE {where_sql}
                GROUP BY process_name, exe_path
                ORDER BY total_seconds DESC, process_name COLLATE NOCASE
                """,
                params,
            )
            return cursor.fetchall()

    def fetch_window_details(
        self,
        range_name: str,
        process_name: str | None = None,
        exe_path: str | None = None,
    ) -> list[sqlite3.Row]:
        where_sql, params = self._scope_sql(range_name)
        filters = [where_sql]

        if process_name is not None and exe_path is not None:
            filters.append("process_name = ?")
            filters.append("exe_path = ?")
            params.extend([process_name, exe_path])

        filtered_sql = " AND ".join(filters)
        with self.lock:
            cursor = self.conn.execute(
                f"""
                WITH scoped AS (
                    SELECT *
                    FROM activity_slices
                    WHERE {filtered_sql}
                ),
                window_totals AS (
                    SELECT
                        window_key,
                        hwnd,
                        process_name,
                        exe_path,
                        MIN(started_at) AS first_active_at,
                        SUM(duration_seconds) AS total_seconds
                    FROM scoped
                    GROUP BY window_key, hwnd, process_name, exe_path
                )
                SELECT
                    wt.process_name,
                    wt.exe_path,
                    wt.hwnd,
                    wt.first_active_at,
                    wt.total_seconds,
                    COALESCE(
                        (
                            SELECT s.window_title
                            FROM scoped s
                            WHERE s.window_key = wt.window_key
                            ORDER BY s.started_at DESC
                            LIMIT 1
                        ),
                        "(Untitled window)"
                    ) AS window_title
                FROM window_totals wt
                ORDER BY wt.total_seconds DESC, wt.first_active_at ASC
                """,
                params,
            )
            return cursor.fetchall()

    def fetch_software_totals_for_day(self, day_key: str) -> list[sqlite3.Row]:
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT
                    process_name,
                    exe_path,
                    COUNT(DISTINCT window_key) AS window_count,
                    SUM(duration_seconds) AS total_seconds
                FROM activity_slices
                WHERE day_key = ?
                GROUP BY process_name, exe_path
                ORDER BY total_seconds DESC, process_name COLLATE NOCASE
                """,
                (day_key,),
            )
            return cursor.fetchall()

    def fetch_window_details_for_day(
        self,
        day_key: str,
        process_name: str | None = None,
        exe_path: str | None = None,
    ) -> list[sqlite3.Row]:
        params = [day_key]
        filters = ["day_key = ?"]

        if process_name is not None and exe_path is not None:
            filters.append("process_name = ?")
            filters.append("exe_path = ?")
            params.extend([process_name, exe_path])

        filtered_sql = " AND ".join(filters)
        with self.lock:
            cursor = self.conn.execute(
                f"""
                WITH scoped AS (
                    SELECT *
                    FROM activity_slices
                    WHERE {filtered_sql}
                ),
                window_totals AS (
                    SELECT
                        window_key,
                        hwnd,
                        process_name,
                        exe_path,
                        MIN(started_at) AS first_active_at,
                        SUM(duration_seconds) AS total_seconds
                    FROM scoped
                    GROUP BY window_key, hwnd, process_name, exe_path
                )
                SELECT
                    wt.process_name,
                    wt.exe_path,
                    wt.hwnd,
                    wt.first_active_at,
                    wt.total_seconds,
                    COALESCE(
                        (
                            SELECT s.window_title
                            FROM scoped s
                            WHERE s.window_key = wt.window_key
                            ORDER BY s.started_at DESC
                            LIMIT 1
                        ),
                        "(Untitled window)"
                    ) AS window_title
                FROM window_totals wt
                ORDER BY wt.total_seconds DESC, wt.first_active_at ASC
                """,
                params,
            )
            return cursor.fetchall()

    def fetch_daily_totals(self, day_from: str, day_to: str) -> list[sqlite3.Row]:
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT
                    day_key,
                    SUM(duration_seconds) AS total_seconds,
                    COUNT(DISTINCT process_name || '|' || exe_path) AS app_count,
                    COUNT(DISTINCT window_key) AS window_count
                FROM activity_slices
                WHERE day_key BETWEEN ? AND ?
                GROUP BY day_key
                ORDER BY day_key ASC
                """,
                (day_from, day_to),
            )
            return cursor.fetchall()

    def get_day_stats(self, day_key: str) -> dict[str, object]:
        app_rows = self.fetch_software_totals_for_day(day_key)
        window_rows = self.fetch_window_details_for_day(day_key)

        grouped: dict[tuple[str, str], dict[str, object]] = {}
        for row in app_rows:
            grouped[(row["process_name"], row["exe_path"] or "")] = {
                "app_name": row["process_name"],
                "exe_path": row["exe_path"] or "",
                "total_seconds": float(row["total_seconds"] or 0),
                "windows": [],
            }

        for row in window_rows:
            app_key = (row["process_name"], row["exe_path"] or "")
            app_bucket = grouped.setdefault(
                app_key,
                {
                    "app_name": row["process_name"],
                    "exe_path": row["exe_path"] or "",
                    "total_seconds": 0.0,
                    "windows": [],
                },
            )
            app_bucket["windows"].append(
                {
                    "window_title": row["window_title"] or "(Untitled window)",
                    "hwnd": int(row["hwnd"]),
                    "total_seconds": float(row["total_seconds"] or 0),
                    "first_active_at": row["first_active_at"] or "",
                }
            )

        apps = sorted(grouped.values(), key=lambda item: float(item["total_seconds"]), reverse=True)
        return {
            "date": day_key,
            "apps": apps,
            "total_seconds": sum(float(item["total_seconds"]) for item in apps),
        }

    def _fetch_runtime_app_rows(self, day_from: str, day_to: str) -> list[sqlite3.Row]:
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT
                    process_name,
                    exe_path,
                    SUM(total_seconds) AS total_seconds,
                    MAX(last_updated) AS last_updated
                FROM runtime_app_totals
                WHERE day_key BETWEEN ? AND ?
                GROUP BY process_name, exe_path
                ORDER BY total_seconds DESC, process_name COLLATE NOCASE
                """,
                (day_from, day_to),
            )
            return cursor.fetchall()

    def _fetch_runtime_window_rows(self, day_from: str, day_to: str) -> list[sqlite3.Row]:
        with self.lock:
            cursor = self.conn.execute(
                """
                SELECT
                    process_name,
                    exe_path,
                    window_key,
                    hwnd,
                    window_title,
                    SUM(total_seconds) AS total_seconds,
                    MIN(first_seen_at) AS first_seen_at,
                    MAX(last_updated) AS last_updated
                FROM runtime_window_totals
                WHERE day_key BETWEEN ? AND ?
                GROUP BY process_name, exe_path, window_key, hwnd, window_title
                ORDER BY total_seconds DESC, last_updated DESC
                """,
                (day_from, day_to),
            )
            return cursor.fetchall()

    def _recover_state_from_activity_slices(
        self,
        day_key: str,
    ) -> tuple[dict[int, WindowUsage], dict[tuple[str, str], float]]:
        with self.lock:
            window_rows = self.conn.execute(
                """
                WITH day_scoped AS (
                    SELECT *
                    FROM activity_slices
                    WHERE day_key = ?
                ),
                window_totals AS (
                    SELECT
                        window_key,
                        hwnd,
                        process_name,
                        exe_path,
                        MIN(started_at) AS first_seen_at,
                        MAX(ended_at) AS last_seen_at,
                        SUM(duration_seconds) AS total_seconds
                    FROM day_scoped
                    GROUP BY window_key, hwnd, process_name, exe_path
                )
                SELECT
                    wt.window_key,
                    wt.hwnd,
                    wt.process_name,
                    wt.exe_path,
                    wt.first_seen_at,
                    wt.last_seen_at,
                    wt.total_seconds,
                    COALESCE(
                        (
                            SELECT s.window_title
                            FROM day_scoped s
                            WHERE s.window_key = wt.window_key
                            ORDER BY s.ended_at DESC
                            LIMIT 1
                        ),
                        "(Untitled window)"
                    ) AS window_title
                FROM window_totals wt
                ORDER BY wt.total_seconds DESC
                """,
                (day_key,),
            ).fetchall()

            app_rows = self.conn.execute(
                """
                SELECT
                    process_name,
                    exe_path,
                    SUM(duration_seconds) AS total_seconds
                FROM activity_slices
                WHERE day_key = ?
                GROUP BY process_name, exe_path
                """,
                (day_key,),
            ).fetchall()

        windows = {
            int(row["hwnd"]): WindowUsage(
                window_key=row["window_key"],
                hwnd=int(row["hwnd"]),
                window_title=row["window_title"] or "(Untitled window)",
                process_name=row["process_name"],
                exe_path=row["exe_path"] or "",
                active_seconds=float(row["total_seconds"] or 0),
                first_seen_at=row["first_seen_at"] or "",
                last_seen_at=row["last_seen_at"] or "",
            )
            for row in window_rows
        }
        software = {
            (row["process_name"], row["exe_path"] or ""): float(row["total_seconds"] or 0)
            for row in app_rows
        }
        return windows, software
