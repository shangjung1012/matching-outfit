from PIL import Image

from model_manager import FastFitModelManager


class FakeCuda:
    def reset_peak_memory_stats(self) -> None:
        pass

    def max_memory_allocated(self) -> int:
        return 4321


class FakeTorch:
    cuda = FakeCuda()


class FakeEngine:
    device_name = "Fake RTX 5080"
    torch = FakeTorch()

    def __init__(self) -> None:
        self.closed = False
        self.runs = 0

    def run(self, _person, _references) -> bytes:
        self.runs += 1
        return b"png"

    def close(self) -> None:
        self.closed = True


def test_manager_loads_once_runs_and_can_release_the_model(monkeypatch) -> None:
    created: list[FakeEngine] = []

    def factory() -> FakeEngine:
        engine = FakeEngine()
        created.append(engine)
        return engine

    monkeypatch.setattr(FastFitModelManager, "_empty_cuda_cache", staticmethod(lambda: None))
    manager = FastFitModelManager(factory=factory)
    person = Image.new("RGB", (8, 8), "white")

    assert manager.run(person, {}) == b"png"
    assert manager.run(person, {}) == b"png"
    assert len(created) == 1
    assert created[0].runs == 2
    assert manager.peak_gpu_memory_bytes == 4321

    manager.unload()
    assert manager.model_loaded is False
    assert created[0].closed is True

    manager.load()
    assert len(created) == 2
    assert manager.model_loaded is True
