import subprocess
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from swirl import engine, tools

needs_ffmpeg = pytest.mark.skipif(not tools.find("ffmpeg"), reason="ffmpeg not installed")
needs_office = pytest.mark.skipif(not tools.find("soffice"), reason="LibreOffice not installed")
needs_pandoc = pytest.mark.skipif(not tools.find("pandoc"), reason="pandoc not installed")


@pytest.fixture
def photo(tmp_path) -> Path:
    img = Image.new("RGB", (800, 600), (200, 80, 40))
    exif = Image.Exif()
    exif[0x010F] = "TestCam"                          # Make
    exif[0x8825] = {1: "N", 2: (33.0, 59.0, 0.0)}      # GPS
    path = tmp_path / "photo.jpg"
    img.save(path, exif=exif)
    return path


@pytest.fixture
def logo(tmp_path) -> Path:
    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    img.paste((20, 120, 220, 255), (50, 50, 250, 250))
    path = tmp_path / "logo.png"
    img.save(path)
    return path


def make_pdf(path: Path, pages: int) -> Path:
    imgs = [Image.new("RGB", (400, 500), (255, 255, 255)) for _ in range(pages)]
    imgs[0].save(path, "PDF", save_all=True, append_images=imgs[1:])
    writer = PdfWriter(clone_from=path)
    writer.add_metadata({"/Author": "Secret Person", "/Title": "Draft"})
    with open(path, "wb") as fh:
        writer.write(fh)
    return path


@pytest.fixture
def video(tmp_path) -> Path:
    path = tmp_path / "clip.mp4"
    subprocess.run([tools.find("ffmpeg"), "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=15",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "1.5", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-metadata", "title=Secret", str(path)], check=True)
    return path


@pytest.fixture
def song(tmp_path) -> Path:
    path = tmp_path / "tone.wav"
    subprocess.run([tools.find("ffmpeg"), "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440",
                    "-t", "1", str(path)], check=True)
    return path


def test_kinds_and_menus(tmp_path):
    assert engine.kind_of(Path("a.JPEG")) == "image"
    assert engine.kind_of(Path("a.unknown")) is None
    labels = [a.label for a in engine.actions_for([tmp_path / "x.png"], "convert")]
    assert "PNG" not in labels and "JPG" in labels          # no PNG → PNG
    assert engine.actions_for([tmp_path / "a.png", tmp_path / "b.pdf"]) == []   # mixed kinds
    single = {a.id for a in engine.actions_for([tmp_path / "a.pdf"])}
    double = {a.id for a in engine.actions_for([tmp_path / "a.pdf", tmp_path / "b.pdf"])}
    assert "pdf-merge" not in single and "pdf-merge" in double


def test_never_overwrites(photo):
    first = engine.perform(engine.BY_ID["img-png"], [photo])[0]
    second = engine.perform(engine.BY_ID["img-png"], [photo])[0]
    assert first.name == "photo.png" and second.name == "photo (1).png"
    assert photo.exists()


@pytest.mark.parametrize("action", ["img-png", "img-webp", "img-pdf", "img-gif", "img-bmp", "img-tiff", "img-ico"])
def test_image_conversions(photo, action):
    out = engine.perform(engine.BY_ID[action], [photo])
    assert len(out) == 1 and out[0].stat().st_size > 0


def test_transparent_png_to_jpg_gets_white_background(logo):
    out = engine.perform(engine.BY_ID["img-jpg"], [logo])[0]
    assert Image.open(out).getpixel((5, 5)) == (255, 255, 255)


def test_image_tools(photo, logo):
    clean = engine.perform(engine.BY_ID["img-strip"], [photo])[0]
    assert len(Image.open(photo).getexif()) > 0
    assert len(Image.open(clean).getexif()) == 0
    half = engine.perform(engine.BY_ID["img-half"], [photo])[0]
    assert Image.open(half).size == (400, 300)
    for f in engine.perform(engine.BY_ID["img-compress"], [photo, logo]):
        assert f.exists()
    combined = engine.perform(engine.BY_ID["img-onepdf"], [photo, logo])
    assert len(PdfReader(combined[0]).pages) == 2


def test_pdf_tools(tmp_path):
    a = make_pdf(tmp_path / "a.pdf", 3)
    b = make_pdf(tmp_path / "b.pdf", 2)
    pages = engine.perform(engine.BY_ID["pdf-png"], [a])
    assert [p.name for p in pages] == ["a-page1.png", "a-page2.png", "a-page3.png"]
    assert len(engine.perform(engine.BY_ID["pdf-split"], [a])) == 3
    merged = engine.perform(engine.BY_ID["pdf-merge"], [a, b])[0]
    assert len(PdfReader(merged).pages) == 5
    clean = engine.perform(engine.BY_ID["pdf-strip"], [a])[0]
    assert PdfReader(a).metadata.get("/Author") == "Secret Person"
    assert not (PdfReader(clean).metadata or {}).get("/Author")
    assert engine.perform(engine.BY_ID["pdf-compress"], [a])[0].exists()
    assert engine.perform(engine.BY_ID["pdf-txt"], [a])[0].suffix == ".txt"


@needs_ffmpeg
@pytest.mark.parametrize("action", ["vid-webm", "vid-mov", "vid-gif", "vid-mp3", "vid-compress", "vid-mute", "vid-strip"])
def test_video(video, action):
    out = engine.perform(engine.BY_ID[action], [video])
    assert out[0].stat().st_size > 0


@needs_ffmpeg
@pytest.mark.parametrize("action", ["aud-mp3", "aud-ogg", "aud-flac", "aud-m4a"])
def test_audio(song, action):
    assert engine.perform(engine.BY_ID[action], [song])[0].stat().st_size > 0


@needs_office
@needs_pandoc
def test_documents(tmp_path):
    md = tmp_path / "notes.md"
    md.write_text("# Hello\n\nSome **bold** text.\n")
    docx = engine.perform(engine.BY_ID["txt-docx"], [md])[0]
    assert docx.suffix == ".docx"
    pdf = engine.perform(engine.BY_ID["doc-pdf"], [docx])[0]
    assert "Hello" in PdfReader(pdf).pages[0].extract_text()
    assert engine.perform(engine.BY_ID["txt-pdf"], [md])[0].exists()
    assert engine.perform(engine.BY_ID["doc-odt"], [docx])[0].suffix == ".odt"


def test_missing_tool_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "find", lambda name: None)
    with pytest.raises(tools.ToolError, match="needs ffmpeg"):
        engine.perform(engine.BY_ID["vid-mp3"], [tmp_path / "x.mp4"])


def test_child_processes_get_system_libraries(monkeypatch):
    """A packaged Swirl must not hand its bundled libraries to LibreOffice & co."""
    import sys
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/opt/swirl/_internal")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")
    assert tools.child_env()["LD_LIBRARY_PATH"] == "/usr/local/lib"
    monkeypatch.delenv("LD_LIBRARY_PATH_ORIG")
    assert "LD_LIBRARY_PATH" not in tools.child_env()
    monkeypatch.setattr(sys, "frozen", False)
    assert tools.child_env()["LD_LIBRARY_PATH"] == "/opt/swirl/_internal"   # dev runs untouched
