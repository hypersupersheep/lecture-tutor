import json

import pytest

from fixtures.make_pdf import make_pdf
from tutor_any_lecture.acquire.importer import import_transcript
from tutor_any_lecture.cli import main
from tutor_any_lecture.slides import Page, extract_pdf, load_pages, max_label, slide_terms, term_list
from tutor_any_lecture.source import sha256_file
from tutor_any_lecture.transcript import AcquireError
from tutor_any_lecture.unit import UnitPaths


def test_labels_from_footer(tmp_path):
    pdf = make_pdf(tmp_path, ["Compound interest\n1/3", "Discounting\n2/3", "Summary\n3/3"])
    pages = extract_pdf(pdf, tmp_path)
    assert [p.label for p in pages] == ["1", "2", "3"] and max_label(pages) == 3


def test_no_labels_falls_back_to_count(tmp_path):
    pages = extract_pdf(make_pdf(tmp_path, ["a", "b"]), tmp_path)
    assert max_label(pages) == 2


def test_slide_terms_limit():
    assert len(slide_terms([Page(1, None, "Black-Scholes GBM martingale " * 30)], 200)) <= 200


def test_max_label_counts_unlabelled_page_by_position():
    pages = [Page(1, "1", "a\n1/2"), Page(2, "2", "b\n2/2"), Page(3, None, "Appendix")]
    assert max_label(pages) == 3
    assert max_label([]) == 0


def test_term_list_order_dedup_and_footer():
    page = Page(1, "1", "martingale pricing under Black-Scholes\nGBM paths, Martingale\n1/3")
    assert term_list([page]) == ["Black-Scholes", "GBM", "martingale", "pricing"]


def test_term_list_unclassed_token_does_not_block_later_spelling():
    assert term_list([Page(1, None, "gbm GBM")]) == ["GBM"]


def test_slide_terms_cut_at_term_boundary():
    page = Page(1, None, "Black-Scholes GBM martingale")
    assert slide_terms([page], 200) == "Black-Scholes, GBM, martingale"
    assert slide_terms([page], 20) == "Black-Scholes, GBM"
    assert slide_terms([page], 5) == ""
    assert slide_terms([]) == ""


def test_pages_json_roundtrip(tmp_path):
    assert load_pages(tmp_path) == []
    pages = extract_pdf(make_pdf(tmp_path, ["Compound interest\n1/2", "Summary"]), tmp_path)
    assert pages == [Page(1, "1", "Compound interest\n1/2"), Page(2, None, "Summary")]
    assert load_pages(tmp_path) == pages
    stored = json.loads(UnitPaths(tmp_path).pages.read_text(encoding="utf-8"))
    assert stored[1] == {"n": 2, "label": None, "text": "Summary", "image": None}


def test_source_json_written_when_absent(tmp_path):
    pdf = make_pdf(tmp_path / "课程 资料", ["Compound interest\n1/2", "Discounting\n2/2"])
    unit = tmp_path / "课程 资料" / "第1周"
    extract_pdf(pdf, unit)
    src = json.loads(UnitPaths(unit).source.read_text(encoding="utf-8"))
    assert src["kind"] == "slides-only" and src["acquisition"] == "slides"
    assert src["title"] == "slides" and src["duration"] is None and src["health"] == {}
    assert src["inputs_sha256"] == {"slides.pdf": sha256_file(pdf)}
    assert "pdfplumber" in src["tool_versions"]


def test_source_json_untouched_when_present(tmp_path):
    paths = UnitPaths(tmp_path / "unit")
    paths.ensure()
    sentinel = b'{"kind": "transcript"}\n'
    paths.source.write_bytes(sentinel)
    extract_pdf(make_pdf(tmp_path, ["a", "b"]), tmp_path / "unit")
    assert paths.source.read_bytes() == sentinel
    assert len(load_pages(tmp_path / "unit")) == 2


def test_images_written(tmp_path):
    pages = extract_pdf(make_pdf(tmp_path, ["a", "b"]), tmp_path, images=True)
    assert [p.image for p in pages] == ["page-001.png", "page-002.png"]
    slides_dir = UnitPaths(tmp_path).pages.parent
    assert all((slides_dir / p.image).stat().st_size > 0 for p in pages)


def test_cli_slides_pdf(tmp_path, capsys):
    pdf = make_pdf(tmp_path, ["Compound interest\n1/3", "Discounting\n2/3", "Summary"])
    unit = tmp_path / "unit"
    assert main(["slides", "--pdf", str(pdf), "--unit", str(unit)]) == 0
    assert json.loads(capsys.readouterr().out) == {"status": "ok", "pages": 3, "labelled": 2}
    assert [p.label for p in load_pages(unit)] == ["1", "2", None]


def test_cli_slides_usage(tmp_path, capsys):
    for argv in (["slides"], ["slides", "--pdf", str(tmp_path / "x.pdf")]):
        assert main(argv) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        lines = captured.err.splitlines()
        assert len(lines) == 1
        assert "slides --pdf" in lines[0] and "slides suspects" in lines[0]


def test_cli_slides_missing_pdf(tmp_path):
    unit = tmp_path / "unit"
    assert main(["slides", "--pdf", str(tmp_path / "missing.pdf"), "--unit", str(unit)]) == 1
    assert not unit.exists()


def test_not_a_pdf_is_acquire_error_and_writes_nothing(tmp_path):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"not a pdf")
    unit = tmp_path / "unit"
    with pytest.raises(AcquireError) as exc:
        extract_pdf(pdf, unit)
    assert str(exc.value) == "notes.pdf is not a readable PDF"
    assert exc.value.__cause__ is not None
    assert not unit.exists()


def test_cli_slides_not_a_pdf_exits_1(tmp_path, capsys):
    pdf = tmp_path / "notes.pdf"
    pdf.write_bytes(b"not a pdf")
    unit = tmp_path / "unit"
    assert main(["slides", "--pdf", str(pdf), "--unit", str(unit)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.splitlines() == ["notes.pdf is not a readable PDF"]
    assert not unit.exists()


def test_cli_slides_pdf_with_suspects_is_usage(tmp_path, capsys):
    pdf = make_pdf(tmp_path, ["Compound interest\n1/1"])
    a = tmp_path / "A"
    b = tmp_path / "B"
    vtt = tmp_path / "lecture.vtt"
    vtt.write_text("WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nCompound interes\n", encoding="utf-8", newline="\n")
    import_transcript(vtt, b, None, False)   # so that "suspects --unit B" could have run
    before = sorted(p.relative_to(b) for p in b.rglob("*"))
    assert main(["slides", "--pdf", str(pdf), "--unit", str(a), "suspects", "--unit", str(b)]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert len(lines) == 1 and "slides --pdf" in lines[0] and "slides suspects" in lines[0]
    assert not a.exists()
    assert sorted(p.relative_to(b) for p in b.rglob("*")) == before
    assert not UnitPaths(b).suspects.exists()


def test_render_failure_is_acquire_error(monkeypatch, tmp_path):
    import pdfplumber.page

    def broken_render(self, *args, **kwargs):
        raise OSError("renderer crashed")

    monkeypatch.setattr(pdfplumber.page.Page, "to_image", broken_render)
    pdf = make_pdf(tmp_path, ["a", "b"])
    with pytest.raises(AcquireError) as exc:
        extract_pdf(pdf, tmp_path / "unit", images=True)
    assert str(exc.value).startswith("could not render page 1 of")
    assert str(exc.value) == "could not render page 1 of slides.pdf"
    assert isinstance(exc.value.__cause__, OSError)
