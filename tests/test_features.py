import zipfile
from pathlib import Path

import fitz
import pytest

from src.cleanup import strip_headers_footers
from src.cli import main as cli_main
from src.converter import (
    ConversionCancelled,
    ConversionOptions,
    convert_many,
    convert_pdf_to_epub,
    read_pdf_metadata,
)
from src.htmlutil import lines_to_html


def _pdf_with_headers(tmp_path: Path) -> Path:
    pdf_path = tmp_path / "headers.pdf"
    doc = fitz.open()
    for i in range(1, 5):
        page = doc.new_page()
        page.insert_text((72, 40), "Mi Novela — Título del libro")
        page.insert_text((72, 72), f"Párrafo de contenido de la página {i} con texto real.")
        page.insert_text((72, 780), f"{i}")
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_strip_headers_footers_removes_repeating_lines():
    pages = [
        "Mi Novela\nContenido A bastante largo para no ser cabecera.\n12",
        "Mi Novela\nContenido B bastante largo para no ser cabecera.\n13",
        "Mi Novela\nContenido C bastante largo para no ser cabecera.\n14",
        "Mi Novela\nContenido D bastante largo para no ser cabecera.\n15",
    ]
    cleaned = strip_headers_footers(pages)
    for page in cleaned:
        assert "Mi Novela" not in page
        assert "Contenido" in page
        assert not page.strip().endswith("12")


def test_convert_strips_headers_from_epub(tmp_path):
    pdf_path = _pdf_with_headers(tmp_path)
    output_path = tmp_path / "headers.epub"
    convert_pdf_to_epub(
        pdf_path,
        output_path,
        ConversionOptions(title="T", strip_headers_footers=True, extract_cover_from_pdf=False),
    )
    with zipfile.ZipFile(output_path) as z:
        xhtml = "\n".join(
            z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xhtml")
        )
    assert "Mi Novela — Título del libro" not in xhtml
    assert "Párrafo de contenido" in xhtml


def test_read_pdf_metadata(tmp_path):
    pdf_path = tmp_path / "meta.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.set_metadata({"title": "El título", "author": "Pérez"})
    doc.save(pdf_path)
    doc.close()
    meta = read_pdf_metadata(pdf_path)
    assert meta.title == "El título"
    assert meta.author == "Pérez"


def test_epub_links_css_and_escapes_title(tmp_path, sample_pdf):
    output_path = tmp_path / "css.epub"
    convert_pdf_to_epub(
        sample_pdf,
        output_path,
        ConversionOptions(
            title='A & B <script>',
            extract_cover_from_pdf=False,
            chapters=[("A & B <script>", "<p>hola</p>")],
            detection_method="manual",
        ),
    )
    with zipfile.ZipFile(output_path) as z:
        names = z.namelist()
        assert any(n.endswith("kobo.css") for n in names)
        chap = z.read("EPUB/chap_001.xhtml").decode("utf-8")
    assert "kobo.css" in chap
    assert "&amp;" in chap
    assert "&lt;script&gt;" in chap
    assert "<script>" not in chap


def test_kepub_wraps_spans(tmp_path, sample_pdf):
    output_path = tmp_path / "book.kepub.epub"
    result = convert_pdf_to_epub(
        sample_pdf,
        output_path,
        ConversionOptions(kepub=True, extract_cover_from_pdf=False),
    )
    assert result.chapter_count == 2
    with zipfile.ZipFile(output_path) as z:
        chap = z.read("EPUB/chap_001.xhtml").decode("utf-8")
    assert 'class="koboSpan"' in chap


def test_extract_cover_from_pdf(tmp_path, sample_pdf):
    output_path = tmp_path / "with_cover.epub"
    convert_pdf_to_epub(
        sample_pdf,
        output_path,
        ConversionOptions(extract_cover_from_pdf=True),
    )
    with zipfile.ZipFile(output_path) as z:
        assert any("cover" in n.lower() for n in z.namelist())


def test_cancel_before_work(tmp_path, sample_pdf):
    with pytest.raises(ConversionCancelled):
        convert_pdf_to_epub(
            sample_pdf,
            tmp_path / "no.epub",
            ConversionOptions(is_cancelled=lambda: True),
        )


def test_cli_converts(tmp_path, sample_pdf):
    out = tmp_path / "cli.epub"
    code = cli_main([str(sample_pdf), "-o", str(out), "--no-extract-cover"])
    assert code == 0
    assert out.exists()


def test_cli_missing_file(tmp_path):
    code = cli_main([str(tmp_path / "no.pdf")])
    assert code == 2


def test_convert_many(tmp_path, sample_pdf):
    dest = tmp_path / "lote"
    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    a.write_bytes(sample_pdf.read_bytes())
    b.write_bytes(sample_pdf.read_bytes())
    results = convert_many(
        [a, b],
        dest,
        ConversionOptions(extract_cover_from_pdf=False),
    )
    assert len(results) == 2
    assert {r.output_path.name for r in results} == {"a.epub", "b.epub"}
    assert all(r.output_path.exists() for r in results)


def test_lines_to_html_tuple_compat():
    html, next_id = lines_to_html(["Hola mundo."], kepub=True)
    assert "koboSpan" in html
    assert next_id > 1
