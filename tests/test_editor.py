import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader

from swirl import pdfedit
from swirl.editor import RENDER_SCALE, BoxItem, FormPage, ImageItem, OrganizePage, PageEditor, TextItem

from .test_pdftools import make_report


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_scene_positions_map_to_pdf_points(app, tmp_path):
    pdf = make_report(tmp_path / "r.pdf", 2)
    ed = PageEditor(pdf, "redact")
    ed.show_page(1)
    s = RENDER_SCALE
    # A box 100pt from the left and 50pt from the top, 200 x 30 pt.
    box = BoxItem(QRectF(100 * s, 50 * s, 200 * s, 30 * s), "redact", "#000")
    ed.scene_for(1).addItem(box)
    (e,) = ed.edits()
    page_h = PdfReader(pdf).pages[1].mediabox.height
    assert e["page"] == 1 and e["type"] == "redact"
    assert e["x"] == pytest.approx(100) and e["w"] == pytest.approx(200)
    assert e["y"] == pytest.approx(float(page_h) - 80) and e["h"] == pytest.approx(30)


def test_editor_saves_text_and_signature(app, tmp_path):
    pdf = make_report(tmp_path / "r.pdf", 1)
    sig = pdfedit.text_signature("Zainab", tmp_path / "sig.png")
    ed = PageEditor(pdf, "edit")
    sc = ed.scene_for(0)
    t = TextItem("Approved", "#d32f2f", 14 * RENDER_SCALE); t.setPos(QPointF(100, 100)); sc.addItem(t)
    img = ImageItem(sig, 160 * RENDER_SCALE); img.setPos(QPointF(300, 900)); sc.addItem(img)
    edits = ed.edits()
    assert {e["type"] for e in edits} == {"text", "image"}
    out = pdfedit.apply_edits(pdf, edits)
    assert "Approved" in PdfReader(out).pages[0].extract_text()


def test_placeholder_text_is_ignored(app, tmp_path):
    ed = PageEditor(make_report(tmp_path / "r.pdf", 1), "edit")
    ed.scene_for(0).addItem(TextItem("Type here", "#111", 20))
    assert ed.edits() == []


def test_organize_page_plan(app, tmp_path):
    page = OrganizePage(make_report(tmp_path / "r.pdf", 3))
    page.grid.setCurrentRow(0); page.grid.item(0).setSelected(True)
    page.rotate(90)
    page.reverse()
    assert [d["source"] for d in page.plan()] == [2, 1, 0]
    assert page.plan()[-1]["rotate"] == 90


def test_form_page(app, tmp_path):
    from reportlab.pdfgen import canvas
    path = tmp_path / "form.pdf"
    c = canvas.Canvas(str(path)); c.drawString(72, 750, "City")
    c.acroForm.textfield(name="city", x=100, y=700, width=200, height=20); c.save()
    page = FormPage(path)
    page.inputs["city"].setText("Peshawar")
    assert page.values() == {"city": "Peshawar"}
