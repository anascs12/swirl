import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication

from swirl import wheel as wheel_mod
from swirl.wheel import R_INNER, R_OUTER, SIZE, Wheel


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def at(angle_deg: float, radius: float) -> QPointF:
    import math
    a = math.radians(angle_deg)
    return QPointF(SIZE / 2 + radius * math.sin(a), SIZE / 2 - radius * math.cos(a))


def test_segments_follow_the_pointer(app, tmp_path):
    w = Wheel([tmp_path / "photo.jpg"])
    n = len(w.items)
    mid = (R_INNER + R_OUTER) / 2
    assert w._segment_at(at(0, mid)) == 0                      # top segment
    assert w._segment_at(at(360 / n, mid)) == 1                # next one clockwise
    assert w._segment_at(at(-360 / n, mid)) == n - 1           # previous one
    assert w._segment_at(at(0, R_INNER - 10)) == -1            # centre disc
    assert w._segment_at(at(0, R_OUTER + 10)) == -1            # outside


def test_tab_switches_between_formats_and_tools(app, tmp_path):
    w = Wheel([tmp_path / "a.pdf", tmp_path / "b.pdf"])
    assert w.group == "convert"
    w.toggle_group()
    assert w.group == "tool"
    assert "Merge" in [a.label for a in w.items]
    w.toggle_group()
    assert w.group == "convert"


def test_unsupported_and_mixed_files(app, tmp_path):
    assert Wheel([tmp_path / "data.xyz"]).state == "error"
    mixed = Wheel([tmp_path / "a.png", tmp_path / "b.mp3"])
    assert mixed.state == "error" and "one type" in mixed.message


def test_renders_without_errors(app, tmp_path):
    w = Wheel([tmp_path / "clip.mp4"])
    w.hover = 0
    img = w.grab()
    assert img.width() == SIZE * img.devicePixelRatio()
