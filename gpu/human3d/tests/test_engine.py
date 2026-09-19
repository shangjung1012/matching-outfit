import importlib.util
from pathlib import Path

import pytest

from engine import LHMEngine


class FakeCuda:
    def is_available(self): return False


class FakeTorch:
    cuda = FakeCuda()


def test_engine_rejects_cpu_without_touching_upstream(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="CPU fallback is disabled"):
        LHMEngine(torch_module=FakeTorch(), upstream_root=tmp_path)


def test_extension_check_reports_missing_nested_package(monkeypatch) -> None:
    engine = object.__new__(LHMEngine)

    def fake_find_spec(name: str):
        if name == "spconv.pytorch":
            raise ModuleNotFoundError("No module named 'spconv'")
        return object()

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    with pytest.raises(RuntimeError, match=r"unavailable: spconv\.pytorch"):
        engine._check_dependencies()
