# Contributing to Swirl

Thanks for helping! Swirl is a small, readable Python codebase, so most changes touch one or two
files. New contributors are very welcome: look for issues labelled
[`good first issue`](https://github.com/anascs12/swirl/labels/good%20first%20issue), or pick one
from [docs/good-first-issues.md](docs/good-first-issues.md).

If you want to work on something, comment on the issue so nobody else starts the same thing.
For larger ideas, open an issue first so we can agree on the approach before you write code.

## Set up

```bash
git clone https://github.com/<you>/swirl && cd swirl
python3 -m venv .venv && . .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest                                  # all tests should pass
python -m swirl                                   # run Swirl Studio from source
```

Optional engines (FFmpeg, LibreOffice, Pandoc, Tesseract) unlock more conversions. Tests that need a
missing engine are skipped, not failed. `python -m swirl --check` shows what you have.

## Where things live

| File | What it does |
|---|---|
| `swirl/engine.py` | Wheel conversions. Each entry in `ACTIONS` is an `Action` (images, PDF, video, audio, documents, notebooks). |
| `swirl/pdftools.py` | Studio PDF tools. Each entry in `TOOLS` is a `Tool` with its `Option`s; the Studio builds the settings form from them. |
| `swirl/pdfedit.py`, `swirl/editor.py` | The page editor (text, highlight, sign, redact, organize). |
| `swirl/studio.py` | Swirl Studio window. |
| `swirl/wheel.py`, `swirl/bubble.py` | The format wheel and the floating drop target. |
| `swirl/tools.py` | Finding and running external programs (`find`, `run`, `ToolError`). |
| `swirl/integrate.py` | Right-click menu integration for Linux file managers and Windows. |
| `tests/` | pytest suite; `test_engine.py` for the wheel, `test_pdftools.py` for Studio tools. |

## Common changes

**Add a Studio PDF tool.** Write a function `def my_tool(files, o) -> list[Path]` in
`swirl/pdftools.py` (`o` is the dict of option values), save results with `beside(...)` so the
original is never overwritten, and add a `Tool(...)` entry to `TOOLS`. The Studio and
`swirl --run my-tool` pick it up automatically. Add a test in `tests/test_pdftools.py`;
`make_report()` builds a sample PDF for you.

**Add a wheel conversion.** Write a function in `swirl/engine.py` that takes a list of paths and
returns the new paths, then add an `Action(...)` to `ACTIONS`. If it needs an external program, set
`needs=("ffmpeg",)` so Swirl shows a note instead of failing when it is missing.

## Rules of the house

- **Never change the user's files.** Results go beside the original with a new name.
- **No network code.** Everything runs locally; that is a promise in the README.
- Match the surrounding style: short functions, plain names, comments only where the *why* isn't obvious.
- Keep pull requests focused: one fix or feature per PR is easiest to review.
- Run `python -m pytest` before pushing. CI runs the same tests on Ubuntu and Windows.

## Sending a pull request

1. Fork the repo and create a branch (`git checkout -b fix-heic-images`).
2. Make the change and add or update a test.
3. Push and open a pull request; the template will ask what changed and how you tested it.
4. A maintainer will review, usually within a few days. Small follow-up changes are normal.

Thank you for contributing. Your name goes in the Contributors table once your first PR is merged.
