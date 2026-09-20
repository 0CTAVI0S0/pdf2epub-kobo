"""Interfaz de consola: pdf2epub archivo.pdf [-o salida.epub]."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.converter import (
    ConversionCancelled,
    ConversionError,
    ConversionOptions,
    convert_many,
    convert_pdf_to_epub,
    default_output_path,
    parse_manual_chapter_markers,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdf2epub",
        description="Convierte PDFs de texto a EPUB/KEPUB listos para Kobo.",
    )
    p.add_argument("pdfs", nargs="+", type=Path, help="Uno o más archivos PDF")
    p.add_argument("-o", "--output", type=Path, help="Archivo EPUB de salida (un solo PDF)")
    p.add_argument("-d", "--outdir", type=Path, help="Carpeta de salida (varios PDFs o un PDF)")
    p.add_argument("--title", default="", help="Título del libro")
    p.add_argument("--author", default="", help="Autor")
    p.add_argument("--language", default="es", help="Idioma BCP-47 (por defecto: es)")
    p.add_argument("--split-by-page", action="store_true", help="Un capítulo por página")
    p.add_argument("--chapters-file", type=Path, help="Archivo de marcadores 'Título :: inicio'")
    p.add_argument("--cover", type=Path, help="Imagen de portada (.jpg/.png)")
    p.add_argument("--no-extract-cover", action="store_true", help="No extraer portada del PDF")
    p.add_argument("--ocr", action="store_true", help="OCR con Tesseract si no hay texto")
    p.add_argument("--keep-headers", action="store_true", help="No quitar cabeceras/pies")
    p.add_argument("--kepub", action="store_true", help="Generar .kepub.epub con spans Kobo")
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    pdfs = [p.resolve() for p in args.pdfs]
    missing = [p for p in pdfs if not p.is_file()]
    if missing:
        print("No existe: " + ", ".join(str(p) for p in missing), file=sys.stderr)
        return 2

    manual = None
    if args.chapters_file:
        manual = parse_manual_chapter_markers(args.chapters_file.read_text(encoding="utf-8"))

    options = ConversionOptions(
        title=args.title,
        author=args.author or "Desconocido",
        language=args.language,
        split_by_page=args.split_by_page,
        manual_chapters=manual,
        cover_image_path=args.cover,
        extract_cover_from_pdf=not args.no_extract_cover,
        use_ocr=args.ocr,
        strip_headers_footers=not args.keep_headers,
        kepub=args.kepub,
    )

    def progress(msg: str, percent: int = 0) -> None:
        print(f"[{percent:3d}%] {msg}", file=sys.stderr)

    try:
        if len(pdfs) > 1:
            dest = args.outdir or args.output or pdfs[0].parent
            results = convert_many(pdfs, dest, options, progress_cb=progress)
            for r in results:
                print(f"{r.output_path} ({r.chapter_count} caps., {r.detection_method})")
                for w in r.warnings:
                    print(f"  aviso: {w}", file=sys.stderr)
            return 0

        out = args.output
        if out is None:
            out = default_output_path(pdfs[0], args.outdir, kepub=args.kepub)
        result = convert_pdf_to_epub(pdfs[0], out, options, progress_cb=progress)
        print(f"{result.output_path} ({result.chapter_count} caps., {result.detection_method})")
        for w in result.warnings:
            print(f"aviso: {w}", file=sys.stderr)
        return 0
    except ConversionCancelled:
        print("Cancelado.", file=sys.stderr)
        return 130
    except (ConversionError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
