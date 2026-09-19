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
