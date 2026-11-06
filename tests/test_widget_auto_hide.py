"""Fork: auto hide blanks widgets instead of hiding windows (for OpenKneeboard / VR capture)"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PySide2.QtGui import QColor, QPainter
from PySide2.QtWidgets import QApplication, QLabel, QVBoxLayout

import tinypedal
from tinypedal.state import ApplicationSignal, OverlaySignal, RealtimeState
from tinypedal.widget import _base


@pytest.fixture
def widget(monkeypatch):
    """A widget with a styled child label and its own painting"""
    app = QApplication.instance() or QApplication([])
    state = RealtimeState()
    signal = OverlaySignal()
    for module in (tinypedal, _base):
        monkeypatch.setattr(module, "realtime_state", state, raising=False)
        monkeypatch.setattr(module, "overlay_signal", signal, raising=False)
    monkeypatch.setattr(tinypedal, "app_signal", ApplicationSignal(), raising=False)
    state.active = True
    cfg = SimpleNamespace(
        user=SimpleNamespace(setting={"test": {
            "position_x": 0, "position_y": 0, "opacity": 1.0, "update_interval": 20, "enable": True,
        }}),
        compatibility={"enable_translucent_background": True, "enable_bypass_window_manager": False},
        overlay={"vr_compatibility": False, "fixed_position": True, "auto_hide": True},
        application={"minimum_update_interval": 10},
    )

    class Widget(_base.Base):
        def __init__(self):
            super().__init__(cfg, "test")
            layout = QVBoxLayout()
            label = QLabel("TEST")
            label.setStyleSheet("background: red; color: white")
            layout.addWidget(label)
            self.setLayout(layout)
            self.resize(100, 60)

        def paintEvent(self, event):
            QPainter(self).fillRect(0, 50, 100, 10, QColor("blue"))

        def timerEvent(self, event):
            pass

    test_widget = Widget()
    test_widget.start()
    app.processEvents()
    yield test_widget, signal, cfg, app
    test_widget.stop()


def drawn_pixels(widget):
    image = widget.grab().toImage()
    return sum(
        image.pixelColor(x, y).alpha() > 0
        for x in range(0, image.width(), 2)
        for y in range(0, image.height(), 2)
    )


def test_auto_hide_blanks_window(widget):
    test_widget, signal, _, app = widget
    shown = drawn_pixels(test_widget)
    size = test_widget.size()
    assert test_widget.isVisible() and shown > 0

    signal.hidden.emit(True)
    app.processEvents()
    assert test_widget.isVisible()  # window stays, so capture tools get an empty frame
    assert drawn_pixels(test_widget) == 0
    assert test_widget.size() == size

    signal.hidden.emit(False)
    app.processEvents()
    assert drawn_pixels(test_widget) == shown
    assert test_widget.size() == size


def test_auto_hide_without_translucency_hides_window(widget):
    test_widget, signal, cfg, app = widget
    cfg.compatibility["enable_translucent_background"] = False
    signal.hidden.emit(True)
    app.processEvents()
    assert not test_widget.isVisible()


def test_widget_hidden_with_overlay_hidden(widget):
    """A widget's own hide state blanks it, overlay auto hide still applies on top"""
    test_widget, signal, _, app = widget
    test_widget.set_widget_hidden(True)
    app.processEvents()
    assert test_widget.isVisible() and drawn_pixels(test_widget) == 0

    signal.hidden.emit(True)
    signal.hidden.emit(False)  # overlay shown again, widget stays hidden
    app.processEvents()
    assert drawn_pixels(test_widget) == 0

    test_widget.set_widget_hidden(False)
    app.processEvents()
    assert drawn_pixels(test_widget) > 0
