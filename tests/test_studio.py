import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication
from pypdf import PdfReader

from swirl import pdftools
from swirl.studio import Home, Studio, ToolPage

from .test_pdftools import make_report


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_home_lists_and_filters_tools(app):
    home = Home()
    assert home.grid.count() == len(pdftools.TOOLS)
    home.set_category("Security")
    assert home.grid.count() == sum(t.category == "Security" for t in pdftools.TOOLS)
    home.set_category("All")
    home.search.setText("compress")
    assert home.grid.count() == 1


def test_every_tool_page_builds_its_form(app):
    for tool in pdftools.TOOLS:
        page = ToolPage(tool)
        assert set(page.values()) == {o.key for o in tool.options}


def test_tool_page_runs_with_form_values(app, tmp_path):
    a = make_report(tmp_path / "a.pdf", 3)
    page = ToolPage(pdftools.TOOL_BY_ID["split"], [a])
    assert page.run_btn.isEnabled()
    page.inputs["mode"].setCurrentText("Every N pages")
    page.inputs["every"].setText("2")
    out = pdftools.run_tool(page.tool, page.files.paths(), page.values())
    assert [len(PdfReader(p).pages) for p in out] == [2, 1]


def test_merge_needs_two_files(app, tmp_path):
    page = ToolPage(pdftools.TOOL_BY_ID["merge"], [make_report(tmp_path / "only.pdf", 1)])
    assert not page.run_btn.isEnabled()
    assert "at least 2" in page.status.text()


def test_studio_opens_a_tool_directly(app, tmp_path):
    a = make_report(tmp_path / "a.pdf", 1)
    w = Studio([a], "compress")
    page = w.stack.currentWidget()
    assert isinstance(page, ToolPage) and page.files.paths() == [a]
