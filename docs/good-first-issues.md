# Good first issues

Small, well-scoped tasks for new contributors. Each one is a real gap in Swirl today. Comment on
the matching GitHub issue (or open one) before you start, then see
[CONTRIBUTING.md](../CONTRIBUTING.md) for setup.

## Easy

### 1. HEIC photos are offered but can't be opened
`engine.KINDS["image"]` lists `.heic`, so the wheel offers conversions for iPhone photos, but
Pillow can't read HEIC on its own and the conversion fails. Add the optional
[`pillow-heif`](https://pypi.org/project/pillow-heif/) package (register its opener in
`engine._open_image`); if it isn't installed, show a clear "install pillow-heif" note like other
missing engines. Add a test that skips when `pillow_heif` is missing.
*Files:* `swirl/engine.py`, `pyproject.toml`, `tests/test_engine.py`

### 2. CSV to Excel and PDF from the wheel
`openpyxl` is already a dependency. Add a `"table"` kind for `.csv` / `.tsv` and wheel actions
*XLSX* (numbers stay numbers, like *PDF → Excel*) and *PDF* (via LibreOffice, `needs=("soffice",)`).
*Files:* `swirl/engine.py`, `tests/test_engine.py`

### 3. EPUB to PDF, DOCX and Markdown
Pandoc already reads EPUB. Add `.epub` to a kind and reuse `_pandoc_to(...)` for the wheel actions.
*Files:* `swirl/engine.py`, `tests/test_engine.py` (skip when Pandoc is missing)

### 4. Install instructions for Fedora and Arch
The README covers Ubuntu and Windows. Document running from source on Fedora (`dnf`) and Arch
(`pacman`), including the optional engines and `swirl --install` for the right-click menu. Try it on
a real machine or container and note anything that breaks.
*Files:* `README.md`

## Medium

### 5. Flatten PDF forms
Add a Studio tool that bakes filled form fields into the page so they can't be edited any more
(useful before sending a signed form). pypdf can do this; follow the *Add a Studio PDF tool*
steps in CONTRIBUTING.
*Files:* `swirl/pdftools.py`, `tests/test_pdftools.py`

### 6. Grayscale PDF
A Studio tool that converts a PDF to black and white for printing, with a choice between keeping
text selectable (where possible) and rasterising pages with `pypdfium2`.
*Files:* `swirl/pdftools.py`, `tests/test_pdftools.py`

### 7. Tests for the command line
`swirl --run`, `--set` and `--list` in `swirl/__main__.py` have no tests. Add tests that run a tool
through `main([...])` and check the output file and the error for an unknown option.
*Files:* `tests/test_cli.py` (new)

## Bigger (help wanted)

### 8. macOS support
Swirl is pure Python plus Qt, so most of it should run on macOS. Needed: a Finder Quick Action for
*Convert with Swirl* in `swirl/integrate.py`, Homebrew hints in `swirl/tools.py`, a macOS job in CI,
and a `.app` build with PyInstaller.
