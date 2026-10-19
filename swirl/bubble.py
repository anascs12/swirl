"""A small always-on-top drop target: drop files on it to open the wheel."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QMenu, QWidget

SIZE = 68


class Bubble(QWidget):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setFixedSize(SIZE, SIZE)
        self.setToolTip("Drop files here to convert them · drag to move · right-click for options")
        self._drag_from: QPoint | None = None
        self._hot = False
        area = QGuiApplication.primaryScreen().availableGeometry()
        self.move(area.right() - SIZE - 24, area.bottom() - SIZE - 96)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(SIZE / 2, SIZE / 2)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 40))
        p.drawEllipse(c + QPointF(0, 2), SIZE / 2 - 3, SIZE / 2 - 3)
        p.setBrush(QColor(124, 92, 255) if self._hot else QColor(28, 28, 36, 235))
        p.setPen(QPen(QColor(124, 92, 255), 2))
        p.drawEllipse(c, SIZE / 2 - 6, SIZE / 2 - 6)
        # a small swirl mark: three arcs
        p.setPen(QPen(QColor(242, 242, 247), 3, Qt.SolidLine, Qt.RoundCap))
        for k, r in enumerate((15, 10, 5)):
            p.drawArc(int(c.x() - r), int(c.y() - r), 2 * r, 2 * r, (90 + 120 * k) * 16, 240 * 16)
        p.end()

    # drag to move
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_from = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._drag_from is not None:
            self.move(e.globalPosition().toPoint() - self._drag_from)

    def mouseReleaseEvent(self, _):
        self._drag_from = None

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        quit_action = QAction("Quit Swirl", menu)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(quit_action)
        menu.exec(e.globalPos())

    # drops
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hot = True
            self.update()

    def dragLeaveEvent(self, _):
        self._hot = False
        self.update()

    def dropEvent(self, e):
        self._hot = False
        self.update()
        files = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        files = [f for f in files if f.is_file()]
        if files:
            e.acceptProposedAction()
            self.files_dropped.emit(files)
