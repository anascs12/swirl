"""Swirl Studio: every PDF tool in one window, like an offline iLovePDF."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QDoubleValidator, QFont, QIntValidator, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QProgressBar, QPushButton,
    QScrollArea, QStackedWidget, QVBoxLayout, QWidget,
)

from . import __version__, pdftools
from .pdftools import Option, Tool

CATEGORY_COLORS = {
    "Organize": "#e5532d", "Optimize": "#2f9e44", "Edit": "#8e44ad", "Security": "#1f6feb",
    "From PDF": "#d6336c", "To PDF": "#e8a317", "Review": "#0c8599",
}

STYLE = """
QWidget { font-size: 14px; color: #14161c; }
QMainWindow, #page { background: #f6f7f9; }
#title { font-size: 26px; font-weight: 700; }
#subtitle { color: #5b6170; font-size: 15px; }
#card { background: #ffffff; border: 1px solid #e3e5ea; border-radius: 14px; }
#card:hover { border-color: #b9bdc8; }
#cardTitle { font-size: 15px; font-weight: 600; }
#cardBlurb { color: #5b6170; font-size: 12.5px; }
QLineEdit, QComboBox {
  background: #ffffff; border: 1px solid #d7dae1; border-radius: 9px; padding: 7px 10px; min-height: 20px; }
QLineEdit:focus, QComboBox:focus { border-color: #5b4bff; }
QPushButton { background: #ffffff; border: 1px solid #d7dae1; border-radius: 9px; padding: 8px 14px; }
QPushButton:hover { background: #f0f1f4; }
QPushButton#primary { background: #5b4bff; color: white; border: none; font-weight: 600; padding: 12px 22px; font-size: 15px; }
QPushButton#primary:hover { background: #4a3bf0; }
QPushButton#primary:disabled { background: #b8b2ff; }
QPushButton#chip { border-radius: 15px; padding: 5px 14px; min-height: 18px; background: #ffffff; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { image: url(@ASSETS@/chevron-down.svg); width: 12px; height: 12px; margin-right: 10px; }
QComboBox QAbstractItemView { background: #ffffff; border: 1px solid #d7dae1; selection-background-color: #eeecff; }
QPushButton#chip:checked { background: #14161c; color: white; border-color: #14161c; }
QPushButton#link { border: none; background: transparent; color: #5b4bff; padding: 4px 0; text-align: left; }
#drop { background: #ffffff; border: 2px dashed #c9ccd6; border-radius: 14px; }
#drop[hot="true"] { border-color: #5b4bff; background: #f3f1ff; }
QListWidget { background: #ffffff; border: 1px solid #e3e5ea; border-radius: 12px; padding: 4px; }
QListWidget::item { padding: 8px; border-radius: 8px; }
QListWidget::item:selected { background: #eeecff; color: #14161c; }
#panel { background: #ffffff; border: 1px solid #e3e5ea; border-radius: 14px; }
#error { color: #c92a2a; }
#ok { color: #2f9e44; font-weight: 600; }
QProgressBar { border: none; background: #e9e7ff; border-radius: 3px; height: 6px; }
QProgressBar::chunk { background: #5b4bff; border-radius: 3px; }
"""


def tool_icon(tool: Tool, size: int = 40) -> QPixmap:
    """A coloured rounded square with the tool's initials."""
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(CATEGORY_COLORS.get(tool.category, "#5b4bff")))
    p.drawRoundedRect(0, 0, size, size, 10, 10)
    words = [w for w in tool.title.replace("/", " ").split() if w.lower() not in ("pdf", "to", "add")]
    letters = "".join(w[0] for w in words[:2]).upper() or tool.title[:2].upper()
    f = QFont(); f.setPixelSize(int(size * 0.38)); f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(0, 0, size, size, Qt.AlignCenter, letters)
    p.end()
    return pm


class Card(QFrame):
    clicked = Signal(object)

    def __init__(self, tool: Tool):
        super().__init__()
        self.tool = tool
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(150)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        icon = QLabel(); icon.setPixmap(tool_icon(tool))
        title = QLabel(tool.title); title.setObjectName("cardTitle")
        blurb = QLabel(tool.blurb); blurb.setObjectName("cardBlurb"); blurb.setWordWrap(True)
        lay.addWidget(icon); lay.addSpacing(4); lay.addWidget(title); lay.addWidget(blurb); lay.addStretch()
        if tool.missing():
            need = QLabel(f"Needs {', '.join(tool.missing())}"); need.setObjectName("error")
            lay.addWidget(need)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.tool)


class Home(QWidget):
    open_tool = Signal(object)

    def __init__(self):
        super().__init__()
        self.setObjectName("page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 32, 40, 24)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        t = QLabel("Every PDF tool, offline"); t.setObjectName("title")
        s = QLabel("Merge, split, compress, convert, protect and more. Your files never leave this computer.")
        s.setObjectName("subtitle")
        titles.addWidget(t); titles.addWidget(s)
        head.addLayout(titles); head.addStretch()
        self.search = QLineEdit(placeholderText="Search tools…")
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.refresh)
        head.addWidget(self.search, alignment=Qt.AlignTop)
        outer.addLayout(head)
        outer.addSpacing(14)

        chips = QHBoxLayout()
        self.category = "All"
        self.chips = {}
        for name in ["All", *pdftools.CATEGORIES]:
            b = QPushButton(name, objectName="chip", checkable=True, checked=(name == "All"))
            b.clicked.connect(lambda _=False, n=name: self.set_category(n))
            chips.addWidget(b)
            self.chips[name] = b
        chips.addStretch()
        outer.addLayout(chips)
        outer.addSpacing(10)

        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame)
        holder = QWidget(objectName="page")
        self.grid = QGridLayout(holder)
        self.grid.setSpacing(14)
        self.grid.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(holder)
        outer.addWidget(scroll)
        self.cards = [Card(t) for t in pdftools.TOOLS]
        for c in self.cards:
            c.clicked.connect(self.open_tool)
        self.refresh()

    def set_category(self, name):
        self.category = name
        for n, b in self.chips.items():
            b.setChecked(n == name)
        self.refresh()

    def refresh(self):
        q = self.search.text().strip().lower()
        while self.grid.count():
            self.grid.takeAt(0).widget().setParent(None)
        shown = [c for c in self.cards
                 if (self.category == "All" or c.tool.category == self.category)
                 and (not q or q in c.tool.title.lower() or q in c.tool.blurb.lower())]
        cols = 4
        for i, c in enumerate(shown):
            self.grid.addWidget(c, i // cols, i % cols)
        self.grid.setRowStretch(len(shown) // cols + 1, 1)


class FileList(QListWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.model().rowsMoved.connect(lambda *_: self.changed.emit())

    def paths(self) -> list[Path]:
        return [Path(self.item(i).data(Qt.UserRole)) for i in range(self.count())]

    def add(self, paths):
        have = set(map(str, self.paths()))
        for p in paths:
            if str(p) in have:
                continue
            size = p.stat().st_size if p.exists() else 0
            item = QListWidgetItem(f"{p.name}    ·  {size / 1048576:.1f} MB" if size >= 1048576 else f"{p.name}    ·  {size // 1024 or 1} KB")
            item.setData(Qt.UserRole, str(p))
            item.setToolTip(str(p))
            self.addItem(item)
        self.changed.emit()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            for item in self.selectedItems():
                self.takeItem(self.row(item))
            self.changed.emit()
        else:
            super().keyPressEvent(e)


class _Runner(QObject):
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, tool, files, opts):
        super().__init__()
        self.tool, self.files, self.opts = tool, files, opts

    def run(self):
        try:
            self.done.emit(pdftools.run_tool(self.tool, self.files, self.opts))
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)


class ToolPage(QWidget):
    back = Signal()

    def __init__(self, tool: Tool, files: list[Path] = ()):
        super().__init__()
        self.tool = tool
        self.setObjectName("page")
        self.setAcceptDrops(True)
        self.inputs: dict[str, QWidget] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 24, 40, 24)
        back = QPushButton("← All tools", objectName="link")
        back.clicked.connect(self.back)
        outer.addWidget(back, alignment=Qt.AlignLeft)
        head = QHBoxLayout()
        icon = QLabel(); icon.setPixmap(tool_icon(tool, 48))
        head.addWidget(icon)
        titles = QVBoxLayout()
        t = QLabel(tool.title); t.setObjectName("title")
        s = QLabel(tool.blurb); s.setObjectName("subtitle")
        titles.addWidget(t); titles.addWidget(s)
        head.addLayout(titles); head.addStretch()
        outer.addLayout(head)
        outer.addSpacing(16)

        body = QHBoxLayout()
        body.setSpacing(20)
        outer.addLayout(body, 1)

        # Left: files
        left = QVBoxLayout()
        self.drop = QLabel(objectName="drop", alignment=Qt.AlignCenter)
        self.drop.setMinimumHeight(110)
        self.drop.setText(f"<b>Drop {self._accepts_text()} here</b><br><span style='color:#5b6170'>or</span>")
        left.addWidget(self.drop)
        pick = QPushButton("Choose files…")
        pick.clicked.connect(self.choose_files)
        left.addWidget(pick, alignment=Qt.AlignCenter)
        self.files = FileList()
        self.files.changed.connect(self.update_state)
        left.addWidget(self.files, 1)
        hint = QLabel("Drag files in the list to change their order. Delete removes a file.")
        hint.setObjectName("cardBlurb")
        left.addWidget(hint)
        body.addLayout(left, 3)

        # Right: options + run + result
        panel = QFrame(objectName="panel")
        panel.setMinimumWidth(340)
        right = QVBoxLayout(panel)
        right.setContentsMargins(20, 18, 20, 18)
        if tool.options:
            form = QFormLayout()
            form.setLabelAlignment(Qt.AlignLeft)
            form.setVerticalSpacing(10)
            for opt in tool.options:
                widget = self._input_for(opt)
                self.inputs[opt.key] = widget
                if opt.type == "bool":
                    form.addRow(widget)
                else:
                    form.addRow(opt.label, widget)
                if opt.hint:
                    h = QLabel(opt.hint); h.setObjectName("cardBlurb"); h.setWordWrap(True)
                    form.addRow("", h)
            right.addLayout(form)
        else:
            right.addWidget(QLabel("No settings needed."))
        right.addStretch()
        self.status = QLabel(wordWrap=True)
        right.addWidget(self.status)
        self.progress = QProgressBar(maximum=0, textVisible=False, visible=False)
        right.addWidget(self.progress)
        self.results = QVBoxLayout()
        right.addLayout(self.results)
        self.run_btn = QPushButton(tool.title, objectName="primary")
        self.run_btn.clicked.connect(self.run)
        right.addWidget(self.run_btn)
        body.addWidget(panel, 2)

        self.files.add([f for f in files if tool.accepts_file(f)])
        self.update_state()

    def _accepts_text(self) -> str:
        if self.tool.accepts == {".pdf"}:
            return "PDF files"
        exts = sorted(e.lstrip(".").upper() for e in self.tool.accepts)
        return ", ".join(exts[:5]) + (" …" if len(exts) > 5 else "") + " files"

    def _input_for(self, opt: Option) -> QWidget:
        if opt.type == "choice":
            w = QComboBox(); w.addItems(opt.choices); w.setCurrentText(str(opt.default))
            if opt.key == "mode":
                w.currentTextChanged.connect(self._mode_changed)
            return w
        if opt.type == "bool":
            w = QCheckBox(opt.label); w.setChecked(bool(opt.default)); return w
        if opt.type in ("int", "float"):
            # Plain fields with a validator: styled spin boxes render their text clipped.
            w = QLineEdit(str(opt.default))
            lo, hi = opt.min if opt.min is not None else -1e9, opt.max if opt.max is not None else 1e9
            w.setValidator(QIntValidator(int(lo), int(hi), w) if opt.type == "int" else QDoubleValidator(lo, hi, 2, w))
            w.number = opt.type
            w.setMaximumWidth(120)
            return w
        if opt.type == "file":
            row = QWidget(); lay = QHBoxLayout(row); lay.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(placeholderText="none"); btn = QPushButton("Browse…")
            btn.clicked.connect(lambda: edit.setText(QFileDialog.getOpenFileName(self, opt.label, "", "Images (*.png *.jpg *.jpeg)")[0] or edit.text()))
            lay.addWidget(edit); lay.addWidget(btn)
            row.text = edit.text  # read like a line edit
            return row
        w = QLineEdit(str(opt.default or ""))
        if opt.type == "password":
            w.setEchoMode(QLineEdit.Password)
        return w

    def _mode_changed(self, _=None):
        mode = self.inputs.get("mode")
        if not mode:
            return
        m = mode.currentText()
        for key, visible in (("ranges", m == "Custom ranges"), ("every", m == "Every N pages"),
                             ("margin", m == "Fixed margin"), ("padding", m.startswith("Auto"))):
            if key in self.inputs:
                self.inputs[key].setEnabled(visible)

    def values(self) -> dict:
        out = {}
        for opt in self.tool.options:
            w = self.inputs[opt.key]
            if isinstance(w, QComboBox):
                out[opt.key] = w.currentText()
            elif isinstance(w, QCheckBox):
                out[opt.key] = w.isChecked()
            elif getattr(w, "number", None):
                text = w.text().strip() or str(opt.default)
                out[opt.key] = int(float(text)) if w.number == "int" else float(text)
            else:
                out[opt.key] = w.text()
        return out

    def update_state(self):
        n = len(self.files.paths())
        need = self.tool.min_files
        missing = self.tool.missing()
        self._mode_changed()
        if missing:
            self.status.setObjectName("error"); self.status.setText(f"Install {', '.join(missing)} to use this tool.")
        elif n < need:
            self.status.setObjectName(""); self.status.setText(f"Add {'at least ' + str(need) if need > 1 else 'a'} file{'s' if need > 1 else ''} to start.")
        else:
            self.status.setObjectName(""); self.status.setText(f"{n} file{'s' if n != 1 else ''} ready.")
        self.status.setStyle(self.status.style())
        self.run_btn.setEnabled(n >= need and not missing)

    def choose_files(self):
        pattern = " ".join(f"*{e}" for e in sorted(self.tool.accepts))
        paths, _ = QFileDialog.getOpenFileNames(self, "Choose files", "", f"Supported files ({pattern})")
        self.files.add([Path(p) for p in paths])

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self.drop.setProperty("hot", True); self.drop.setStyle(self.drop.style())

    def dragLeaveEvent(self, _):
        self.drop.setProperty("hot", False); self.drop.setStyle(self.drop.style())

    def dropEvent(self, e):
        self.dragLeaveEvent(None)
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        good = [p for p in paths if p.is_file() and self.tool.accepts_file(p)]
        self.files.add(good)
        if len(good) < len(paths):
            self.status.setText(f"Skipped {len(paths) - len(good)} file(s) this tool can't use.")

    def run(self):
        while self.results.count():
            self.results.takeAt(0).widget().setParent(None)
        self.run_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setObjectName(""); self.status.setText("Working…"); self.status.setStyle(self.status.style())
        self._thread = QThread(self)
        self._runner = _Runner(self.tool, self.files.paths(), self.values())
        self._runner.moveToThread(self._thread)
        self._thread.started.connect(self._runner.run)
        self._runner.done.connect(self._done)
        self._runner.failed.connect(self._failed)
        self._thread.start()

    def _finish(self):
        self._thread.quit(); self._thread.wait()
        self.progress.setVisible(False)
        self.run_btn.setEnabled(True)

    def _done(self, outputs: list[Path]):
        self._finish()
        self.status.setObjectName("ok")
        self.status.setText(f"Done. Saved {len(outputs)} file{'s' if len(outputs) != 1 else ''} next to the originals.")
        self.status.setStyle(self.status.style())
        for path in outputs[:8]:
            b = QPushButton(f"Open {path.name}", objectName="link")
            b.clicked.connect(lambda _=False, p=path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
            self.results.addWidget(b)
        folder = QPushButton("Show in folder", objectName="link")
        folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(outputs[0].parent))))
        self.results.addWidget(folder)

    def _failed(self, error: str):
        self._finish()
        self.status.setObjectName("error"); self.status.setText(error); self.status.setStyle(self.status.style())


class Studio(QMainWindow):
    def __init__(self, files: list[Path] = (), tool_id: str | None = None):
        super().__init__()
        self.setWindowTitle(f"Swirl Studio {__version__}")
        self.resize(1180, 780)
        assets = (Path(__file__).parent / "assets").as_posix()
        self.setStyleSheet(STYLE.replace("@ASSETS@", assets))
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home = Home()
        self.home.open_tool.connect(lambda t: self.open_tool(t))
        self.stack.addWidget(self.home)
        self._files = list(files)
        if tool_id:
            self.open_tool(pdftools.TOOL_BY_ID[tool_id])

    def open_tool(self, tool: Tool):
        page = ToolPage(tool, self._files)
        self._files = []
        page.back.connect(lambda: self._go_home(page))
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def _go_home(self, page):
        self.stack.setCurrentWidget(self.home)
        self.stack.removeWidget(page)
        page.deleteLater()
