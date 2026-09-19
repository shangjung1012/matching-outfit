from __future__ import annotations

import gc
from threading import RLock
from typing import Callable

from PIL import Image

from engine import FastFitEngine


class FastFitModelManager:
    """Own exactly one FastFit instance and make residency explicitly controllable."""

    def __init__(self, factory: Callable[[], FastFitEngine] = FastFitEngine) -> None:
        self._factory = factory
        self._engine: FastFitEngine | None = None
        self._lock = RLock()
        self._device_name = "NVIDIA CUDA GPU"
        self.peak_gpu_memory_bytes = 0

    @property
    def model_loaded(self) -> bool:
        return self._engine is not None

    @property
    def device_name(self) -> str:
        return self._device_name

    def load(self) -> None:
        with self._lock:
            if self._engine is not None:
                return
            engine = self._factory()
            self._device_name = engine.device_name
            self._engine = engine

    def unload(self) -> None:
        with self._lock:
            if self._engine is None:
                return
            engine = self._engine
            self._engine = None
            close = getattr(engine, "close", None)
            if callable(close):
                close()
            del engine
            gc.collect()
            self._empty_cuda_cache()

    def run(
        self,
        person: Image.Image,
        references: dict[str, Image.Image],
    ) -> bytes:
        with self._lock:
            self.load()
            assert self._engine is not None
            torch = self._engine.torch
            reset_peak = getattr(torch.cuda, "reset_peak_memory_stats", None)
            if callable(reset_peak):
                reset_peak()
            result = self._engine.run(person, references)
            max_allocated = getattr(torch.cuda, "max_memory_allocated", None)
            if callable(max_allocated):
                self.peak_gpu_memory_bytes = max(
                    self.peak_gpu_memory_bytes,
                    int(max_allocated()),
                )
            return result

    @staticmethod
    def _empty_cuda_cache() -> None:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except (ImportError, RuntimeError):
            pass
