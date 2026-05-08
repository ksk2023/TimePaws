"""
WinVibeTime Web Dashboard — Flask-based web UI.

Usage:
    python web_app.py [--port 5000] [--db path/to/database.db]

Provides a responsive web interface for viewing time tracking statistics,
reading from the same SQLite database as the desktop app.
"""

from __future__ import annotations

import argparse
import calendar
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template, request

# Allow importing from src/
sys.path.insert(0, str(Path(__file__).parent / "src"))

from winvibetime.storage import DataManager

app = Flask(__name__, template_folder="templates", static_folder="static")
data_manager: DataManager | None = None


def get_dm() -> DataManager:
    global data_manager
    if data_manager is None:
        db_path = app.config.get("DB_PATH")
        data_manager = DataManager(Path(db_path) if db_path else None)
    return data_manager


# ─── Helper ─────────────────────────────────────────────────────────────────

def _format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _compact_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, _ = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m"
    return f"{seconds}s"


def _serialize_software_rows(rows) -> list[dict]:
    return [
        {
            "process_name": str(r["process_name"]),
            "exe_path": str(r["exe_path"] or ""),
            "total_seconds": float(r["total_seconds"] or 0),
            "formatted": _format_duration(float(r["total_seconds"] or 0)),
            "compact": _compact_duration(float(r["total_seconds"] or 0)),
        }
        for r in rows
    ]


def _serialize_window_rows(rows) -> list[dict]:
    return [
        {
            "process_name": str(r["process_name"]),
            "exe_path": str(r["exe_path"] or ""),
            "window_title": str(r["window_title"] or "(Untitled)"),
            "hwnd": int(r["hwnd"]),
            "total_seconds": float(r["total_seconds"] or 0),
            "formatted": _format_duration(float(r["total_seconds"] or 0)),
            "compact": _compact_duration(float(r["total_seconds"] or 0)),
        }
        for r in rows
    ]


def _serialize_grouped(software_rows, window_rows) -> list[dict]:
    """Build app list with nested windows."""
    apps = {}
    for r in software_rows:
        key = (str(r["process_name"]), str(r["exe_path"] or ""))
        apps[key] = {
            "process_name": str(r["process_name"]),
            "exe_path": str(r["exe_path"] or ""),
            "total_seconds": float(r["total_seconds"] or 0),
            "formatted": _format_duration(float(r["total_seconds"] or 0)),
            "compact": _compact_duration(float(r["total_seconds"] or 0)),
            "windows": [],
        }

    for r in window_rows:
        key = (str(r["process_name"]), str(r["exe_path"] or ""))
        if key not in apps:
            apps[key] = {
                "process_name": str(r["process_name"]),
                "exe_path": str(r["exe_path"] or ""),
                "total_seconds": 0.0,
                "formatted": "0s",
                "compact": "0s",
                "windows": [],
            }
        apps[key]["windows"].append({
            "window_title": str(r["window_title"] or "(Untitled)"),
            "hwnd": int(r["hwnd"]),
            "total_seconds": float(r["total_seconds"] or 0),
            "formatted": _format_duration(float(r["total_seconds"] or 0)),
            "compact": _compact_duration(float(r["total_seconds"] or 0)),
        })

    result = sorted(apps.values(), key=lambda a: a["total_seconds"], reverse=True)
    return result


# ─── Page routes ─────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ─── API routes ──────────────────────────────────────────────────────────────

@app.route("/api/today")
def api_today():
    dm = get_dm()
    software_rows = dm.fetch_software_totals("today")
    window_rows = dm.fetch_window_details("today")
    apps = _serialize_grouped(software_rows, window_rows)
    total = sum(a["total_seconds"] for a in apps)
    return jsonify({
        "date": date.today().isoformat(),
        "total_seconds": total,
        "total_formatted": _format_duration(total),
        "total_compact": _compact_duration(total),
        "app_count": len(apps),
        "top_app": apps[0]["process_name"] if apps else "—",
        "apps": apps,
    })


@app.route("/api/week")
def api_week():
    dm = get_dm()
    software_rows = dm.fetch_software_totals("week")
    window_rows = dm.fetch_window_details("week")
    apps = _serialize_grouped(software_rows, window_rows)
    total = sum(a["total_seconds"] for a in apps)
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    return jsonify({
        "range": f"{week_start.isoformat()} — {today.isoformat()}",
        "total_seconds": total,
        "total_formatted": _format_duration(total),
        "total_compact": _compact_duration(total),
        "app_count": len(apps),
        "top_app": apps[0]["process_name"] if apps else "—",
        "apps": apps,
    })


@app.route("/api/day/<day_key>")
def api_day(day_key: str):
    dm = get_dm()
    software_rows = dm.fetch_software_totals_for_day(day_key)
    window_rows = dm.fetch_window_details_for_day(day_key)
    apps = _serialize_grouped(software_rows, window_rows)
    total = sum(a["total_seconds"] for a in apps)
    return jsonify({
        "date": day_key,
        "total_seconds": total,
        "total_formatted": _format_duration(total),
        "total_compact": _compact_duration(total),
        "app_count": len(apps),
        "top_app": apps[0]["process_name"] if apps else "—",
        "apps": apps,
    })


@app.route("/api/calendar/<int:year>/<int:month>")
def api_calendar(year: int, month: int):
    dm = get_dm()
    last_day = calendar.monthrange(year, month)[1]
    day_from = date(year, month, 1).isoformat()
    day_to = date(year, month, last_day).isoformat()
    rows = dm.fetch_daily_totals(day_from, day_to)
    totals = {
        str(r["day_key"]): {
            "total_seconds": float(r["total_seconds"] or 0),
            "formatted": _format_duration(float(r["total_seconds"] or 0)),
            "compact": _compact_duration(float(r["total_seconds"] or 0)),
        }
        for r in rows
    }
    return jsonify({
        "year": year,
        "month": month,
        "totals": totals,
    })


@app.route("/api/calendar/<int:year>/<int:month>/<int:day>/popup")
def api_day_popup(year: int, month: int, day: int):
    dm = get_dm()
    day_key = date(year, month, day).isoformat()
    software_rows = dm.fetch_software_totals_for_day(day_key)
    total = sum(float(r["total_seconds"] or 0) for r in software_rows)
    apps = [
        {
            "process_name": str(r["process_name"]),
            "total_seconds": float(r["total_seconds"] or 0),
            "compact": _compact_duration(float(r["total_seconds"] or 0)),
        }
        for r in software_rows[:5]
    ]
    return jsonify({
        "date": day_key,
        "total_seconds": total,
        "compact": _compact_duration(total),
        "apps": apps,
    })


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="WinVibeTime Web Dashboard")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--db", default=None, help="Path to SQLite database")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.db:
        app.config["DB_PATH"] = args.db

    print(f"WinVibeTime Web Dashboard starting on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
