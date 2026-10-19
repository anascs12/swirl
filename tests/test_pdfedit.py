from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from swirl import pdfedit, tools

from .test_pdftools import make_report


def all_text_bytes(path: Path) -> bytes:
    """Every stream object in the file, decoded, including unreferenced leftovers."""
    from pypdf.generic import IndirectObject, StreamObject
    reader = PdfReader(path)
    chunks = []
    for gen, ids in reader.xref.items():
        for num in ids:
            try:
                obj = reader.get_object(IndirectObject(num, gen, reader))
            except Exception:
                continue
            if isinstance(obj, StreamObject):
                try:
                    chunks.append(obj.get_data())
                except Exception:
                    chunks.append(obj._data or b"")
    return b"\n".join(chunks)


@pytest.fixture
def report(tmp_path):
    return make_report(tmp_path / "report.pdf", 3)


def test_stamps_text_shapes_and_images(report, tmp_path):
    logo = tmp_path / "sig.png"
    Image.new("RGBA", (200, 80), (20, 40, 120, 255)).save(logo)
    out = pdfedit.apply_edits(report, [
        {"page": 0, "type": "text", "x": 72, "y": 600, "text": "Approved by Ayesha", "size": 14},
        {"page": 0, "type": "highlight", "x": 70, "y": 725, "w": 200, "h": 16},
        {"page": 1, "type": "rect", "x": 50, "y": 50, "w": 100, "h": 40, "color": "#d00000"},
        {"page": 1, "type": "ink", "points": [[100, 100], [120, 130], [160, 110]]},
        {"page": 2, "type": "image", "x": 300, "y": 80, "w": 150, "h": 60, "path": str(logo)},
    ])
    r = PdfReader(out)
    assert "Approved by Ayesha" in r.pages[0].extract_text()
    assert "Quarterly Report 1" in r.pages[0].extract_text()          # original text kept
    assert len(r.pages[2].images) >= 1


def test_redaction_really_removes_text(report):
    assert "Page 1 talks" in PdfReader(report).pages[0].extract_text()
    assert b"Page 1 talks" in all_text_bytes(report)                   # the check below is meaningful
    out = pdfedit.apply_edits(report, [{"page": 0, "type": "redact", "x": 60, "y": 720, "w": 400, "h": 25}], tag="-redacted")
    r = PdfReader(out)
    assert r.pages[0].extract_text().strip() == ""                    # page 1 is flattened
    assert "Quarterly Report 2" in r.pages[1].extract_text()          # other pages untouched
    assert b"Page 1 talks" not in all_text_bytes(out)                 # gone from the file bytes too


def test_organize(report):
    out = pdfedit.organize(report, [{"source": 2}, {"blank": True}, {"source": 0, "rotate": 90}])
    r = PdfReader(out)
    assert len(r.pages) == 3
    assert "Report 3" in r.pages[0].extract_text()
    assert r.pages[1].extract_text().strip() == ""
    assert r.pages[2].rotation == 90


def test_forms(tmp_path):
    from reportlab.pdfgen import canvas
    path = tmp_path / "form.pdf"
    c = canvas.Canvas(str(path))
    c.drawString(72, 750, "Name:")
    c.acroForm.textfield(name="name", x=120, y=740, width=200, height=20)
    c.acroForm.checkbox(name="agree", x=120, y=700, size=16)
    c.save()
    fields = pdfedit.form_fields(path)
    assert fields["name"]["type"] == "text" and fields["agree"]["type"] == "check"
    out = pdfedit.fill_form(path, {"name": "Zainab Shah"})
    assert PdfReader(out).get_fields()["name"]["/V"] == "Zainab Shah"


def test_signatures(tmp_path):
    typed = pdfedit.text_signature("Hamza Ali", tmp_path / "typed.png")
    assert Image.open(typed).mode == "RGBA"
    photo = tmp_path / "paper.jpg"
    img = Image.new("RGB", (600, 300), "white")
    from PIL import ImageDraw
    ImageDraw.Draw(img).line([(100, 200), (300, 100), (500, 220)], fill="black", width=8)
    img.save(photo)
    clean = pdfedit.clean_signature_image(photo, tmp_path / "clean.png")
    out = Image.open(clean)
    assert out.mode == "RGBA" and out.getpixel((0, 0))[3] == 0 and out.width < 600


@pytest.mark.skipif(not tools.find("tesseract"), reason="tesseract not installed")
def test_ocr_makes_scans_searchable(tmp_path):
    from PIL import ImageDraw, ImageFont
    img = Image.new("RGB", (1700, 2200), "white")
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 64)
    ImageDraw.Draw(img).text((150, 300), "Invoice number 4821", fill="black", font=font)
    scan = tmp_path / "scan.pdf"
    img.save(scan, "PDF", resolution=200)
    assert PdfReader(scan).pages[0].extract_text().strip() == ""
    out = pdfedit.ocr(scan)
    assert "4821" in PdfReader(out).pages[0].extract_text()
    assert abs(float(PdfReader(out).pages[0].mediabox.width) - float(PdfReader(scan).pages[0].mediabox.width)) < 1
