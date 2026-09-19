from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import TracebackType


class SharedGPULock:
    """Cross-process semaphore (capacity one) for all heavy GPU inference."""

    def __init__(self, path: str | None = None) -> None:
        self.path = Path(
            path
            or os.getenv(
                "GPU_LOCK_PATH", "/tmp/matching-outfit-gpu/inference.lock"
            )
        )
        self._handle = None

    def __enter__(self) -> SharedGPULock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+")
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()
        self._handle = None
