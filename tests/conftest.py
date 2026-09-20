from pathlib import Path

import fitz
import pytest


@pytest.fixture
def sample_pdf(tmp_path) -> Path:
    pdf_path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "CAPITULO UNO\n\nTexto de prueba del primer capitulo.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "CAPITULO DOS\n\nTexto de prueba del segundo capitulo.")
    doc.save(pdf_path)
    doc.close()
    return pdf_path
