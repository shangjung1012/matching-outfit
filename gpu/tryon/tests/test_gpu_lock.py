from multiprocessing import Event, Process
from pathlib import Path
import time

from gpu_lock import SharedGPULock


def hold_lock(path: str, entered: Event, release: Event) -> None:
    with SharedGPULock(path):
        entered.set()
        release.wait(timeout=5)


def test_shared_gpu_lock_allows_only_one_process_at_a_time(tmp_path: Path) -> None:
    path = str(tmp_path / "inference.lock")
    first_entered = Event()
    first_release = Event()
    second_entered = Event()
    second_release = Event()
    first = Process(target=hold_lock, args=(path, first_entered, first_release))
    second = Process(target=hold_lock, args=(path, second_entered, second_release))
    first.start()
    try:
        assert first_entered.wait(timeout=2)
        second.start()
        time.sleep(0.15)
        assert not second_entered.is_set()
        first_release.set()
        assert second_entered.wait(timeout=2)
        second_release.set()
    finally:
        first_release.set()
        second_release.set()
        first.join(timeout=2)
        if second.pid is not None:
            second.join(timeout=2)
        if first.is_alive():
            first.terminate()
        if second.pid is not None and second.is_alive():
            second.terminate()

    assert first.exitcode == 0
    assert second.exitcode == 0
