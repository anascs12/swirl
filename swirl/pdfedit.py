"""Applying page edits (text, shapes, images, signatures, redactions), page
organizing, form filling and OCR. The editor UI produces plain dicts, so all of
this is testable without a screen.

Coordinates are PDF points from the page's bottom-left corner.
"""

from __future__ import annotations

import io
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import DictionaryObject, NameObject, StreamObject

from . import tools
from .engine import beside
from .pdftools import _hex, open_reader, overlay_page, write

# An edit:
#   {"page": 0, "type": "text", "x": 72, "y": 700, "text": "Hello", "size": 14, "color": "#111111"}
#   {"page": 0, "type": "rect", "x": .., "y": .., "w": .., "h": .., "color": "#d00", "fill": False, "width": 2}
#   {"page": 0, "type": "highlight", "x": .., "y": .., "w": .., "h": .., "color": "#ffd400"}
#   {"page": 0, "type": "line"|"ink", "points": [[x, y], ...], "color": "#111", "width": 2}
#   {"page": 0, "type": "image", "x": .., "y": .., "w": .., "h": .., "path": "sig.png"}
#   {"page": 0, "type": "redact", "x": .., "y": .., "w": .., "h": ..}


def _draw_edits(c, edits: list[dict]):
    from reportlab.lib.utils import ImageReader
    for e in edits:
        kind = e["type"]
        color = _hex(e.get("color", "#111111"))
        c.saveState()
        if kind == "text":
            c.setFillColor(color)
            size = float(e.get("size", 12))
            c.setFont(e.get("font", "Helvetica"), size)
            for i, line in enumerate(str(e["text"]).splitlines() or [""]):
                c.drawString(e["x"], e["y"] - i * size * 1.25, line)
        elif kind == "rect":
            c.setStrokeColor(color)
            c.setLineWidth(float(e.get("width", 2)))
            if e.get("fill"):
                c.setFillColor(color)
            c.rect(e["x"], e["y"], e["w"], e["h"], stroke=1, fill=1 if e.get("fill") else 0)
        elif kind == "highlight":
            c.setFillColor(color, alpha=0.35)
            c.rect(e["x"], e["y"], e["w"], e["h"], stroke=0, fill=1)
        elif kind in ("ink", "line"):
            pts = e["points"]
            if len(pts) >= 2:
                c.setStrokeColor(color)
                c.setLineWidth(float(e.get("width", 2)))
                c.setLineCap(1); c.setLineJoin(1)
                path = c.beginPath()
                path.moveTo(*pts[0])
                for p in pts[1:]:
                    path.lineTo(*p)
                c.drawPath(path, stroke=1, fill=0)
        elif kind == "image":
            c.drawImage(ImageReader(str(e["path"])), e["x"], e["y"], e["w"], e["h"], mask="auto", preserveAspectRatio=True)
        c.restoreState()


def apply_edits(src: Path, edits: list[dict], tag: str = "-edited", password: str = "") -> Path:
    """Stamp edits onto the pages. Pages with redactions are flattened so the
    covered text and images are gone, not just hidden."""
    import pypdfium2 as pdfium

    reader = open_reader(src, password)
    writer = PdfWriter(clone_from=reader)
    by_page: dict[int, list[dict]] = {}
    for e in edits:
        by_page.setdefault(int(e["page"]), []).append(e)

    doc = None
    for index, page_edits in sorted(by_page.items()):
        if not 0 <= index < len(writer.pages):
            raise ValueError(f"Page {index + 1} does not exist")
        page = writer.pages[index]
        box = page.mediabox
        ox, oy, w, h = float(box.left), float(box.bottom), float(box.width), float(box.height)
        redactions = [e for e in page_edits if e["type"] == "redact"]
        marks = [e for e in page_edits if e["type"] != "redact"]

        if redactions:
            doc = doc or pdfium.PdfDocument(src, password=password or None)
            page = _flatten_with_redactions(writer, index, doc, redactions, ox, oy, w, h)

        if marks:
            stamp = overlay_page(w, h, lambda c, *_: _draw_edits(c, [{**m, "x": m.get("x", 0) - ox, "y": m.get("y", 0) - oy,
                                                                     "points": [[px - ox, py - oy] for px, py in m.get("points", [])]}
                                                                    for m in marks])).pages[0]
            page.merge_transformed_page(stamp, Transformation().translate(ox, oy))
    if doc is not None:
        doc.close()
        # Drop the replaced page content entirely, so redacted text is not left in the file.
        writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    return write(writer, beside(src, ".pdf", tag))


def _flatten_with_redactions(writer: PdfWriter, index: int, doc, redactions, ox, oy, w, h):
    """Replace the page with an image of itself, with black boxes burned in."""
    from reportlab.lib.utils import ImageReader

    scale = 200 / 72  # 200 DPI keeps text crisp when printed
    rot = writer.pages[index].rotation
    img = doc[index].render(scale=scale, rotation=0, may_draw_forms=True).to_pil().convert("RGB")
    draw = ImageDraw.Draw(img)
    H = img.height
    for r in redactions:
        x0 = (r["x"] - ox) * scale
        x1 = (r["x"] - ox + r["w"]) * scale
        y1 = H - (r["y"] - oy) * scale
        y0 = H - (r["y"] - oy + r["h"]) * scale
        draw.rectangle([min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)], fill="black")

    flat = overlay_page(w, h, lambda c, *_: c.drawImage(ImageReader(img), 0, 0, w, h)).pages[0]
    blank = writer.pages[index]
    # Wipe the original content and resources, then draw the flattened image.
    blank[NameObject("/Contents")] = writer._add_object(StreamObject())
    blank[NameObject("/Resources")] = DictionaryObject()
    for key in ("/Annots", "/Thumb"):
        if key in blank:
            del blank[key]
    blank.merge_transformed_page(flat, Transformation().translate(ox, oy))
    if rot:
        blank.rotation = rot
    return blank


# ── Organize ──────────────────────────────────────────────────

def organize(src: Path, plan: list[dict], password: str = "") -> Path:
    """Rebuild a PDF from a page plan: [{"source": 2, "rotate": 90}, {"blank": True}, ...]."""
    reader = open_reader(src, password)
    writer = PdfWriter()
    last_size = (595.28, 841.89)
    for item in plan:
        if item.get("blank"):
            writer.add_blank_page(*last_size)
            continue
        page = writer.add_page(reader.pages[int(item["source"])])
        last_size = (float(page.mediabox.width), float(page.mediabox.height))
        if item.get("rotate"):
            page.rotate(int(item["rotate"]))
    if not writer.pages:
        raise ValueError("The document would have no pages")
    return write(writer, beside(src, ".pdf", "-organized"))


# ── Forms ─────────────────────────────────────────────────────

def form_fields(src: Path) -> dict[str, dict]:
    """Fillable fields: name → {"value", "type", "options"}."""
    reader = open_reader(src)
    fields = reader.get_fields() or {}
    out = {}
    for name, f in fields.items():
        ft = f.get("/FT")
        if ft not in ("/Tx", "/Btn", "/Ch"):
            continue
        states = []
        if ft == "/Btn":
            for kid in [f] + [k.get_object() for k in f.get("/Kids", [])]:
                ap = kid.get("/AP", {}).get("/N", {})
                states += [str(k) for k in ap.keys() if str(k) != "/Off"]
        out[name] = {"value": f.get("/V", ""), "type": {"/Tx": "text", "/Btn": "check", "/Ch": "choice"}[ft],
                     "options": [str(o) for o in f.get("/Opt", [])] if ft == "/Ch" else states}
    return out


def fill_form(src: Path, values: dict[str, str], flatten: bool = False) -> Path:
    reader = open_reader(src)
    writer = PdfWriter(clone_from=reader)
    for page in writer.pages:
        writer.update_page_form_field_values(page, values, auto_regenerate=False, flatten=flatten)
    writer.set_need_appearances_writer(True)
    return write(writer, beside(src, ".pdf", "-filled"))


# ── OCR ───────────────────────────────────────────────────────

def ocr(src: Path, language: str = "eng", dpi: int = 300) -> Path:
    """Make a scanned PDF searchable: each page becomes image + invisible text (Tesseract)."""
    import pypdfium2 as pdfium
    exe = tools.find("tesseract")
    if not exe:
        raise tools.ToolError("OCR needs Tesseract installed")
    doc = pdfium.PdfDocument(src)
    writer = PdfWriter()
    with tempfile.TemporaryDirectory() as tmp:
        for i in range(len(doc)):
            png = Path(tmp, f"p{i}.png")
            doc[i].render(scale=dpi / 72).to_pil().convert("RGB").save(png, dpi=(dpi, dpi))
            base = Path(tmp, f"p{i}")
            tools.run([exe, str(png), str(base), "-l", language, "--dpi", str(dpi), "pdf"], timeout=600)
            page = PdfReader(str(base) + ".pdf").pages[0]
            w0, h0 = doc[i].get_size()
            sx, sy = w0 / float(page.mediabox.width), h0 / float(page.mediabox.height)
            if abs(sx - 1) > 0.01 or abs(sy - 1) > 0.01:
                page.scale(sx, sy)
            writer.add_page(page)
    doc.close()
    return write(writer, beside(src, ".pdf", "-ocr"))


def ocr_languages() -> list[str]:
    exe = tools.find("tesseract")
    if not exe:
        return []
    import subprocess
    out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True).stdout.splitlines()
    return [l.strip() for l in out[1:] if l.strip() and l.strip() != "osd"]


# ── Signatures ────────────────────────────────────────────────

def text_signature(name: str, dest: Path, color: str = "#1a2b6d") -> Path:
    """Render a typed name as a signature image (transparent PNG)."""
    from PIL import ImageFont
    font = None
    for candidate in ("DejaVuSerif-Italic.ttf", "Z003-MediumItalic.otf", "Inkfree.ttf", "segoesc.ttf",
                      "LiberationSerif-Italic.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf"):
        try:
            font = ImageFont.truetype(candidate, 120)
            break
        except OSError:
            continue
    font = font or ImageFont.load_default(120)
    left, top, right, bottom = font.getbbox(name)
    img = Image.new("RGBA", (right - left + 40, bottom - top + 40), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((20 - left, 20 - top), name, font=font, fill=color)
    img.save(dest)
    return dest


def clean_signature_image(src: Path, dest: Path) -> Path:
    """Photo of a signature on paper → transparent PNG of just the ink."""
    img = Image.open(src).convert("L")
    img.thumbnail((1600, 1600))
    hist, half, seen = img.histogram(), img.width * img.height / 2, 0
    median = next(v for v in range(256) if (seen := seen + hist[v]) >= half)
    threshold = median - 40  # ink is clearly darker than the paper
    alpha = img.point(lambda v: 255 if v < threshold else 0)
    ink = Image.new("RGBA", img.size, (26, 43, 109, 0))
    ink.putalpha(alpha)
    box = alpha.getbbox()
    (ink.crop(box) if box else ink).save(dest)
    return dest
