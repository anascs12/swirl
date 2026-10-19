"""Visual PDF tools: the page editor (edit, sign, redact), organize and forms."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush, QColor, QFont, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QGraphicsItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsTextItem, QGraphicsView, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget, QListWidgetItem,
    QMessageBox, QPushButton, QScrollArea, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from . import pdfedit

RENDER_SCALE = 1.5          # page pixels per PDF point in the editor
COLORS = ["#111111", "#d32f2f", "#1f6feb", "#2f9e44", "#ffd400"]


def render_page(doc, index: int, scale: float) -> QPixmap:
    """`doc` is an open pypdfium2 document or a path (opened and closed here)."""
    if isinstance(doc, (str, Path)):
        import pypdfium2 as pdfium
        d = pdfium.PdfDocument(doc)
        try:
            return render_page(d, index, scale)
        finally:
            d.close()
    pil = doc[index].render(scale=scale).to_pil().convert("RGB")
    data = pil.tobytes("raw", "RGB")
    img = QImage(data, pil.width, pil.height, pil.width * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(img)


# ── Items placed on a page ────────────────────────────────────

class _Movable:
    FLAGS = QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsFocusable


class TextItem(QGraphicsTextItem):
    def __init__(self, text, color, px):
        super().__init__(text)
        self.setDefaultTextColor(QColor(color))
        f = QFont("Helvetica"); f.setPixelSize(int(px)); self.setFont(f)
        self.setFlags(_Movable.FLAGS)
        self.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.kind = "text"


class BoxItem(QGraphicsRectItem):
    def __init__(self, rect, kind, color):
        super().__init__(rect)
        self.kind = kind
        self.color = color
        self.setFlags(_Movable.FLAGS)
        c = QColor(color)
        if kind == "highlight":
            c.setAlpha(90); self.setBrush(c); self.setPen(Qt.NoPen)
        elif kind == "redact":
            self.setBrush(QColor(0, 0, 0)); self.setPen(QPen(QColor("#d32f2f"), 1.5, Qt.DashLine))
        else:
            self.setPen(QPen(c, 2 * RENDER_SCALE)); self.setBrush(Qt.NoBrush)


class InkItem(QGraphicsPathItem):
    def __init__(self, start: QPointF, color):
        super().__init__()
        self.kind = "ink"
        self.color = color
        self.points = [start]
        self.setPen(QPen(QColor(color), 2 * RENDER_SCALE, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        self.setFlags(_Movable.FLAGS)
        self._rebuild()

    def add(self, p: QPointF):
        self.points.append(p)
        self._rebuild()

    def _rebuild(self):
        path = QPainterPath(self.points[0])
        for p in self.points[1:]:
            path.lineTo(p)
        self.setPath(path)


class ImageItem(QGraphicsPixmapItem):
    def __init__(self, path: Path, width_px: float):
        pm = QPixmap(str(path))
        super().__init__(pm)
        self.kind = "image"
        self.path = path
        self.setTransformationMode(Qt.SmoothTransformation)
        self.setScale(width_px / max(1, pm.width()))
        self.setFlags(_Movable.FLAGS)


# ── Signature dialog ──────────────────────────────────────────

class DrawPad(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 200)
        self.strokes: list[list[QPointF]] = []
        self.setCursor(Qt.CrossCursor)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("white"))
        p.setPen(QPen(QColor("#d7dae1"), 1, Qt.DashLine))
        p.drawLine(30, self.height() - 50, self.width() - 30, self.height() - 50)
        p.setPen(QPen(QColor("#1a2b6d"), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for s in self.strokes:
            for a, b in zip(s, s[1:]):
                p.drawLine(a, b)

    def mousePressEvent(self, e): self.strokes.append([e.position()]); self.update()
    def mouseMoveEvent(self, e):
        if self.strokes: self.strokes[-1].append(e.position()); self.update()

    def save_png(self, dest: Path) -> Path | None:
        if not any(len(s) > 1 for s in self.strokes):
            return None
        img = QImage(self.size() * 2, QImage.Format_ARGB32); img.fill(Qt.transparent)
        img.setDevicePixelRatio(2)
        p = QPainter(img); p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor("#1a2b6d"), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for s in self.strokes:
            for a, b in zip(s, s[1:]):
                p.drawLine(a, b)
        p.end()
        img.save(str(dest))
        from PIL import Image
        pil = Image.open(dest); box = pil.getbbox()
        if box:
            pil.crop(box).save(dest)
        return dest


class SignatureDialog(QDialog):
    def __init__(self, parent, workdir: Path):
        super().__init__(parent)
        self.setWindowTitle("Create your signature")
        self.workdir = workdir
        self.result_path: Path | None = None
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.pad = DrawPad()
        draw_tab = QWidget(); dl = QVBoxLayout(draw_tab); dl.addWidget(self.pad)
        clear = QPushButton("Clear"); clear.clicked.connect(lambda: (self.pad.strokes.clear(), self.pad.update()))
        dl.addWidget(clear, alignment=Qt.AlignRight)
        self.tabs.addTab(draw_tab, "Draw")
        type_tab = QWidget(); tl = QFormLayout(type_tab)
        self.name = QLineEdit(placeholderText="Your full name"); tl.addRow("Name", self.name)
        self.tabs.addTab(type_tab, "Type")
        up_tab = QWidget(); ul = QVBoxLayout(up_tab)
        self.upload_path = QLineEdit(placeholderText="Photo or scan of your signature")
        pick = QPushButton("Choose image…")
        pick.clicked.connect(lambda: self.upload_path.setText(QFileDialog.getOpenFileName(self, "Signature image", "", "Images (*.png *.jpg *.jpeg)")[0]))
        ul.addWidget(self.upload_path); ul.addWidget(pick); ul.addWidget(QLabel("The paper background is removed automatically.")); ul.addStretch()
        self.tabs.addTab(up_tab, "Upload")
        lay.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept); buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def _accept(self):
        dest = self.workdir / f"signature-{id(self)}.png"
        tab = self.tabs.currentIndex()
        try:
            if tab == 0:
                self.result_path = self.pad.save_png(dest)
            elif tab == 1 and self.name.text().strip():
                self.result_path = pdfedit.text_signature(self.name.text().strip(), dest)
            elif tab == 2 and self.upload_path.text():
                self.result_path = pdfedit.clean_signature_image(Path(self.upload_path.text()), dest)
        except Exception as exc:
            QMessageBox.warning(self, "Signature", str(exc)); return
        if not self.result_path:
            QMessageBox.information(self, "Signature", "Draw, type or upload a signature first."); return
        self.accept()


# ── Page canvas ───────────────────────────────────────────────

class PageView(QGraphicsView):
    placed = Signal()

    def __init__(self, editor: "PageEditor"):
        super().__init__()
        self.editor = editor
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor("#e9ebef"))
        self.setDragMode(QGraphicsView.NoDrag)
        self._start: QPointF | None = None
        self._temp = None

    def wheelEvent(self, e):
        items = self.scene().selectedItems() if self.scene() else []
        if e.modifiers() & Qt.ControlModifier and items:
            factor = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
            for it in items:
                if isinstance(it, ImageItem):
                    it.setScale(it.scale() * factor)
                elif isinstance(it, TextItem):
                    f = it.font(); f.setPixelSize(max(6, int(f.pixelSize() * factor))); it.setFont(f)
            return
        super().wheelEvent(e)

    def mousePressEvent(self, e):
        mode = self.editor.mode
        pos = self.mapToScene(e.position().toPoint())
        if mode == "select" or e.button() != Qt.LeftButton or not self.editor.page_rect().contains(pos):
            return super().mousePressEvent(e)
        color = self.editor.color
        if mode == "text":
            item = TextItem("Type here", color, 14 * RENDER_SCALE)
            item.setPos(pos)
            self.scene().addItem(item)
            item.setFocus(); cursor = item.textCursor(); cursor.select(cursor.SelectionType.Document); item.setTextCursor(cursor)
            self.editor.push(item); self.editor.set_mode("select")
        elif mode in ("rect", "highlight", "redact"):
            self._start = pos
            self._temp = BoxItem(QRectF(pos, pos), mode, color if mode != "highlight" else "#ffd400")
            self.scene().addItem(self._temp)
        elif mode == "ink":
            self._temp = InkItem(pos, color)
            self.scene().addItem(self._temp)
        elif mode in ("image", "signature") and self.editor.pending_image:
            item = ImageItem(self.editor.pending_image, 160 * RENDER_SCALE)
            item.setPos(pos - QPointF(item.boundingRect().width() * item.scale() / 2, item.boundingRect().height() * item.scale() / 2))
            self.scene().addItem(item)
            self.editor.push(item)
            item.setSelected(True)
            self.editor.set_mode("select")

    def mouseMoveEvent(self, e):
        pos = self.mapToScene(e.position().toPoint())
        if isinstance(self._temp, BoxItem) and self._start is not None:
            self._temp.setRect(QRectF(self._start, pos).normalized())
        elif isinstance(self._temp, InkItem):
            self._temp.add(pos)
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._temp is not None:
            item, self._temp, self._start = self._temp, None, None
            too_small = isinstance(item, BoxItem) and (item.rect().width() < 4 or item.rect().height() < 4)
            if too_small or (isinstance(item, InkItem) and len(item.points) < 2):
                self.scene().removeItem(item)
            else:
                self.editor.push(item)
            return
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        focus = self.scene().focusItem() if self.scene() else None
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and not (isinstance(focus, TextItem) and focus.hasFocus()):
            for it in self.scene().selectedItems():
                self.scene().removeItem(it)
            return
        super().keyPressEvent(e)


class PageEditor(QWidget):
    """Edit, sign or redact a PDF. `purpose` picks the tools shown."""

    back = Signal()
    MODES = {
        "edit":   [("select", "Select"), ("text", "Text"), ("highlight", "Highlight"), ("rect", "Box"),
                   ("ink", "Draw"), ("image", "Image…"), ("signature", "Signature…")],
        "sign":   [("select", "Select"), ("signature", "Signature…"), ("text", "Date / text")],
        "redact": [("select", "Select"), ("redact", "Mark area")],
    }
    TITLES = {"edit": "Edit PDF", "sign": "Sign PDF", "redact": "Redact PDF"}

    def __init__(self, path: Path, purpose: str = "edit"):
        super().__init__()
        import pypdfium2 as pdfium
        self.setObjectName("page")
        self.path, self.purpose = path, purpose
        # Keep no PDF handle open: each page is rendered from the file when first shown.
        doc = pdfium.PdfDocument(path)
        self.sizes = [doc[i].get_size() for i in range(len(doc))]
        self.boxes = [tuple(doc[i].get_mediabox()) for i in range(len(doc))]
        self.scenes: dict[int, QGraphicsScene] = {}
        self.index = 0
        self.mode = "select"
        self.color = COLORS[0]
        self.pending_image: Path | None = None
        self.workdir = Path(tempfile.mkdtemp(prefix="swirl-"))
        self.history: list = []

        outer = QVBoxLayout(self); outer.setContentsMargins(24, 16, 24, 16)
        top = QHBoxLayout()
        back = QPushButton("← All tools", objectName="link"); back.clicked.connect(self.back)
        top.addWidget(back)
        title = QLabel(f"{self.TITLES[purpose]} · {path.name}"); title.setObjectName("cardTitle")
        top.addWidget(title); top.addStretch()
        self.save_btn = QPushButton("Save copy", objectName="primary"); self.save_btn.clicked.connect(self.save)
        top.addWidget(self.save_btn)
        outer.addLayout(top)

        bar = QHBoxLayout()
        self.mode_buttons = QButtonGroup(self)
        for key, label in self.MODES[purpose]:
            b = QPushButton(label, objectName="chip", checkable=True)
            b.clicked.connect(lambda _=False, k=key: self.set_mode(k))
            self.mode_buttons.addButton(b); b.setProperty("mode", key)
            bar.addWidget(b)
        if purpose == "edit":
            bar.addSpacing(12)
            for c in COLORS:
                sw = QToolButton(); sw.setFixedSize(22, 22)
                sw.setStyleSheet(f"background:{c}; border-radius:11px; border:2px solid white;")
                sw.clicked.connect(lambda _=False, c=c: setattr(self, "color", c))
                bar.addWidget(sw)
        bar.addStretch()
        undo = QPushButton("Undo"); undo.clicked.connect(self.undo); bar.addWidget(undo)
        for label, f in (("−", 1 / 1.2), ("+", 1.2)):
            z = QPushButton(label); z.setFixedWidth(36); z.clicked.connect(lambda _=False, f=f: self.view.scale(f, f)); bar.addWidget(z)
        outer.addLayout(bar)

        hint = {"edit": "Click to add text, drag to draw boxes. Select an item and press Delete to remove it, Ctrl+scroll to resize.",
                "sign": "Create your signature, then click where it goes. Ctrl+scroll resizes it.",
                "redact": "Drag over everything to hide. Marked pages are flattened so the text can't be copied back out."}[purpose]
        h = QLabel(hint); h.setObjectName("cardBlurb"); outer.addWidget(h)

        body = QHBoxLayout()
        self.thumbs = QListWidget()
        self.thumbs.setViewMode(QListView.IconMode); self.thumbs.setFlow(QListView.TopToBottom)
        self.thumbs.setIconSize(QSize(110, 150)); self.thumbs.setFixedWidth(150); self.thumbs.setMovement(QListView.Static)
        for i in range(len(doc)):
            it = QListWidgetItem(QIcon(render_page(doc, i, 0.25)), str(i + 1)); self.thumbs.addItem(it)
        doc.close()
        self.thumbs.currentRowChanged.connect(self.show_page)
        body.addWidget(self.thumbs)
        self.view = PageView(self)
        body.addWidget(self.view, 1)
        outer.addLayout(body, 1)
        self.thumbs.setCurrentRow(0)
        self.set_mode("select")

    # pages
    def scene_for(self, i: int) -> QGraphicsScene:
        if i not in self.scenes:
            sc = QGraphicsScene(self)
            bg = sc.addPixmap(render_page(self.path, i, RENDER_SCALE))
            bg.setZValue(-10); bg.setFlag(QGraphicsItem.ItemIsSelectable, False)
            sc.setSceneRect(bg.boundingRect().adjusted(-40, -40, 40, 40))
            self.scenes[i] = sc
        return self.scenes[i]

    def show_page(self, i: int):
        if i < 0:
            return
        self.index = i
        self.view.setScene(self.scene_for(i))
        self.view.fitInView(self.scene_for(i).itemsBoundingRect().adjusted(-20, -20, 20, 20), Qt.KeepAspectRatio)

    def page_rect(self) -> QRectF:
        w, h = self.sizes[self.index]
        return QRectF(0, 0, w * RENDER_SCALE, h * RENDER_SCALE)

    def showEvent(self, e):
        super().showEvent(e)
        self.show_page(self.index)

    # modes
    def set_mode(self, mode: str):
        if mode in ("image", "signature"):
            path = self._ask_image(mode)
            if not path:
                mode = "select"
            self.pending_image = path
        self.mode = mode
        for b in self.mode_buttons.buttons():
            b.setChecked(b.property("mode") == mode)
        self.view.setCursor(Qt.ArrowCursor if mode == "select" else Qt.CrossCursor)

    def _ask_image(self, mode):
        if mode == "signature":
            dlg = SignatureDialog(self, self.workdir)
            return dlg.result_path if dlg.exec() else None
        path, _ = QFileDialog.getOpenFileName(self, "Add image", "", "Images (*.png *.jpg *.jpeg *.webp)")
        return Path(path) if path else None

    def push(self, item):
        self.history.append((self.index, item))

    def undo(self):
        while self.history:
            i, item = self.history.pop()
            if item.scene() is not None:
                item.scene().removeItem(item)
                return

    # saving
    def edits(self) -> list[dict]:
        """Scene items → edit dicts in PDF points (origin bottom-left)."""
        out = []
        s = RENDER_SCALE
        for i, sc in self.scenes.items():
            _, page_h = self.sizes[i]
            ox, oy = self.boxes[i][0], self.boxes[i][1]
            to_pdf = lambda p: (ox + p.x() / s, oy + page_h - p.y() / s)
            for it in sc.items():
                kind = getattr(it, "kind", None)
                if kind in ("rect", "highlight", "redact"):
                    r = it.mapRectToScene(it.rect())
                    x0, y1 = to_pdf(r.topLeft()); x1, y0 = to_pdf(r.bottomRight())
                    out.append({"page": i, "type": kind, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "color": it.color})
                elif kind == "text":
                    text = it.toPlainText().strip()
                    if text and text != "Type here":
                        size = it.font().pixelSize() / s
                        tl = it.mapToScene(QPointF(4, 4))  # QGraphicsTextItem has a small document margin
                        x, top = to_pdf(tl)
                        out.append({"page": i, "type": "text", "x": x, "y": top - size * 0.95, "text": text,
                                    "size": size, "color": it.defaultTextColor().name()})
                elif kind == "ink":
                    out.append({"page": i, "type": "ink", "color": it.color,
                                "points": [list(to_pdf(it.mapToScene(p))) for p in it.points]})
                elif kind == "image":
                    r = it.mapRectToScene(it.boundingRect())
                    x0, y1 = to_pdf(r.topLeft()); x1, y0 = to_pdf(r.bottomRight())
                    out.append({"page": i, "type": "image", "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "path": str(it.path)})
        return out

    def save(self):
        edits = self.edits()
        if not edits:
            QMessageBox.information(self, self.TITLES[self.purpose], "Add something to the page first.")
            return
        if self.purpose == "redact" and QMessageBox.question(
                self, "Redact PDF", "Marked pages will be flattened into images so the hidden text is gone for good. "
                                    "The original file is kept. Continue?") != QMessageBox.Yes:
            return
        try:
            tag = {"edit": "-edited", "sign": "-signed", "redact": "-redacted"}[self.purpose]
            out = pdfedit.apply_edits(self.path, edits, tag=tag)
        except Exception as exc:
            QMessageBox.warning(self, "Couldn't save", str(exc)); return
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        if QMessageBox.information(self, "Saved", f"Saved {out.name} next to the original.",
                                   QMessageBox.Open | QMessageBox.Ok) == QMessageBox.Open:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(out)))


# ── Organize ──────────────────────────────────────────────────

class OrganizePage(QWidget):
    back = Signal()

    def __init__(self, path: Path):
        super().__init__()
        import pypdfium2 as pdfium
        self.setObjectName("page")
        self.path = path
        doc = pdfium.PdfDocument(path)
        outer = QVBoxLayout(self); outer.setContentsMargins(24, 16, 24, 16)
        top = QHBoxLayout()
        back = QPushButton("← All tools", objectName="link"); back.clicked.connect(self.back); top.addWidget(back)
        t = QLabel(f"Organize PDF · {path.name}"); t.setObjectName("cardTitle"); top.addWidget(t); top.addStretch()
        save = QPushButton("Save copy", objectName="primary"); save.clicked.connect(self.save); top.addWidget(save)
        outer.addLayout(top)
        bar = QHBoxLayout()
        for label, fn in (("Rotate left", lambda: self.rotate(-90)), ("Rotate right", lambda: self.rotate(90)),
                          ("Delete", self.delete), ("Insert blank page", self.blank), ("Reverse order", self.reverse)):
            b = QPushButton(label); b.clicked.connect(fn); bar.addWidget(b)
        bar.addStretch(); outer.addLayout(bar)
        h = QLabel("Drag pages to reorder. Select several with Ctrl or Shift."); h.setObjectName("cardBlurb"); outer.addWidget(h)
        self.grid = QListWidget()
        self.grid.setViewMode(QListView.IconMode); self.grid.setIconSize(QSize(150, 200)); self.grid.setGridSize(QSize(180, 240))
        self.grid.setResizeMode(QListView.Adjust); self.grid.setMovement(QListView.Snap)
        self.grid.setDragDropMode(QAbstractItemView.InternalMove); self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.pixmaps = {}
        for i in range(len(doc)):
            pm = render_page(doc, i, 0.35); self.pixmaps[i] = pm
            it = QListWidgetItem(QIcon(pm), f"Page {i + 1}")
            it.setData(Qt.UserRole, {"source": i, "rotate": 0})
            self.grid.addItem(it)
        doc.close()
        outer.addWidget(self.grid, 1)

    def _refresh(self, it):
        d = it.data(Qt.UserRole)
        if d.get("blank"):
            pm = QPixmap(150, 200); pm.fill(QColor("white"))
        else:
            from PySide6.QtGui import QTransform
            pm = self.pixmaps[d["source"]].transformed(QTransform().rotate(d["rotate"]))
        it.setIcon(QIcon(pm))

    def rotate(self, deg):
        for it in self.grid.selectedItems():
            d = dict(it.data(Qt.UserRole))
            if not d.get("blank"):
                d["rotate"] = (d["rotate"] + deg) % 360
                it.setData(Qt.UserRole, d); self._refresh(it)

    def delete(self):
        for it in self.grid.selectedItems():
            self.grid.takeItem(self.grid.row(it))

    def blank(self):
        row = max([self.grid.row(i) for i in self.grid.selectedItems()], default=self.grid.count() - 1) + 1
        it = QListWidgetItem("Blank"); it.setData(Qt.UserRole, {"blank": True})
        self.grid.insertItem(row, it); self._refresh(it)

    def reverse(self):
        items = [self.grid.takeItem(0) for _ in range(self.grid.count())]
        for it in reversed(items):
            self.grid.addItem(it)

    def plan(self) -> list[dict]:
        return [self.grid.item(i).data(Qt.UserRole) for i in range(self.grid.count())]

    def save(self):
        try:
            out = pdfedit.organize(self.path, self.plan())
        except Exception as exc:
            QMessageBox.warning(self, "Couldn't save", str(exc)); return
        QMessageBox.information(self, "Saved", f"Saved {out.name} next to the original.")


# ── Forms ─────────────────────────────────────────────────────

class FormPage(QWidget):
    back = Signal()

    def __init__(self, path: Path):
        super().__init__()
        self.setObjectName("page")
        self.path = path
        outer = QVBoxLayout(self); outer.setContentsMargins(40, 24, 40, 24)
        top = QHBoxLayout()
        back = QPushButton("← All tools", objectName="link"); back.clicked.connect(self.back); top.addWidget(back)
        t = QLabel(f"Fill PDF form · {path.name}"); t.setObjectName("cardTitle"); top.addWidget(t); top.addStretch()
        outer.addLayout(top)
        self.fields = pdfedit.form_fields(path)
        panel = QFrame(objectName="panel"); form = QFormLayout(panel); form.setContentsMargins(20, 18, 20, 18)
        self.inputs = {}
        if not self.fields:
            form.addRow(QLabel("This PDF has no fillable fields."))
        for name, f in self.fields.items():
            if f["type"] == "check":
                w = QCheckBox(); w.setChecked(str(f["value"]) not in ("", "/Off")); w.on = (f["options"] or ["/Yes"])[0]
            elif f["type"] == "choice" and f["options"]:
                w = QComboBox(); w.addItems(f["options"]); w.setCurrentText(str(f["value"]))
            else:
                w = QLineEdit(str(f["value"] or ""))
            self.inputs[name] = w
            form.addRow(name, w)
        self.flatten = QCheckBox("Flatten (fields can no longer be changed)")
        form.addRow(self.flatten)
        scroll = QScrollArea(widgetResizable=True, frameShape=QFrame.NoFrame); scroll.setWidget(panel)
        outer.addWidget(scroll, 1)
        save = QPushButton("Save filled copy", objectName="primary"); save.clicked.connect(self.save)
        save.setEnabled(bool(self.fields)); outer.addWidget(save, alignment=Qt.AlignRight)

    def values(self) -> dict:
        out = {}
        for name, w in self.inputs.items():
            if isinstance(w, QCheckBox):
                out[name] = w.on if w.isChecked() else "/Off"
            elif isinstance(w, QComboBox):
                out[name] = w.currentText()
            else:
                out[name] = w.text()
        return out

    def save(self):
        try:
            out = pdfedit.fill_form(self.path, self.values(), flatten=self.flatten.isChecked())
        except Exception as exc:
            QMessageBox.warning(self, "Couldn't save", str(exc)); return
        QMessageBox.information(self, "Saved", f"Saved {out.name} next to the original.")
