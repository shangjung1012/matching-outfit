from pathlib import Path

from PIL import Image

import residency
from engine import ReconstructionResult


class FakeEngine:
    model_loaded = False
    peak_gpu_memory_bytes = 0
    model_gpu_memory_bytes = 0

    def __init__(self, events: list[str], *, oom_once: bool = False) -> None:
        self.events = events
        self.oom_once = oom_once

    def load(self) -> None:
        self.events.append("lhm.load")
        self.model_loaded = True

    def unload(self) -> None:
        self.events.append("lhm.unload")
        self.model_loaded = False

    def run(self, _images, output_dir: Path) -> ReconstructionResult:
        self.events.append("lhm.run")
        if self.oom_once:
            self.oom_once = False
            (output_dir / "partial.ply").write_text("partial")
            raise RuntimeError("CUDA out of memory")
        artifact = output_dir / "result.ply"
        artifact.write_text("ply")
        return ReconstructionResult(artifact, "ply")


class FakeFastFit:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def unload(self) -> None:
        self.events.append("fastfit.unload")

    def load(self) -> None:
        self.events.append("fastfit.load")


class FakePreparedEngine(FakeEngine):
    def prepare(self, images):
        self.events.append("lhm.prepare")
        return ["prepared" for _ in images]

    def run_prepared(self, prepared, output_dir: Path) -> ReconstructionResult:
        assert prepared == ["prepared"]
        return super().run(prepared, output_dir)


class FakeMonitor:
    total_bytes = 16 * 1024**3
    peak_used_bytes = 0

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


def image() -> Image.Image:
    return Image.new("RGB", (8, 8), "white")


def test_switch_mode_unloads_fastfit_then_restores_it(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GPU_LOCK_PATH", str(tmp_path / "gpu.lock"))
    events: list[str] = []
    controller = residency.ResidencyController(
        FakeEngine(events),
        FakeFastFit(events),
        mode="switch",
    )
    controller.initialize()
    events.clear()

    controller.run([image()], tmp_path)

    assert events == [
        "fastfit.unload",
        "lhm.load",
        "lhm.run",
        "lhm.unload",
        "fastfit.load",
    ]


def test_cpu_preprocessing_happens_before_fastfit_is_unloaded(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GPU_LOCK_PATH", str(tmp_path / "gpu.lock"))
    events: list[str] = []
    controller = residency.ResidencyController(
        FakePreparedEngine(events),
        FakeFastFit(events),
        mode="switch",
    )
    controller.initialize()
    events.clear()

    controller.run([image()], tmp_path)

    assert events == [
        "lhm.prepare",
        "fastfit.unload",
        "lhm.load",
        "lhm.run",
        "lhm.unload",
        "fastfit.load",
    ]


def test_auto_mode_keeps_both_models_only_with_measured_headroom(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GPU_LOCK_PATH", str(tmp_path / "gpu.lock"))
    monkeypatch.setenv("GPU_VRAM_SAFETY_MARGIN_GB", "1.5")
    monitor = FakeMonitor()
    monitor.peak_used_bytes = 13 * 1024**3
    monkeypatch.setattr(residency, "DeviceMemoryMonitor", lambda: monitor)
    events: list[str] = []
    controller = residency.ResidencyController(
        FakeEngine(events),
        FakeFastFit(events),
        mode="auto",
    )
    controller.initialize()

    controller.run([image()], tmp_path)

    assert controller.effective_mode == "resident"
    assert events == ["lhm.load", "lhm.run"]


def test_auto_mode_falls_back_to_switch_after_unsafe_peak(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GPU_LOCK_PATH", str(tmp_path / "gpu.lock"))
    monitor = FakeMonitor()
    monitor.peak_used_bytes = 15 * 1024**3
    monkeypatch.setattr(residency, "DeviceMemoryMonitor", lambda: monitor)
    events: list[str] = []
    controller = residency.ResidencyController(
        FakeEngine(events),
        FakeFastFit(events),
        mode="auto",
    )
    controller.initialize()

    controller.run([image()], tmp_path)

    assert controller.effective_mode == "switch"
    assert events == ["lhm.load", "lhm.run", "lhm.unload", "fastfit.load"]


def test_auto_mode_falls_back_to_switch_when_peak_cannot_be_measured(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GPU_LOCK_PATH", str(tmp_path / "gpu.lock"))
    monitor = FakeMonitor()
    monitor.total_bytes = 0
    monkeypatch.setattr(residency, "DeviceMemoryMonitor", lambda: monitor)
    events: list[str] = []
    controller = residency.ResidencyController(
        FakeEngine(events),
        FakeFastFit(events),
        mode="auto",
    )
    controller.initialize()

    controller.run([image()], tmp_path)

    assert controller.effective_mode == "switch"
    assert events == ["lhm.load", "lhm.run", "lhm.unload", "fastfit.load"]


def test_auto_mode_retries_oom_with_lazy_switch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GPU_LOCK_PATH", str(tmp_path / "gpu.lock"))
    events: list[str] = []
    controller = residency.ResidencyController(
        FakeEngine(events, oom_once=True),
        FakeFastFit(events),
        mode="auto",
    )
    controller.initialize()

    result = controller.run([image()], tmp_path)

    assert result.artifact_path.name == "result.ply"
    assert controller.effective_mode == "switch"
    assert not (tmp_path / "partial.ply").exists()
    assert events == [
        "lhm.load",
        "lhm.run",
        "lhm.unload",
        "fastfit.unload",
        "lhm.load",
        "lhm.run",
        "lhm.unload",
        "fastfit.load",
    ]
