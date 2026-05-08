from __future__ import annotations

import ctypes
import errno
import sys
import tempfile
from pathlib import Path


ERROR_ALREADY_EXISTS = 183

if sys.platform != "win32":
    import fcntl
else:
    fcntl = None


class SingleInstanceGuard:
    def __init__(self, name: str) -> None:
        self.name = name
        self.handle: int | None = None
        self.lock_file = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            return self._acquire_windows_mutex()
        return self._acquire_file_lock()

    def release(self) -> None:
        if sys.platform == "win32":
            self._release_windows_mutex()
            return
        self._release_file_lock()

    def _acquire_windows_mutex(self) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        mutex_name = f"Local\\{self.name}"
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        if not handle:
            raise OSError("Failed to create Windows mutex for single-instance guard.")

        self.handle = int(handle)
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    def _release_windows_mutex(self) -> None:
        if self.handle is None:
            return

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(ctypes.c_void_p(self.handle))
        self.handle = None

    def _acquire_file_lock(self) -> bool:
        if fcntl is None:
            return True

        lock_path = Path(tempfile.gettempdir()) / f"{self.name}.lock"
        self.lock_file = lock_path.open("w", encoding="utf-8")
        try:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                return False
            raise
        return True

    def _release_file_lock(self) -> None:
        if self.lock_file is None or fcntl is None:
            return

        try:
            fcntl.flock(self.lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            self.lock_file.close()
            self.lock_file = None
