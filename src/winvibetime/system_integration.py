from __future__ import annotations

import ctypes
import subprocess
import sys
from pathlib import Path

from .models import APP_NAME

if sys.platform == "win32":
    import winreg
else:
    winreg = None


RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_running_as_admin() -> bool:
    if sys.platform != "win32":
        return False

    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def build_launch_command(extra_args: list[str] | None = None) -> str:
    args = list(extra_args or [])

    if getattr(sys, "frozen", False):
        command = [sys.executable, *args]
    else:
        script_path = Path(sys.argv[0]).resolve()
        command = [sys.executable, str(script_path), *args]

    return subprocess.list2cmdline(command)


def relaunch_as_admin(extra_args: list[str] | None = None) -> bool:
    if sys.platform != "win32":
        return False

    executable = sys.executable if getattr(sys, "frozen", False) else sys.executable
    parameters = ""

    if getattr(sys, "frozen", False):
        executable = sys.executable
        parameters = subprocess.list2cmdline(list(extra_args or []))
    else:
        script_path = Path(sys.argv[0]).resolve()
        parameters = subprocess.list2cmdline([str(script_path), *(extra_args or [])])

    try:
        result = ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, parameters, None, 1)
    except Exception:
        return False

    return int(result) > 32


def enable_startup(app_name: str = APP_NAME, extra_args: list[str] | None = None) -> None:
    if sys.platform != "win32" or winreg is None:
        raise RuntimeError("Windows startup integration is only available on Windows.")

    command = build_launch_command(extra_args)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)


def disable_startup(app_name: str = APP_NAME) -> None:
    if sys.platform != "win32" or winreg is None:
        raise RuntimeError("Windows startup integration is only available on Windows.")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
        try:
            winreg.DeleteValue(key, app_name)
        except FileNotFoundError:
            return


def startup_enabled(app_name: str = APP_NAME) -> bool:
    if sys.platform != "win32" or winreg is None:
        return False

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH) as key:
        try:
            value, _ = winreg.QueryValueEx(key, app_name)
        except FileNotFoundError:
            return False

    return bool(str(value).strip())
