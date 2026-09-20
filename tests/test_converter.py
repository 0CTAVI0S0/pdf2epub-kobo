import zipfile
from pathlib import Path

import fitz
import pytest

from src.converter import ConversionOptions, convert_pdf_to_epub


@pytest.fixture
def sample_pdf_with_toc(tmp_path) -> Path:
    pdf_path = tmp_path / "sample_toc.pdf"
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Uno\n\nTexto de la primera parte del libro.")
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Dos\n\nTexto de la segunda parte del libro.")
    doc.set_toc([[1, "Introducción", 1], [1, "Desarrollo", 2]])
    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def sample_pdf_by_fontsize(tmp_path) -> Path:
    pdf_path = tmp_path / "sample_font.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Titulo Grande", fontsize=24)
    page.insert_text((72, 110), "Texto normal del cuerpo del capitulo uno.", fontsize=11)
    page.insert_text((72, 160), "Otro Titulo", fontsize=24)
    page.insert_text((72, 200), "Texto normal del cuerpo del capitulo dos.", fontsize=11)
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_convert_creates_valid_epub(sample_pdf, tmp_path):
    output_path = tmp_path / "output.epub"
    result = convert_pdf_to_epub(
        sample_pdf, output_path, ConversionOptions(title="Prueba", author="Test")
    )

    assert output_path.exists()
    assert result.chapter_count == 2
    assert not result.warnings

    with zipfile.ZipFile(output_path) as z:
        assert z.testzip() is None
        assert "mimetype" in z.namelist()


def test_convert_uses_toc_when_available(sample_pdf_with_toc, tmp_path):
    output_path = tmp_path / "output_toc.epub"
    result = convert_pdf_to_epub(sample_pdf_with_toc, output_path)
    assert result.chapter_count == 2
    assert result.detection_method == "índice del PDF"


def test_convert_uses_font_size_when_no_toc(sample_pdf_by_fontsize, tmp_path):
    output_path = tmp_path / "output_font.epub"
    result = convert_pdf_to_epub(sample_pdf_by_fontsize, output_path)
    assert result.chapter_count == 2
    assert result.detection_method == "tamaño de letra de los títulos"


def test_convert_falls_back_to_text_pattern(sample_pdf, tmp_path):
    output_path = tmp_path / "output_pattern.epub"
    result = convert_pdf_to_epub(sample_pdf, output_path)
    assert result.detection_method == "patrón de texto (Capítulo X / mayúsculas)"


def test_convert_split_by_page(sample_pdf, tmp_path):
    output_path = tmp_path / "output_by_page.epub"
    result = convert_pdf_to_epub(
        sample_pdf, output_path, ConversionOptions(split_by_page=True)
    )
    assert result.chapter_count == 2  # 2 páginas en el PDF de prueba


def test_convert_empty_pdf_warns(tmp_path):
    pdf_path = tmp_path / "empty.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(pdf_path)
    doc.close()

    output_path = tmp_path / "empty.epub"
    result = convert_pdf_to_epub(pdf_path, output_path)
    assert result.warnings  # debe avisar que no encontró texto


# ---------------------------------------------------------------------------
# Modo manual
# ---------------------------------------------------------------------------

from src.converter import parse_manual_chapter_markers


def test_parse_manual_chapter_markers_ok():
    raw = "Noche primera :: Era una noche maravillosa\nNoche segunda :: Bueno, ¿y qué?"
    markers = parse_manual_chapter_markers(raw)
    assert markers == [
        {"titulo": "Noche primera", "inicio": "Era una noche maravillosa"},
        {"titulo": "Noche segunda", "inicio": "Bueno, ¿y qué?"},
    ]


def test_parse_manual_chapter_markers_ignores_blank_lines():
    raw = "\n\nCap 1 :: Texto uno\n\nCap 2 :: Texto dos\n\n"
    markers = parse_manual_chapter_markers(raw)
    assert len(markers) == 2


def test_parse_manual_chapter_markers_missing_separator():
    with pytest.raises(ValueError, match="Línea 2"):
        parse_manual_chapter_markers("Cap 1 :: Texto uno\nCap 2 Texto dos")


def test_parse_manual_chapter_markers_empty_title():
    with pytest.raises(ValueError, match="título"):
        parse_manual_chapter_markers(" :: Texto uno")


def test_parse_manual_chapter_markers_empty_input():
    with pytest.raises(ValueError):
        parse_manual_chapter_markers("   \n   \n")


@pytest.fixture
def sample_pdf_novela(tmp_path) -> Path:
    pdf_path = tmp_path / "novela.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "FIN\n\nNoche primera\n\nEra una noche maravillosa, llena de estrellas.\n\n"
        "Noche segunda\n\nBueno, y que? No ha dormido usted?",
        fontsize=11,
    )
    doc.save(pdf_path)
    doc.close()
    return pdf_path


def test_convert_with_manual_chapters(sample_pdf_novela, tmp_path):
    manual_chapters = [
        {"titulo": "Noche segunda", "inicio": "Bueno, y que?"},
        {"titulo": "Noche primera", "inicio": "Era una noche maravillosa"},
    ]
    output_path = tmp_path / "novela.epub"
    result = convert_pdf_to_epub(
        sample_pdf_novela,
        output_path,
        ConversionOptions(manual_chapters=manual_chapters),
    )
    assert result.chapter_count == 2
    assert result.detection_method == "capítulos definidos manualmente"
    # Deben quedar ordenados por posición real en el texto, no por el orden
    # en que el usuario los escribió.
    with zipfile.ZipFile(output_path) as z:
        chap1 = z.read("EPUB/chap_001.xhtml").decode("utf-8")
        assert "Noche primera" in chap1


def test_convert_with_manual_chapters_ignores_line_wrap(tmp_path):
    """El fragmento del usuario no tiene el salto de línea que sí quedó en el
    texto extraído del PDF (texto justificado); debe encontrarse igual."""
    pdf_path = tmp_path / "wrap.pdf"
    doc = fitz.open()
    page = doc.new_page()
    # En el PDF, "maravillosa" y "llena" quedan en renglones distintos.
    page.insert_text(
        (72, 72),
        "Noche primera\n\nEra una noche maravillosa\nllena de estrellas.",
        fontsize=11,
    )
    doc.save(pdf_path)
    doc.close()

    manual_chapters = [{"titulo": "Noche primera", "inicio": "maravillosa llena de estrellas"}]
    output_path = tmp_path / "wrap.epub"
    result = convert_pdf_to_epub(
        pdf_path, output_path, ConversionOptions(manual_chapters=manual_chapters)
    )
    assert result.chapter_count == 1


def test_lines_to_html_dehyphenates_line_wrap():
    from src.converter import _lines_to_html

    html = _lines_to_html(["Era una palabra cor-", "tada por el ancho de página."])
    assert "cortada por el ancho de página" in html
    assert "cor-" not in html


def test_lines_to_html_preserves_intentional_hyphen():
    from src.converter import _lines_to_html

    # "Torre-Nieto" es un apellido compuesto, no debe dehifenizarse porque
    # la siguiente línea empieza en mayúscula.
    html = _lines_to_html(["El autor es Torre-", "Nieto, nacido en 1980."])
    assert "Torre-" in html
    assert "Torre-Nieto" not in html


def test_convert_with_manual_chapters_not_found(sample_pdf_novela, tmp_path):
    manual_chapters = [{"titulo": "Capitulo fantasma", "inicio": "esto no existe en el pdf"}]
    with pytest.raises(ValueError, match="Capitulo fantasma"):
        convert_pdf_to_epub(
            sample_pdf_novela,
            tmp_path / "out.epub",
            ConversionOptions(manual_chapters=manual_chapters),
        )


# ---------------------------------------------------------------------------
# Portada personalizada
# ---------------------------------------------------------------------------

def test_convert_with_cover_image(sample_pdf, tmp_path):
    cover_path = tmp_path / "cover.jpg"
    # JPEG mínimo, solo para probar que el archivo se adjunta como portada.
    cover_path.write_bytes(
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
    )
    output_path = tmp_path / "output_cover.epub"
    result = convert_pdf_to_epub(
        sample_pdf, output_path, ConversionOptions(cover_image_path=cover_path)
    )
    assert not any("portada" in w for w in result.warnings)
    with zipfile.ZipFile(output_path) as z:
        assert any("cover" in n.lower() for n in z.namelist())


def test_convert_with_missing_cover_image_warns(sample_pdf, tmp_path):
    missing_cover = tmp_path / "no_existe.jpg"
    output_path = tmp_path / "output_no_cover.epub"
    result = convert_pdf_to_epub(
        sample_pdf, output_path, ConversionOptions(cover_image_path=missing_cover)
    )
    assert any("portada" in w for w in result.warnings)
    assert output_path.exists()
