"""What can be done to a set of files, and doing it.

Every action writes new files beside the originals and never modifies or
overwrites an existing file.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

from . import tools

KINDS = {
    "image":    {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".ico", ".heic", ".avif"},
    "pdf":      {".pdf"},
    "video":    {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".wmv", ".flv"},
    "audio":    {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"},
    "document": {".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp", ".xlsx", ".xls", ".ods"},
    "text":     {".txt", ".md", ".markdown", ".html", ".htm"},
}


def kind_of(path: Path) -> str | None:
    ext = path.suffix.lower()
    return next((k for k, exts in KINDS.items() if ext in exts), None)


def free_path(directory: Path, stem: str, suffix: str) -> Path:
    """A path in `directory` that does not exist yet: 'name.png', then 'name (1).png'…"""
    candidate = directory / f"{stem}{suffix}"
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def beside(src: Path, suffix: str, tag: str = "") -> Path:
    return free_path(src.parent, src.stem + tag, suffix)


@dataclass
class Action:
    id: str
    label: str
    group: str                       # "convert" (format wheel) or "tool"
    kinds: set[str]                  # file kinds it accepts
    run: Callable[[list[Path]], list[Path]]
    needs: tuple[str, ...] = ()      # external programs required
    multi: bool = False              # works on several files together (merge)
    per_file: bool = True            # run once per file
    skip_same_ext: tuple[str, ...] = field(default_factory=tuple)

    def available(self) -> bool:
        return all(tools.find(n) for n in self.needs)

    def missing(self) -> list[str]:
        return [n for n in self.needs if not tools.find(n)]


# ── Images ────────────────────────────────────────────────────

_PIL_FORMAT = {".jpg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".bmp": "BMP",
               ".gif": "GIF", ".tiff": "TIFF", ".ico": "ICO", ".pdf": "PDF"}


def _open_image(src: Path) -> Image.Image:
    img = Image.open(src)
    return ImageOps.exif_transpose(img)  # respect camera rotation


def _image_to(suffix: str):
    def run(files: list[Path]) -> list[Path]:
        out = []
        for src in files:
            img = _open_image(src)
            if suffix in (".jpg", ".bmp", ".pdf") and img.mode not in ("RGB", "L"):
                bg = Image.new("RGB", img.size, "white")
                rgba = img.convert("RGBA")
                bg.paste(rgba, mask=rgba.getchannel("A"))
                img = bg
            dest = beside(src, suffix)
            kwargs = {"quality": 92} if suffix in (".jpg", ".webp") else {}
            if suffix == ".ico":
                kwargs = {"sizes": [(s, s) for s in (16, 32, 48, 64, 128, 256) if s <= max(img.size)] or [(16, 16)]}
            img.save(dest, _PIL_FORMAT[suffix], **kwargs)
            out.append(dest)
        return out
    return run


def compress_images(files: list[Path]) -> list[Path]:
    out = []
    for src in files:
        img = _open_image(src)
        if max(img.size) > 2560:
            img.thumbnail((2560, 2560))
        if src.suffix.lower() == ".png" and img.mode in ("RGBA", "LA", "P"):
            dest = beside(src, ".png", "-compressed")
            img.convert("RGBA").quantize(colors=256, method=Image.Quantize.FASTOCTREE).save(dest, optimize=True)
        else:
            dest = beside(src, ".jpg", "-compressed")
            img.convert("RGB").save(dest, "JPEG", quality=72, optimize=True, progressive=True)
        out.append(dest)
    return out


def strip_image_metadata(files: list[Path]) -> list[Path]:
    """Re-encode pixels only, dropping EXIF (GPS location, camera, dates)."""
    out = []
    for src in files:
        img = _open_image(src)
        clean = Image.frombytes(img.mode, img.size, img.tobytes())
        if img.mode == "P":
            clean.putpalette(img.getpalette())
        suffix = ".jpg" if src.suffix.lower() == ".jpeg" else src.suffix.lower()
        fmt = _PIL_FORMAT.get(suffix, "PNG")
        dest = beside(src, suffix if suffix in _PIL_FORMAT else ".png", "-clean")
        clean.save(dest, fmt, **({"quality": 95} if fmt == "JPEG" else {}))
        out.append(dest)
    return out


def half_size(files: list[Path]) -> list[Path]:
    out = []
    for src in files:
        img = _open_image(src)
        img = img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.Resampling.LANCZOS)
        suffix = ".jpg" if src.suffix.lower() == ".jpeg" else src.suffix.lower()
        dest = beside(src, suffix, "-half")
        img.save(dest, _PIL_FORMAT.get(suffix, "PNG"))
        out.append(dest)
    return out


def images_to_one_pdf(files: list[Path]) -> list[Path]:
    pages = [_open_image(f).convert("RGB") for f in files]
    dest = beside(files[0], ".pdf", "-combined")
    pages[0].save(dest, "PDF", save_all=True, append_images=pages[1:], resolution=150)
    return [dest]


# ── PDF ───────────────────────────────────────────────────────

def _pdf_to_images(suffix: str, scale: float = 2.0):
    def run(files: list[Path]) -> list[Path]:
        import pypdfium2 as pdfium
        out = []
        for src in files:
            doc = pdfium.PdfDocument(src)
            for i in range(len(doc)):
                img = doc[i].render(scale=scale).to_pil()
                tag = f"-page{i + 1}" if len(doc) > 1 else ""
                dest = beside(src, suffix, tag)
                img.convert("RGB").save(dest, _PIL_FORMAT[suffix], **({"quality": 90} if suffix == ".jpg" else {}))
                out.append(dest)
            doc.close()
        return out
    return run


def pdf_to_text(files: list[Path]) -> list[Path]:
    from pypdf import PdfReader
    out = []
    for src in files:
        text = "\n\n".join((p.extract_text() or "") for p in PdfReader(src).pages)
        dest = beside(src, ".txt")
        dest.write_text(text, encoding="utf-8")
        out.append(dest)
    return out


def merge_pdfs(files: list[Path]) -> list[Path]:
    from pypdf import PdfWriter
    writer = PdfWriter()
    for f in files:
        writer.append(f)
    dest = beside(files[0], ".pdf", "-merged")
    with open(dest, "wb") as fh:
        writer.write(fh)
    return [dest]


def split_pdf(files: list[Path]) -> list[Path]:
    from pypdf import PdfReader, PdfWriter
    out = []
    for src in files:
        reader = PdfReader(src)
        for i, page in enumerate(reader.pages):
            writer = PdfWriter()
            writer.add_page(page)
            dest = beside(src, ".pdf", f"-page{i + 1}")
            with open(dest, "wb") as fh:
                writer.write(fh)
            out.append(dest)
    return out


def compress_pdf(files: list[Path]) -> list[Path]:
    from pypdf import PdfWriter
    out = []
    for src in files:
        writer = PdfWriter(clone_from=src)
        for page in writer.pages:
            for img in page.images:
                try:
                    img.replace(img.image, quality=60)
                except Exception:
                    pass  # leave images pypdf cannot re-encode untouched
            page.compress_content_streams()
        writer.compress_identical_objects()  # duplicates and unreferenced objects
        dest = beside(src, ".pdf", "-compressed")
        with open(dest, "wb") as fh:
            writer.write(fh)
        out.append(dest)
    return out


def strip_pdf_metadata(files: list[Path]) -> list[Path]:
    from pypdf import PdfWriter
    out = []
    for src in files:
        writer = PdfWriter(clone_from=src)
        writer.metadata = None
        if "/Metadata" in writer.root_object:
            del writer.root_object["/Metadata"]  # XMP packet
        dest = beside(src, ".pdf", "-clean")
        with open(dest, "wb") as fh:
            writer.write(fh)
        out.append(dest)
    return out


# ── Video and audio (FFmpeg) ──────────────────────────────────

_FFMPEG_ARGS = {
    ".mp4":  ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "-pix_fmt", "yuv420p"],
    ".webm": ["-c:v", "libvpx-vp9", "-crf", "33", "-b:v", "0", "-c:a", "libopus", "-b:a", "128k"],
    ".mov":  ["-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-pix_fmt", "yuv420p"],
    ".mp3":  ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
    ".wav":  ["-vn", "-c:a", "pcm_s16le"],
    ".ogg":  ["-vn", "-c:a", "libvorbis", "-q:a", "5"],
    ".flac": ["-vn", "-c:a", "flac"],
    ".m4a":  ["-vn", "-c:a", "aac", "-b:a", "192k"],
}


def _ffmpeg_to(suffix: str):
    def run(files: list[Path]) -> list[Path]:
        out = []
        for src in files:
            dest = beside(src, suffix)
            tools.run([tools.find("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                       *_FFMPEG_ARGS[suffix], str(dest)])
            out.append(dest)
        return out
    return run


def video_to_gif(files: list[Path]) -> list[Path]:
    out = []
    for src in files:
        dest = beside(src, ".gif")
        vf = "fps=12,scale='min(640,iw)':-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse"
        tools.run([tools.find("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                   "-vf", vf, "-loop", "0", str(dest)])
        out.append(dest)
    return out


def compress_video(files: list[Path]) -> list[Path]:
    out = []
    for src in files:
        dest = beside(src, ".mp4", "-compressed")
        tools.run([tools.find("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                   "-vf", "scale='min(1280,iw)':-2", "-c:v", "libx264", "-preset", "slow", "-crf", "28",
                   "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(dest)])
        out.append(dest)
    return out


def mute_video(files: list[Path]) -> list[Path]:
    out = []
    for src in files:
        dest = beside(src, src.suffix.lower(), "-muted")
        tools.run([tools.find("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                   "-c:v", "copy", "-an", str(dest)])
        out.append(dest)
    return out


def strip_media_metadata(files: list[Path]) -> list[Path]:
    out = []
    for src in files:
        dest = beside(src, src.suffix.lower(), "-clean")
        tools.run([tools.find("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                   "-map_metadata", "-1", "-map_chapters", "-1", "-c", "copy", str(dest)])
        out.append(dest)
    return out


# ── Documents (LibreOffice, Pandoc) ───────────────────────────

def _office_to(fmt: str, suffix: str):
    def run(files: list[Path]) -> list[Path]:
        out = []
        with tempfile.TemporaryDirectory() as tmp:
            # A private profile lets conversions run while LibreOffice is open.
            profile = Path(tmp, "profile").resolve().as_uri()
            for src in files:
                tools.run([tools.find("soffice"), f"-env:UserInstallation={profile}", "--headless",
                           "--convert-to", fmt, "--outdir", tmp, str(src)], timeout=300)
                produced = Path(tmp, src.stem + suffix)
                if not produced.exists():
                    raise tools.ToolError(f"LibreOffice produced no {suffix} for {src.name}")
                dest = beside(src, suffix)
                shutil.move(str(produced), dest)
                out.append(dest)
        return out
    return run


def _pandoc_to(suffix: str):
    def run(files: list[Path]) -> list[Path]:
        out = []
        for src in files:
            dest = beside(src, suffix)
            tools.run([tools.find("pandoc"), str(src), "-s", "-o", str(dest)])
            out.append(dest)
        return out
    return run


def text_to_pdf(files: list[Path]) -> list[Path]:
    """Text → PDF through LibreOffice (Pandoc's PDF route needs a LaTeX install)."""
    out = []
    for src in files:
        if src.suffix.lower() in (".md", ".markdown") and tools.find("pandoc"):
            with tempfile.TemporaryDirectory() as tmp:
                html = Path(tmp, src.stem + ".html")
                tools.run([tools.find("pandoc"), str(src), "-s", "-o", str(html)])
                result = _office_to("pdf", ".pdf")([html])[0]
                dest = beside(src, ".pdf")
                shutil.move(str(result), dest)
                out.append(dest)
        else:
            out.extend(_office_to("pdf", ".pdf")([src]))
    return out


def open_studio(files: list[Path]) -> list[Path]:
    """Hand the files to Swirl Studio for tools that need settings."""
    import subprocess
    import sys
    from .integrate import launch_command
    from .tools import child_env
    env = child_env()
    if getattr(sys, "frozen", False):
        # Starting ourselves again: keep the bundle's libraries.
        env = dict(__import__("os").environ)
    subprocess.Popen([*launch_command(), "--studio", *map(str, files)], env=env,
                     creationflags=0x00000008 if sys.platform == "win32" else 0,  # detached on Windows
                     start_new_session=sys.platform != "win32")
    return []


# ── Mixed selections (e.g. a Word file and two PDFs) ──────────

PDF_ABLE = {"pdf", "image", "document", "text"}


def _to_pdf(src: Path, workdir: Path) -> Path:
    """A PDF version of `src`, made inside `workdir` (PDFs are used as they are)."""
    kind = kind_of(src)
    if kind == "pdf":
        return src
    if kind in ("document", "text") and not tools.find("soffice"):
        raise tools.ToolError(f"{src.name} needs LibreOffice installed")
    copy = free_path(workdir, src.stem, src.suffix)
    shutil.copy2(src, copy)
    if kind == "image":
        dest = beside(copy, ".pdf")
        _open_image(copy).convert("RGB").save(dest, "PDF", resolution=150)
        return dest
    return (text_to_pdf if kind == "text" else _office_to("pdf", ".pdf"))([copy])[0]


def mixed_to_pdf(files: list[Path]) -> list[Path]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for src in files:
            if kind_of(src) == "pdf":
                continue
            dest = beside(src, ".pdf")
            shutil.move(str(_to_pdf(src, Path(tmp))), dest)
            out.append(dest)
    return out


def mixed_merge(files: list[Path]) -> list[Path]:
    from pypdf import PdfWriter
    writer = PdfWriter()
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            writer.append(_to_pdf(f, Path(tmp)))
        dest = beside(files[0], ".pdf", "-merged")
        with open(dest, "wb") as fh:
            writer.write(fh)
    return [dest]


# ── Registry ──────────────────────────────────────────────────

ACTIONS: list[Action] = [
    # Images
    *[Action(f"img-{s[1:]}", s[1:].upper(), "convert", {"image"}, _image_to(s), skip_same_ext=(s, ".jpeg") if s == ".jpg" else (s,))
      for s in (".png", ".jpg", ".webp", ".pdf", ".gif", ".bmp", ".tiff", ".ico")],
    Action("img-compress", "Compress", "tool", {"image"}, compress_images),
    Action("img-half", "Half size", "tool", {"image"}, half_size),
    Action("img-strip", "Strip metadata", "tool", {"image"}, strip_image_metadata),
    Action("img-onepdf", "Combine into PDF", "tool", {"image"}, images_to_one_pdf, multi=True, per_file=False),
    # PDF
    Action("pdf-png", "PNG", "convert", {"pdf"}, _pdf_to_images(".png")),
    Action("pdf-jpg", "JPG", "convert", {"pdf"}, _pdf_to_images(".jpg")),
    Action("pdf-txt", "TXT", "convert", {"pdf"}, pdf_to_text),
    Action("pdf-compress", "Compress", "tool", {"pdf"}, compress_pdf),
    Action("pdf-split", "Split pages", "tool", {"pdf"}, split_pdf),
    Action("pdf-merge", "Merge", "tool", {"pdf"}, merge_pdfs, multi=True, per_file=False),
    Action("pdf-strip", "Strip metadata", "tool", {"pdf"}, strip_pdf_metadata),
    Action("pdf-studio", "All PDF tools…", "tool", {"pdf"}, open_studio),
    # Video
    *[Action(f"vid-{s[1:]}", s[1:].upper(), "convert", {"video"}, _ffmpeg_to(s), needs=("ffmpeg",), skip_same_ext=(s,))
      for s in (".mp4", ".webm", ".mov")],
    Action("vid-gif", "GIF", "convert", {"video"}, video_to_gif, needs=("ffmpeg",)),
    Action("vid-mp3", "MP3", "convert", {"video"}, _ffmpeg_to(".mp3"), needs=("ffmpeg",)),
    Action("vid-compress", "Compress", "tool", {"video"}, compress_video, needs=("ffmpeg",)),
    Action("vid-mute", "Remove audio", "tool", {"video"}, mute_video, needs=("ffmpeg",)),
    Action("vid-strip", "Strip metadata", "tool", {"video", "audio"}, strip_media_metadata, needs=("ffmpeg",)),
    # Audio
    *[Action(f"aud-{s[1:]}", s[1:].upper(), "convert", {"audio"}, _ffmpeg_to(s), needs=("ffmpeg",), skip_same_ext=(s,))
      for s in (".mp3", ".wav", ".ogg", ".flac", ".m4a")],
    # Documents
    Action("doc-pdf", "PDF", "convert", {"document"}, _office_to("pdf", ".pdf"), needs=("soffice",)),
    Action("doc-docx", "DOCX", "convert", {"document"}, _office_to("docx", ".docx"), needs=("soffice",), skip_same_ext=(".docx", ".pptx", ".xlsx", ".ppt", ".xls", ".odp", ".ods")),
    Action("doc-odt", "ODT", "convert", {"document"}, _office_to("odt", ".odt"), needs=("soffice",), skip_same_ext=(".odt", ".pptx", ".xlsx", ".ppt", ".xls", ".odp", ".ods")),
    # Text
    Action("txt-pdf", "PDF", "convert", {"text"}, text_to_pdf, needs=("soffice",)),
    Action("txt-docx", "DOCX", "convert", {"text"}, _pandoc_to(".docx"), needs=("pandoc",)),
    # Mixed selections
    Action("mix-pdf", "PDF", "convert", {"mixed"}, mixed_to_pdf),
    Action("mix-merge", "Merge into one PDF", "tool", {"mixed"}, mixed_merge, multi=True, per_file=False),
    Action("txt-html", "HTML", "convert", {"text"}, _pandoc_to(".html"), needs=("pandoc",), skip_same_ext=(".html", ".htm")),
]

BY_ID = {a.id: a for a in ACTIONS}


def actions_for(files: list[Path], group: str | None = None) -> list[Action]:
    """Actions that apply to every file in the selection.

    Files of one kind get that kind's actions; a mix of PDFs, images, documents
    and text gets the "mixed" ones (make PDFs, merge into one PDF).
    """
    kinds = {kind_of(f) for f in files}
    if None in kinds or not kinds:
        return []
    if len(kinds) > 1:
        if not kinds <= PDF_ABLE:
            return []
        kinds = {"mixed"}
    kind = kinds.pop()
    exts = {f.suffix.lower() for f in files}
    result = []
    for a in ACTIONS:
        if kind not in a.kinds or (group and a.group != group):
            continue
        if a.multi and len(files) < 2:
            continue
        if a.skip_same_ext and exts <= set(a.skip_same_ext):
            continue  # don't offer PNG → PNG
        result.append(a)
    return result


def perform(action: Action, files: list[Path]) -> list[Path]:
    missing = action.missing()
    if missing:
        raise tools.ToolError(f"{action.label} needs {', '.join(missing)} installed")
    return action.run(files)
