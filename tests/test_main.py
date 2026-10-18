import runpy
import sys

import pytest

from real_fast_cinema import __version__


def test_python_m_entry_point_prints_version(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["rf-cinema", "--version"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("real_fast_cinema", run_name="__main__")

    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"rf-cinema {__version__}"
