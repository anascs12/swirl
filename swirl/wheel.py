"""The radial menu that appears at the pointer."""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetricsF, QGuiApplication, QImage, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import engine

SIZE = 400                 # window is a square; the wheel is centred in it
R_OUTER, R_INNER, R_CORE = 176, 92, 78
GAP_DEG = 2.2

# Palette: frosted dark glass. The blurred desktop shows through every layer.
GLASS_TINT = QColor(16, 16, 26, 140)          # over the blurred backdrop
GLASS_FALLBACK = QColor(22, 22, 32, 205)      # when the screen can't be captured
RING = QColor(255, 255, 255, 22)
RING_HOVER = QColor(124, 92, 255, 190)
RING_DISABLED = QColor(255, 255, 255, 8)
CORE = QColor(255, 255, 255, 26)
BLUR_RADIUS = 22
TEXT = QColor(242, 242, 247)
TEXT_DIM = QColor(205, 205, 220)
OK = QColor(52, 199, 89)
ERR = QColor(255, 99, 99)


class _Worker(QObject):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, action: engine.Action, files: list[Path]):
        super().__init__()
        self.action, self.files = action, files

    def run(self):
        try:
            self.done.emit(engine.perform(self.action, self.files))
        except Exception as exc:  # shown to the user in the wheel
            self.failed.emit(str(exc) or exc.__class__.__name__)


class Wheel(QWidget):
    """Frameless, translucent wheel of actions for a set of files."""

    finished = Signal()

    def __init__(self, files: list[Path]):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFixedSize(SIZE, SIZE)
        self.setWindowTitle("Swirl")

        self.files = files
        self.group = "convert"
        self.hover = -1
        self.state = "choose"           # choose | working | done | error
        self.message = ""
        self.spin = 0
        self._thread: QThread | None = None
        self._pick_group()

        self._spinner = QTimer(self, interval=30, timeout=self._tick)
        self._place_at_cursor()
        self._backdrop = self._capture_backdrop()

    # ── setup ────────────────────────────────────────────────
    def _pick_group(self):
        self.items = engine.actions_for(self.files, self.group)
        if not self.items and self.group == "convert":
            self.group = "tool"
            self.items = engine.actions_for(self.files, "tool")
        if not self.items:
            self.state = "error"
            self.message = self._unsupported_message()

    def _unsupported_message(self) -> str:
        kinds = {engine.kind_of(f) for f in self.files}
        if len(kinds) > 1:
            return "Pick files of one type"
        return f"Can't convert {self.files[0].suffix or 'this file'}"

    def _place_at_cursor(self):
        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        if pos.isNull():  # no global pointer position (e.g. native Wayland): centre
            pos = area.center()
        x = min(max(pos.x() - SIZE // 2, area.left()), area.right() - SIZE)
        y = min(max(pos.y() - SIZE // 2, area.top()), area.bottom() - SIZE)
        self.move(x, y)

    def _capture_backdrop(self) -> QPixmap | None:
        """Blurred copy of the screen behind the wheel, for the frosted-glass look.

        Returns None where the screen can't be read (native Wayland, some
        sandboxes); the wheel then uses a plain translucent tint.
        """
        try:
            from PIL import Image, ImageEnhance, ImageFilter
            centre = self.geometry().center()
            screen = QGuiApplication.screenAt(centre) or QGuiApplication.primaryScreen()
            g = screen.geometry()
            shot = screen.grabWindow(0, self.x() - g.x(), self.y() - g.y(), SIZE, SIZE).toImage()
            if shot.isNull() or shot.width() < 10:
                return None
            shot = shot.convertToFormat(QImage.Format_RGB888)
            pil = Image.frombytes("RGB", (shot.width(), shot.height()), bytes(shot.constBits()),
                                  "raw", "RGB", shot.bytesPerLine())
            lo, hi = zip(*pil.getextrema())
            if max(hi) - min(lo) < 6:          # a blank capture, not the real desktop
                return None
            pil = pil.filter(ImageFilter.GaussianBlur(BLUR_RADIUS * shot.width() / SIZE))
            pil = ImageEnhance.Color(pil).enhance(1.4)   # glass looks richer than the desktop
            data = pil.tobytes("raw", "RGB")
            img = QImage(data, pil.width, pil.height, pil.width * 3, QImage.Format_RGB888).copy()
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(shot.width() / SIZE)
            return pm
        except Exception:
            return None

    # ── geometry ─────────────────────────────────────────────
    @property
    def center(self) -> QPointF:
        return QPointF(SIZE / 2, SIZE / 2)

    def _segment_at(self, p: QPointF) -> int:
        d = p - self.center
        r = math.hypot(d.x(), d.y())
        if not (R_INNER <= r <= R_OUTER) or not self.items:
            return -1
        angle = (math.degrees(math.atan2(d.x(), -d.y())) + 360) % 360  # 0° = top, clockwise
        span = 360 / len(self.items)
        return int(((angle + span / 2) % 360) // span)

    def _segment_path(self, i: int) -> QPainterPath:
        span = 360 / len(self.items)
        # Qt angles: 0° = 3 o'clock, counter-clockwise. Segment i is centred on i*span from the top.
        start = 90 - (i * span) + span / 2 - GAP_DEG / 2
        sweep = -(span - GAP_DEG)
        c = self.center
        outer = QRectF(c.x() - R_OUTER, c.y() - R_OUTER, 2 * R_OUTER, 2 * R_OUTER)
        inner = QRectF(c.x() - R_INNER, c.y() - R_INNER, 2 * R_INNER, 2 * R_INNER)
        path = QPainterPath()
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, sweep)
        path.arcTo(inner, start + sweep, -sweep)
        path.closeSubpath()
        return path

    def _label_pos(self, i: int) -> QPointF:
        span = 360 / len(self.items)
        a = math.radians(i * span)
        r = (R_INNER + R_OUTER) / 2
        return QPointF(self.center.x() + r * math.sin(a), self.center.y() - r * math.cos(a))

    # ── painting ─────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        c = self.center

        # soft shadow
        for k, alpha in ((16, 14), (9, 22), (4, 30)):
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawEllipse(c, R_OUTER + k, R_OUTER + k)

        # frosted body: blurred desktop + tint, clipped to the disc
        disc = QPainterPath()
        disc.addEllipse(c, R_OUTER + 2, R_OUTER + 2)
        p.save()
        p.setClipPath(disc)
        if self._backdrop is not None:
            p.drawPixmap(0, 0, self._backdrop)
            p.fillPath(disc, GLASS_TINT)
        else:
            p.fillPath(disc, GLASS_FALLBACK)
        # light falling on the top of the glass
        sheen = QLinearGradient(c.x(), c.y() - R_OUTER, c.x(), c.y() + R_OUTER * 0.2)
        sheen.setColorAt(0, QColor(255, 255, 255, 46))
        sheen.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillPath(disc, sheen)
        p.restore()

        if self.state == "choose":
            self._paint_segments(p)
        self._paint_core(p)

        # bright rim, strongest at the top like a lit glass edge
        rim = QLinearGradient(c.x(), c.y() - R_OUTER, c.x(), c.y() + R_OUTER)
        rim.setColorAt(0, QColor(255, 255, 255, 150))
        rim.setColorAt(0.5, QColor(255, 255, 255, 40))
        rim.setColorAt(1, QColor(255, 255, 255, 80))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(rim, 1.4))
        p.drawEllipse(c, R_OUTER + 1.5, R_OUTER + 1.5)
        p.end()

    def _paint_segments(self, p: QPainter):
        label_font = QFont(self.font())
        label_font.setPixelSize(15 if len(self.items) <= 8 else 13)
        label_font.setWeight(QFont.DemiBold)
        fm = QFontMetricsF(label_font)
        for i, action in enumerate(self.items):
            enabled = action.available()
            fill = RING_HOVER if (i == self.hover and enabled) else (RING if enabled else RING_DISABLED)
            p.setPen(QPen(QColor(255, 255, 255, 70 if i == self.hover else 28), 1))
            p.setBrush(fill)
            p.drawPath(self._segment_path(i))

            p.setFont(label_font)
            p.setPen(TEXT if enabled else TEXT_DIM)
            pos = self._label_pos(i)
            lines = self._wrap(action.label, fm, 76)
            h = fm.height() * len(lines)
            for n, line in enumerate(lines):
                w = fm.horizontalAdvance(line)
                p.drawText(QPointF(pos.x() - w / 2, pos.y() - h / 2 + fm.ascent() + n * fm.height()), line)

    @staticmethod
    def _wrap(text: str, fm: QFontMetricsF, width: float) -> list[str]:
        if fm.horizontalAdvance(text) <= width or " " not in text:
            return [text]
        words, lines, line = text.split(), [], ""
        for w in words:
            trial = f"{line} {w}".strip()
            if fm.horizontalAdvance(trial) > width and line:
                lines.append(line)
                line = w
            else:
                line = trial
        return lines + [line]

    def _paint_core(self, p: QPainter):
        c = self.center
        core = QRadialGradient(c.x(), c.y() - R_CORE * 0.6, R_CORE * 1.6)
        core.setColorAt(0, QColor(255, 255, 255, 40))
        core.setColorAt(1, CORE)
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.setBrush(core)
        p.drawEllipse(c, R_CORE, R_CORE)

        title = QFont(self.font()); title.setPixelSize(13); title.setWeight(QFont.DemiBold)
        small = QFont(self.font()); small.setPixelSize(11)

        if self.state == "working":
            pen = QPen(RING_HOVER, 4, Qt.SolidLine, Qt.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawArc(QRectF(c.x() - 26, c.y() - 34, 52, 52), -self.spin * 16, 100 * 16)
            self._center_text(p, small, TEXT_DIM, "Converting…", 36)
            return
        if self.state in ("done", "error"):
            color = OK if self.state == "done" else ERR
            p.setPen(QPen(color, 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            if self.state == "done":
                path = QPainterPath(QPointF(c.x() - 16, c.y() - 14))
                path.lineTo(c.x() - 4, c.y() - 2)
                path.lineTo(c.x() + 18, c.y() - 26)
            else:
                path = QPainterPath(QPointF(c.x() - 13, c.y() - 27))
                path.lineTo(c.x() + 13, c.y() - 1)
                path.moveTo(c.x() + 13, c.y() - 27)
                path.lineTo(c.x() - 13, c.y() - 1)
            p.drawPath(path)
            self._center_text(p, small, TEXT, self.message, 22, width=2 * R_CORE - 20)
            return

        name = self.files[0].name if len(self.files) == 1 else f"{len(self.files)} files"
        self._center_text(p, title, TEXT, name, -8, width=2 * R_CORE - 22)
        hint = "Tab: tools" if self.group == "convert" else "Tab: formats"
        if not engine.actions_for(self.files, "tool" if self.group == "convert" else "convert"):
            hint = "Esc to close"
        self._center_text(p, small, TEXT_DIM, hint, 14)

        if 0 <= self.hover < len(self.items) and not self.items[self.hover].available():
            need = ", ".join(self.items[self.hover].missing())
            self._center_text(p, small, ERR, f"needs {need}", 32)

    def _center_text(self, p: QPainter, font: QFont, color: QColor, text: str, dy: float, width: float = 140):
        fm = QFontMetricsF(font)
        lines = self._wrap(text, fm, width)[:3]
        lines = [fm.elidedText(line, Qt.ElideMiddle, width) for line in lines]
        p.setFont(font)
        p.setPen(color)
        top = self.center.y() + dy - fm.height() * (len(lines) - 1) / 2
        for n, line in enumerate(lines):
            w = fm.horizontalAdvance(line)
            p.drawText(QPointF(self.center.x() - w / 2, top + n * fm.height()), line)

    # ── interaction ──────────────────────────────────────────
    def mouseMoveEvent(self, e):
        if self.state != "choose":
            return
        seg = self._segment_at(e.position())
        if seg != self.hover:
            self.hover = seg
            self.setCursor(Qt.PointingHandCursor if seg >= 0 and self.items[seg].available() else Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, e):
        if self.state == "working":
            return
        if self.state in ("done", "error"):
            self.close()
            return
        if e.button() == Qt.RightButton:
            self.toggle_group()
            return
        seg = self._segment_at(e.position())
        if seg >= 0:
            self.choose(seg)
        elif math.hypot(*(e.position() - self.center).toTuple()) > R_OUTER:
            self.close()  # click outside the wheel

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self.state != "working":
            self.close()
        elif e.key() == Qt.Key_Tab and self.state == "choose":
            self.toggle_group()

    def focusOutEvent(self, _):
        if self.state in ("choose", "done", "error"):
            QTimer.singleShot(150, self._close_if_inactive)

    def _close_if_inactive(self):
        if not self.isActiveWindow() and self.state != "working":
            self.close()

    def toggle_group(self):
        other = "tool" if self.group == "convert" else "convert"
        if engine.actions_for(self.files, other):
            self.group = other
            self.items = engine.actions_for(self.files, other)
            self.hover = -1
            self.update()

    def choose(self, index: int):
        action = self.items[index]
        if not action.available():
            return
        self.state = "working"
        self.setCursor(Qt.BusyCursor)
        self._spinner.start()
        self.update()

        self._thread = QThread(self)
        self._worker = _Worker(action, self.files)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._thread.start()

    def _tick(self):
        self.spin = (self.spin + 12) % 360
        self.update()

    def _finish(self, state: str, message: str, close_after: int):
        self._spinner.stop()
        self._thread.quit()
        self._thread.wait()
        self.state, self.message = state, message
        self.unsetCursor()
        self.update()
        QTimer.singleShot(close_after, self.close)

    def _on_done(self, outputs: list[Path]):
        if not outputs:  # handed off to Swirl Studio
            self._finish("done", "Opening Studio…", 600)
            return
        msg = f"Saved {outputs[0].name}" if len(outputs) == 1 else f"Saved {len(outputs)} files"
        self._finish("done", msg, 1400)

    def _on_failed(self, error: str):
        self._finish("error", error, 6000)

    def closeEvent(self, e):
        if self.state == "working":
            e.ignore()
            return
        self.finished.emit()
        super().closeEvent(e)

