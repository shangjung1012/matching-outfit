from __future__ import annotations

import os
from pathlib import Path
from threading import Event, Thread
from typing import Any, Protocol

from PIL import Image

from engine import ReconstructionResult
from fastfit_control import FastFitControlClient
from gpu_lock import SharedGPULock


class ManagedEngine(Protocol):
    model_loaded: bool
    peak_gpu_memory_bytes: int
    model_gpu_memory_bytes: int

    def load(self) -> None: ...
    def unload(self) -> None: ...
    def prepare(self, images: list[Image.Image]) -> Any: ...
    def run_prepared(self, prepared: Any, output_dir: Path) -> ReconstructionResult: ...
    def run(self, images: list[Image.Image], output_dir: Path) -> ReconstructionResult: ...


class DeviceMemoryMonitor:
    def __init__(self, index: int = 0) -> None:
        self.index = index
        self.total_bytes = 0
        self.peak_used_bytes = 0
        self._stop = Event()
        self._thread: Thread | None = None
        self._nvml = None
        self._handle = None

    def start(self) -> None:
        try:
            import pynvml

            pynvml.nvmlInit()
            self._nvml = pynvml
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(self.index)
            info = pynvml.nvmlDeviceGetMemoryInfo(self._handle)
            self.total_bytes = int(info.total)
            self.peak_used_bytes = int(info.used)
            self._thread = Thread(target=self._sample, daemon=True)
            self._thread.start()
        except Exception:
            self._nvml = None

    def _sample(self) -> None:
        while not self._stop.wait(0.025):
            try:
                info = self._nvml.nvmlDeviceGetMemoryInfo(self._handle)
                self.peak_used_bytes = max(self.peak_used_bytes, int(info.used))
            except Exception:
                return

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._nvml is not None and self._handle is not None:
            try:
                info = self._nvml.nvmlDeviceGetMemoryInfo(self._handle)
                self.peak_used_bytes = max(self.peak_used_bytes, int(info.used))
            except Exception:
                pass


class ResidencyController:
    MODES = {"auto", "resident", "switch"}

    def __init__(
        self,
        engine: ManagedEngine,
        fastfit: FastFitControlClient | None = None,
        mode: str | None = None,
    ) -> None:
        self.engine = engine
        self.fastfit = fastfit or FastFitControlClient()
        requested = (mode or os.getenv("GPU_RESIDENCY_MODE", "switch")).lower()
        if requested not in self.MODES:
            raise ValueError(f"Invalid GPU_RESIDENCY_MODE: {requested}")
        self.requested_mode = requested
        self.effective_mode = requested
        self.safety_margin_bytes = int(
            float(os.getenv("GPU_VRAM_SAFETY_MARGIN_GB", "1.5")) * 1024**3
        )
        self.measured_device_peak_bytes = 0
        self.last_switch_error: str | None = None

    def initialize(self) -> None:
        if self.requested_mode == "switch":
            self.engine.unload()
            return
        with SharedGPULock():
            try:
                self.engine.load()
            except Exception as error:
                if self.requested_mode == "auto" and self._is_oom(error):
                    self.engine.unload()
                    self.effective_mode = "switch"
                    return
                raise

    @staticmethod
    def _is_oom(error: BaseException) -> bool:
        return "out of memory" in str(error).lower()

    def _prepare_inputs(self, images: list[Image.Image]) -> Any:
        prepare = getattr(self.engine, "prepare", None)
        return prepare(images) if callable(prepare) else images

    def _run_engine(self, prepared: Any, output_dir: Path) -> ReconstructionResult:
        run_prepared = getattr(self.engine, "run_prepared", None)
        if callable(run_prepared):
            return run_prepared(prepared, output_dir)
        return self.engine.run(prepared, output_dir)

    def _switch_run(self, prepared: Any, output_dir: Path) -> ReconstructionResult:
        self.fastfit.unload()
        try:
            self.engine.load()
            return self._run_engine(prepared, output_dir)
        finally:
            self.engine.unload()
            try:
                self.fastfit.load()
                self.last_switch_error = None
            except Exception as error:
                self.last_switch_error = str(error)
                raise

    def run(
        self, images: list[Image.Image], output_dir: Path
    ) -> ReconstructionResult:
        # Segmentation is CPU-only and may initialize/download its own model.
        # Do it before taking the shared GPU semaphore or unloading FastFit.
        prepared = self._prepare_inputs(images)
        with SharedGPULock():
            if self.effective_mode == "switch":
                return self._switch_run(prepared, output_dir)

            monitor = DeviceMemoryMonitor()
            monitor.start()
            try:
                result = self._run_engine(prepared, output_dir)
            except Exception as error:
                monitor.stop()
                if self.requested_mode != "auto" or not self._is_oom(error):
                    raise
                self.engine.unload()
                self.effective_mode = "switch"
                for partial in output_dir.glob("*"):
                    if partial.is_file():
                        partial.unlink(missing_ok=True)
                return self._switch_run(prepared, output_dir)
            monitor.stop()
            self.measured_device_peak_bytes = max(
                self.measured_device_peak_bytes, monitor.peak_used_bytes
            )
            if self.requested_mode == "auto":
                measured_safe = bool(monitor.total_bytes) and (
                    monitor.total_bytes - monitor.peak_used_bytes
                    >= self.safety_margin_bytes
                )
                if measured_safe:
                    self.effective_mode = "resident"
                else:
                    # Retain both models only after an actual device-wide peak
                    # measurement proves the configured headroom is available.
                    self.effective_mode = "switch"
                    self.engine.unload()
                    self.fastfit.load()
            return result

    def health(self) -> dict[str, object]:
        return {
            "residency_mode": self.effective_mode,
            "requested_residency_mode": self.requested_mode,
            "measured_device_peak_bytes": self.measured_device_peak_bytes,
            "vram_safety_margin_bytes": self.safety_margin_bytes,
            "switch_error": self.last_switch_error,
        }
