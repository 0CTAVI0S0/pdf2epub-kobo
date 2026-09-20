"""Detección de capítulos: TOC, fuente, patrón de texto y marcadores manuales."""

from __future__ import annotations

import re
from collections import Counter
from typing import Optional

import fitz

from src.htmlutil import lines_to_html

CHAPTER_PATTERN = re.compile(
    r"^\s*(cap[íi]tulo|chapter|parte|part)\s+\w+", re.IGNORECASE
)


def chapters_from_toc(
    doc: fitz.Document,
    pages: list[str] | None = None,
    *,
    kepub: bool = False,
) -> Optional[list[tuple[str, str]]]:
    toc = doc.get_toc(simple=True)
    if not toc:
        return None

    top_level = [entry for entry in toc if entry[0] == 1]
    entries = top_level if top_level else toc
    entries = sorted(entries, key=lambda e: e[2])

    n_pages = doc.page_count
    page_texts = pages if pages is not None else [p.get_text("text") for p in doc]
    chapters: list[tuple[str, str]] = []
    span_id = 1

    for i, (_lvl, title, page_num) in enumerate(entries):
        start = max(0, min(page_num - 1, n_pages - 1))
        if i + 1 < len(entries):
            end = max(start + 1, min(entries[i + 1][2] - 1, n_pages))
        else:
            end = n_pages
        if start >= end:
            continue
        text = "\n".join(page_texts[start:end])
        clean_title = title.strip() or f"Capítulo {i + 1}"
        html, span_id = lines_to_html(text.split("\n"), kepub=kepub, span_start=span_id)
        html = _drop_leading_title(html, clean_title)
        chapters.append((clean_title, html))

    return chapters or None


def chapters_from_font_size(doc: fitz.Document, *, kepub: bool = False) -> Optional[list[tuple[str, str]]]:
    lines_data: list[tuple[str, float]] = []

    for page in doc:
        page_dict = page.get_text("dict")
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(s.get("text", "") for s in spans).strip()
                if not text:
                    continue
                max_size = max(s.get("size", 0) for s in spans)
                lines_data.append((text, max_size))

    if not lines_data:
        return None

    char_count_by_size: Counter[int] = Counter()
    for text, size in lines_data:
        char_count_by_size[round(size)] += len(text)
    body_size = char_count_by_size.most_common(1)[0][0]
    threshold = body_size * 1.15

    chapters: list[tuple[str, list[str]]] = []
    current_title = "Contenido"
    current_lines: list[str] = []
    found_heading = False

    for text, size in lines_data:
        is_heading = size >= threshold and len(text) <= 80 and len(text.split()) <= 12
        if is_heading:
            found_heading = True
            if current_lines:
                chapters.append((current_title, current_lines))
            current_title = text
            current_lines = []
        else:
            current_lines.append(text)

    if current_lines:
        chapters.append((current_title, current_lines))

    if not found_heading:
        return None

    result: list[tuple[str, str]] = []
    span_id = 1
    for title, lines in chapters:
        html, span_id = lines_to_html(lines, kepub=kepub, span_start=span_id)
        result.append((title, html))
    return result


def parse_manual_chapter_markers(raw_text: str) -> list[dict]:
    """Parsea "Título :: texto de inicio", una línea por capítulo."""
    markers: list[dict] = []

    for line_num, raw_line in enumerate(raw_text.split("\n"), start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        if "::" not in stripped:
            raise ValueError(
                f"Línea {line_num}: falta el separador '::' entre el título y el "
                f"texto de inicio. Formato esperado: 'Título :: texto de inicio'. "
                f"Línea recibida: {stripped!r}"
            )

        titulo, _, inicio = stripped.partition("::")
        titulo = titulo.strip()
        inicio = inicio.strip()

        if not titulo:
            raise ValueError(f"Línea {line_num}: el título del capítulo está vacío.")
        if not inicio:
            raise ValueError(
                f"Línea {line_num}: el texto de inicio del capítulo está vacío."
            )

        markers.append({"titulo": titulo, "inicio": inicio})

    if not markers:
        raise ValueError(
            "No se encontró ningún capítulo válido en el texto pegado. "
            "Escribe al menos una línea con el formato 'Título :: texto de inicio'."
        )

    return markers


def normalize_for_search(text: str) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    index_map: list[int] = []
    prev_was_space = False

    for i, ch in enumerate(text):
        if ch.isspace():
            if not prev_was_space:
                normalized_chars.append(" ")
                index_map.append(i)
                prev_was_space = True
        else:
            normalized_chars.append(ch)
            index_map.append(i)
            prev_was_space = False

    return "".join(normalized_chars), index_map


def chapters_from_manual_markers(
    full_text: str, markers: list[dict], *, kepub: bool = False
) -> list[tuple[str, str]]:
    normalized_text, index_map = normalize_for_search(full_text)
    positions: list[tuple[int, str]] = []

    for marker in markers:
        titulo = marker["titulo"]
        inicio = marker["inicio"]
        normalized_inicio, _ = normalize_for_search(inicio)
        idx_norm = normalized_text.find(normalized_inicio)
        if idx_norm == -1:
            raise ValueError(
                f"No se pudo ubicar el capítulo '{titulo}' en el texto extraído del "
                f"PDF. Revisa que el fragmento '{inicio}' esté escrito exactamente "
                "igual que en el documento (mismas mayúsculas y tildes; los espacios "
                "y saltos de línea no importan)."
            )
        idx = index_map[idx_norm]
        positions.append((idx, titulo))

    positions.sort(key=lambda p: p[0])

    chapters: list[tuple[str, str]] = []
    span_id = 1
    for i, (start, titulo) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(full_text)
        chunk = full_text[start:end]
        html, span_id = lines_to_html(chunk.split("\n"), kepub=kepub, span_start=span_id)
        html = _drop_leading_title(html, titulo)
        chapters.append((titulo, html))

    return chapters


def looks_like_chapter_title(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    if CHAPTER_PATTERN.match(stripped):
        return True
    letters = [c for c in stripped if c.isalpha()]
    if letters and all(c.isupper() for c in letters) and len(stripped.split()) <= 8:
        return True
    return False


def chapters_from_text_pattern(pages: list[str], *, kepub: bool = False) -> list[tuple[str, str]]:
    full_text = "\n".join(pages)
    lines = full_text.split("\n")

    chapters: list[tuple[str, list[str]]] = []
    current_title = "Contenido"
    current_lines: list[str] = []

    for line in lines:
        if looks_like_chapter_title(line):
            if current_lines:
                chapters.append((current_title, current_lines))
            current_title = line.strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        chapters.append((current_title, current_lines))

    result: list[tuple[str, str]] = []
    span_id = 1
    for title, ch_lines in chapters:
        html, span_id = lines_to_html(ch_lines, kepub=kepub, span_start=span_id)
        result.append((title, html))
    return result


def chapters_by_page(pages: list[str], *, kepub: bool = False) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    span_id = 1
    for i, page in enumerate(pages):
        html, span_id = lines_to_html(page.split("\n"), kepub=kepub, span_start=span_id)
        result.append((f"Página {i + 1}", html))
    return result


def _drop_leading_title(html: str, title: str) -> str:
    """Si el primer párrafo copia el título del capítulo, se elimina."""
    from src.htmlutil import escape

    needle = f"<p>{escape(title)}</p>"
    if html.startswith(needle):
        return html[len(needle) :].lstrip()
    return html
