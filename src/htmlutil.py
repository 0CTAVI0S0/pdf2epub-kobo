"""HTML helpers: escape, paragraphs, CSS and optional KEPUB spans."""

from __future__ import annotations

import re
from html import escape as html_escape

KOBO_CSS = """
body {
  margin: 0;
  padding: 0;
  line-height: 1.45;
  text-align: justify;
  widows: 2;
  orphans: 2;
}
h1 {
  font-size: 1.3em;
  font-weight: bold;
  margin: 1em 0 0.8em 0;
  text-align: center;
  text-indent: 0;
  page-break-before: always;
  break-before: page;
}
p {
  margin: 0 0 0.75em 0;
  text-indent: 1.2em;
  text-align: justify;
}
p.no-indent { text-indent: 0; }
"""

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+")


def escape(text: str) -> str:
    return html_escape(text, quote=True)


def _is_wrap_hyphen(text: str) -> bool:
    """True si `text` termina en un guión de corte de línea (word-wrap)."""
    if not text.endswith("-") or text.endswith("--"):
        return False
    if len(text) < 2:
        return False
    return text[-2].isalpha()


def join_paragraph_lines(buffer: list[str]) -> str:
    """Une líneas de un párrafo y recompones cortes con guión al final de renglón."""
    result = buffer[0]
    for line in buffer[1:]:
        if _is_wrap_hyphen(result) and line and line[0].islower():
            result = result[:-1] + line
        else:
            result += " " + line
    return result


def lines_to_html(lines: list[str], *, kepub: bool = False, span_start: int = 1) -> tuple[str, int]:
    """Convierte líneas planas en párrafos HTML. Devuelve (html, siguiente_id_kobo)."""
    paragraphs: list[str] = []
    buffer: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if buffer:
                paragraphs.append(join_paragraph_lines(buffer))
                buffer = []
            continue
        buffer.append(line)

    if buffer:
        paragraphs.append(join_paragraph_lines(buffer))

    span_id = span_start
    parts: list[str] = []
    for p in paragraphs:
        if not p:
            continue
        if kepub:
            wrapped, span_id = wrap_kepub_text(p, span_id)
            parts.append(f"<p>{wrapped}</p>")
        else:
            parts.append(f"<p>{escape(p)}</p>")

    return ("\n".join(parts) if parts else "<p></p>"), span_id


def wrap_kepub_text(text: str, start_id: int = 1) -> tuple[str, int]:
    """Envuelve oraciones en spans koboSpan (formato KEPUB)."""
    pieces = _SENTENCE_SPLIT.split(text.strip()) or [text]
    spans: list[str] = []
    span_id = start_id
    para = 1
    for i, piece in enumerate(pieces, start=1):
        piece = piece.strip()
        if not piece:
            continue
        spans.append(
            f'<span class="koboSpan" id="kobo.{span_id}.{para}.{i}">{escape(piece)}</span>'
        )
        span_id += 1
    return " ".join(spans) if spans else escape(text), span_id


def chapter_xhtml(title: str, body_html: str, *, kepub: bool = False, span_id: int = 1) -> tuple[str, int]:
    heading = escape(title)
    if kepub:
        wrapped, span_id = wrap_kepub_text(title, span_id)
        heading = wrapped
    return f"<h1>{heading}</h1>\n{body_html}", span_id
