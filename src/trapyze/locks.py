"""Keep two runs from writing the same shared database at the same time.

A tool's label lists what it writes (`writes = ["data/prices.db"]`). Before
a run starts, the runner takes a lock for each of those. A lock is a small
file holding the process id of its owner; a lock whose owner has died is
taken over, so a crash never blocks a database for good.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path


class Busy(RuntimeError):
    """Another run is writing the same shared data."""


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows only
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return False
            return code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Locks:
    def __init__(self, folder: Path):
        self.folder = folder

    def _path(self, resource: str) -> Path:
        digest = hashlib.sha1(resource.encode("utf-8")).hexdigest()[:16]
        return self.folder / f"{digest}.lock"

    def acquire(self, resources: list[str], owner: str) -> list[Path]:
        """Take every lock or none. Raises Busy naming who holds one."""
        self.folder.mkdir(parents=True, exist_ok=True)
        taken: list[Path] = []
        try:
            for resource in resources:
                taken.append(self._take(resource, owner))
        except Busy:
            self.release(taken)
            raise
        return taken

    def _take(self, resource: str, owner: str) -> Path:
        path = self._path(resource)
        record = json.dumps({"resource": resource, "owner": owner, "pid": os.getpid(), "since": time.time()})
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                holder = self._read(path)
                if holder and _pid_alive(int(holder.get("pid", -1))):
                    raise Busy(
                        f"{holder.get('owner', 'Another tool')} is still writing {resource}. "
                        "This run will have to wait until it's done."
                    ) from None
                path.unlink(missing_ok=True)  # stale: its owner is gone
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(record)
            return path
        raise Busy(f"Couldn't lock {resource}. Try again in a moment.")

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    @staticmethod
    def release(paths: list[Path]) -> None:
        for p in paths:
            p.unlink(missing_ok=True)
