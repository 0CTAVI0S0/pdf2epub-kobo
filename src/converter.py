"""
Conversión PDF → EPUB/KEPUB para Kobo.

No depende de la GUI: sirve para CLI, tests y la interfaz.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import fitz
from ebooklib import epub

from src.cleanup import strip_headers_footers
from src.detect import (
    chapters_by_page,
    chapters_from_font_size,
    chapters_from_manual_markers,
    chapters_from_text_pattern,
    chapters_from_toc,
    parse_manual_chapter_markers,
)
from src.htmlutil import KOBO_CSS, chapter_xhtml, lines_to_html as _lines_to_html_full

def _lines_to_html(lines: list[str]) -> str:
    html, _ = _lines_to_html_full(lines)
    return html

ProgressCb = Optional[Callable[[str, int], None]]
CancelCb = Optional[Callable[[], bool]]


class ConversionCancelled(Exception):
    """El usuario canceló la conversión."""


class ConversionError(Exception):
    """Error recuperable de conversión (mensaje para la UI)."""


@dataclass
class ConversionOptions:
    title: str = ""
    author: str = "Desconocido"
    language: str = "es"
    split_by_page: bool = False
    manual_chapters: Optional[list[dict]] = None
    cover_image_path: Optional[Path] = None
    extract_cover_from_pdf: bool = True
    use_ocr: bool = False
    strip_headers_footers: bool = True
    kepub: bool = False
    is_cancelled: CancelCb = None
    # Capítulos ya detectados/editados: [(título, html_cuerpo), ...]
    chapters: Optional[list[tuple[str, str]]] = None
    detection_method: str = ""


@dataclass
class ConversionResult:
    output_path: Path
    chapter_count: int
    detection_method: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class PdfMetadata:
    title: str = ""
    author: str = ""
    language: str = ""
    page_count: int = 0


@dataclass
class AnalysisResult:
    metadata: PdfMetadata
    chapters: list[tuple[str, str]]
    detection_method: str
    warnings: list[str] = field(default_factory=list)
    has_text: bool = True
    cover_jpeg: bytes | None = None


def _check_cancel(is_cancelled: CancelCb) -> None:
    if is_cancelled and is_cancelled():
        raise ConversionCancelled("Conversión cancelada.")


def _report(progress_cb: ProgressCb, msg: str, percent: int) -> None:
    if progress_cb:
        progress_cb(msg, max(0, min(100, percent)))


def read_pdf_metadata(pdf_path: Path) -> PdfMetadata:
    doc = fitz.open(pdf_path)
    try:
        meta = doc.metadata or {}
        title = (meta.get("title") or "").strip()
        author = (meta.get("author") or "").strip()
        language = (meta.get("language") or "").strip()
        return PdfMetadata(
            title=title,
            author=author,
            language=language,
            page_count=doc.page_count,
        )
    finally:
        doc.close()


def extract_cover_jpeg(doc: fitz.Document, *, max_width: int = 1200) -> bytes | None:
    """Renderiza la primera página (o la imagen embebida más grande) como JPEG."""
    if doc.page_count < 1:
        return None
    page = doc[0]
    largest: tuple[int, bytes] | None = None
    try:
        for img in page.get_images(full=True):
            xref = img[0]
            extracted = doc.extract_image(xref)
            blob = extracted.get("image")
            if not blob:
                continue
            area = int(extracted.get("width", 0)) * int(extracted.get("height", 0))
            if largest is None or area > largest[0]:
                largest = (area, blob)
    except Exception:
        largest = None

    if largest and largest[0] >= 80_000:
        # Puede no ser JPEG; re-encode vía pixmap si hace falta.
        try:
            pix = fitz.Pixmap(doc, page.get_images(full=True)[0][0])
            if pix.n >= 5:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            return pix.tobytes("jpeg")
        except Exception:
            pass

    scale = min(2.0, max_width / max(page.rect.width, 1))
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return pix.tobytes("jpeg")


def _ocr_page_text(page: fitz.Page) -> str:
    try:
        tpage = page.get_textpage_ocr(dpi=200, full=True)
        return page.get_text("text", textpage=tpage) or ""
    except Exception as exc:
        raise ConversionError(
            "No se pudo usar OCR. Instala Tesseract "
            "(https://github.com/tesseract-ocr/tesseract) y asegúrate de que "
            "esté en el PATH."
        ) from exc


def extract_pages_text(
    doc: fitz.Document,
    *,
    use_ocr: bool = False,
    progress_cb: ProgressCb = None,
    is_cancelled: CancelCb = None,
) -> tuple[list[str], list[str]]:
    pages: list[str] = []
    warnings: list[str] = []
    n = doc.page_count or 1
    used_ocr = False

    for i, page in enumerate(doc):
        _check_cancel(is_cancelled)
        _report(progress_cb, f"Extrayendo texto ({i + 1}/{doc.page_count})…", int(8 + 40 * i / n))
        text = page.get_text("text") or ""
        if not text.strip() and use_ocr:
            text = _ocr_page_text(page)
            used_ocr = True
        pages.append(text)

    if used_ocr:
        warnings.append("Se usó OCR (Tesseract) en páginas sin texto seleccionable.")
    return pages, warnings


def detect_chapters(
    doc: fitz.Document,
    pages: list[str],
    options: ConversionOptions,
) -> tuple[list[tuple[str, str]], str]:
    kepub = options.kepub
    if options.manual_chapters is not None:
        full_text = "\n".join(pages)
        return (
            chapters_from_manual_markers(full_text, options.manual_chapters, kepub=kepub),
            "capítulos definidos manualmente",
        )
    if options.split_by_page:
        return chapters_by_page(pages, kepub=kepub), "una página por capítulo (forzado)"

    chapters = chapters_from_toc(doc, pages, kepub=kepub)
    if chapters:
        return chapters, "índice del PDF"

    chapters = chapters_from_font_size(doc, kepub=kepub)
    if chapters:
        return chapters, "tamaño de letra de los títulos"

    chapters = chapters_from_text_pattern(pages, kepub=kepub)
    return chapters, "patrón de texto (Capítulo X / mayúsculas)"


def analyze_pdf(
    pdf_path: Path,
    options: Optional[ConversionOptions] = None,
    progress_cb: ProgressCb = None,
) -> AnalysisResult:
    options = options or ConversionOptions()
    _report(progress_cb, "Abriendo PDF…", 2)
    doc = fitz.open(pdf_path)
    warnings: list[str] = []
    try:
        meta_raw = doc.metadata or {}
        metadata = PdfMetadata(
            title=(meta_raw.get("title") or "").strip(),
            author=(meta_raw.get("author") or "").strip(),
            language=(meta_raw.get("language") or "").strip(),
            page_count=doc.page_count,
        )
        pages, extract_warnings = extract_pages_text(
            doc,
            use_ocr=options.use_ocr,
            progress_cb=progress_cb,
            is_cancelled=options.is_cancelled,
        )
        warnings.extend(extract_warnings)

        has_text = any(p.strip() for p in pages)
        if not has_text:
            warnings.append(
                "No se encontró texto seleccionable en el PDF. "
                "Activa OCR (requiere Tesseract) si es un escaneo."
            )

        if options.strip_headers_footers:
            _report(progress_cb, "Limpiando cabeceras y pies de página…", 52)
            pages = strip_headers_footers(pages)

        _report(progress_cb, "Detectando capítulos…", 60)
        if options.chapters is not None:
            chapters = options.chapters
            method = options.detection_method or "editados por el usuario"
        else:
            chapters, method = detect_chapters(doc, pages, options)

        if len(chapters) <= 1 and not options.split_by_page and options.manual_chapters is None:
            warnings.append(
                "No se detectaron capítulos separados; "
                "el libro se generó como un solo bloque de lectura."
            )

        cover_jpeg = None
        if options.extract_cover_from_pdf and options.cover_image_path is None:
            _report(progress_cb, "Extrayendo portada…", 70)
            try:
                cover_jpeg = extract_cover_jpeg(doc)
            except Exception:
                warnings.append("No se pudo extraer la portada del PDF.")

        _report(progress_cb, "Análisis listo", 75)
        return AnalysisResult(
            metadata=metadata,
            chapters=chapters,
            detection_method=method,
            warnings=warnings,
            has_text=has_text,
            cover_jpeg=cover_jpeg,
        )
    finally:
        doc.close()


def _write_epub(
    output_path: Path,
    chapters: list[tuple[str, str]],
    options: ConversionOptions,
    cover_jpeg: bytes | None,
    extra_cover_path: Path | None,
    warnings: list[str],
) -> None:
    title = options.title or "Sin título"
    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.set_language(options.language or "es")
    book.add_author(options.author or "Desconocido")

    cover_bytes: bytes | None = None
    cover_name = "cover.jpg"
    if extra_cover_path is not None:
        cover_path = Path(extra_cover_path)
        if cover_path.exists():
            cover_bytes = cover_path.read_bytes()
            cover_name = cover_path.name
        else:
            warnings.append(
                f"No se encontró la imagen de portada en '{cover_path}'; "
                "se intentará usar la extraída del PDF."
            )
    if cover_bytes is None and cover_jpeg:
        cover_bytes = cover_jpeg
        cover_name = "cover.jpg"
    if cover_bytes:
        book.set_cover(cover_name, cover_bytes)

    style = epub.EpubItem(
        uid="style_kobo",
        file_name="style/kobo.css",
        media_type="text/css",
        content=KOBO_CSS,
    )
    book.add_item(style)

    epub_chapters = []
    span_id = 1
    for idx, (chap_title, html) in enumerate(chapters, start=1):
        c = epub.EpubHtml(
            title=chap_title,
            file_name=f"chap_{idx:03d}.xhtml",
            lang=options.language or "es",
        )
        content, span_id = chapter_xhtml(chap_title, html, kepub=options.kepub, span_id=span_id)
        c.content = content
        c.add_link(href="style/kobo.css", rel="stylesheet", type="text/css")
        book.add_item(c)
        epub_chapters.append(c)

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav"] + epub_chapters

    output_path.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(output_path), book)


def default_output_path(pdf_path: Path, dest: Path | None, *, kepub: bool) -> Path:
    suffix = ".kepub.epub" if kepub else ".epub"
    name = pdf_path.stem + suffix
    if dest is None:
        return pdf_path.with_name(name)
    if dest.suffix.lower() in {".epub", ".kepub"} or dest.name.endswith(".kepub.epub"):
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    return dest / name


def convert_pdf_to_epub(
    pdf_path: Path,
    output_path: Path,
    options: Optional[ConversionOptions] = None,
    progress_cb: Optional[Callable[..., None]] = None,
) -> ConversionResult:
    """
    Convierte un PDF a EPUB en output_path.

    progress_cb puede ser (msg) o (msg, percent).
    """
    options = options or ConversionOptions()

    def _cb(msg: str, percent: int = 0) -> None:
        if not progress_cb:
            return
        try:
            progress_cb(msg, percent)
        except TypeError:
            progress_cb(msg)

    analysis = analyze_pdf(pdf_path, options, progress_cb=_cb)
    title = options.title or analysis.metadata.title or pdf_path.stem
    author = options.author if options.author and options.author != "Desconocido" else (
        analysis.metadata.author or options.author or "Desconocido"
    )
    write_opts = ConversionOptions(
        title=title,
        author=author,
        language=options.language or analysis.metadata.language or "es",
        kepub=options.kepub,
        cover_image_path=options.cover_image_path,
        extract_cover_from_pdf=options.extract_cover_from_pdf,
    )

    _check_cancel(options.is_cancelled)
    _cb("Generando EPUB…", 85)
    _write_epub(
        output_path,
        analysis.chapters,
        write_opts,
        analysis.cover_jpeg,
        options.cover_image_path,
        analysis.warnings,
    )
    _cb("¡Listo!", 100)
    return ConversionResult(
        output_path=output_path,
        chapter_count=len(analysis.chapters),
        detection_method=analysis.detection_method,
        warnings=analysis.warnings,
    )


def convert_many(
    pdf_paths: list[Path],
    dest_dir: Path,
    options: Optional[ConversionOptions] = None,
    progress_cb: ProgressCb = None,
) -> list[ConversionResult]:
    options = options or ConversionOptions()
    dest_dir.mkdir(parents=True, exist_ok=True)
    results: list[ConversionResult] = []
    total = len(pdf_paths) or 1
    for i, pdf_path in enumerate(pdf_paths):
        _check_cancel(options.is_cancelled)

        def _cb(msg: str, percent: int = 0, _i=i) -> None:
            overall = int((_i * 100 + percent) / total)
            if progress_cb:
                progress_cb(f"[{pdf_path.name}] {msg}", overall)

        out = default_output_path(pdf_path, dest_dir, kepub=options.kepub)
        file_opts = ConversionOptions(
            title=options.title if len(pdf_paths) == 1 else "",
            author=options.author,
            language=options.language,
            split_by_page=options.split_by_page,
            manual_chapters=options.manual_chapters if len(pdf_paths) == 1 else None,
            cover_image_path=options.cover_image_path if len(pdf_paths) == 1 else None,
            extract_cover_from_pdf=options.extract_cover_from_pdf,
            use_ocr=options.use_ocr,
            strip_headers_footers=options.strip_headers_footers,
            kepub=options.kepub,
            is_cancelled=options.is_cancelled,
        )
        results.append(convert_pdf_to_epub(pdf_path, out, file_opts, progress_cb=_cb))
    return results


# Reexport para compatibilidad con la GUI y tests existentes.
__all__ = [
    "AnalysisResult",
    "ConversionCancelled",
    "ConversionError",
    "ConversionOptions",
    "ConversionResult",
    "PdfMetadata",
    "analyze_pdf",
    "convert_many",
    "convert_pdf_to_epub",
    "default_output_path",
    "parse_manual_chapter_markers",
    "read_pdf_metadata",
]
