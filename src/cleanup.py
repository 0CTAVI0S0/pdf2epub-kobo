"""Quita cabeceras, pies de página y números de página repetidos."""

from __future__ import annotations

import re
from collections import Counter

_PAGE_NUMBER_LINE = re.compile(
    r"^\s*(?:página|page|pag\.?|pág\.?)?\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$",
    re.IGNORECASE,
)
_DIGIT_RUN = re.compile(r"\d+")


def _nonempty_lines(page: str) -> list[str]:
    return [ln.strip() for ln in page.split("\n") if ln.strip()]


def _normalize_repeated(text: str) -> str:
    return _DIGIT_RUN.sub("#", text).casefold().strip()


def _looks_like_running_header(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if _PAGE_NUMBER_LINE.match(stripped):
        return True
    if len(stripped) > 60 or len(stripped.split()) > 8:
        return False
    return True


def _common_pattern(items: list[str], threshold: float = 0.5) -> str | None:
    candidates = [x for x in items if x and _looks_like_running_header(x)]
    if len(candidates) < 3:
        return None
    counts = Counter(_normalize_repeated(x) for x in candidates)
    if not counts:
        return None
    pattern, n = counts.most_common(1)[0]
    if not pattern or n / len(items) < threshold:
        return None
    if pattern in {"#"} and n / len(items) < 0.6:
        return None
    return pattern


def strip_headers_footers(pages: list[str]) -> list[str]:
    """Elimina líneas de cabecera/pie que se repiten en la mayoría de páginas."""
    if len(pages) < 3:
        return [_strip_page_numbers_only(p) for p in pages]

    headers: list[str] = []
    footers: list[str] = []

    for page in pages:
        lines = _nonempty_lines(page)
        if not lines:
            headers.append("")
            footers.append("")
            continue
        headers.append(lines[0])
        footers.append(lines[-1])

    header_pat = _common_pattern(headers)
    footer_pat = _common_pattern(footers)

    cleaned: list[str] = []
    for page in pages:
        raw_lines = page.split("\n")
        stripped_flags = [False] * len(raw_lines)

        def mark_matching_from_start(pattern: str | None, max_scan: int) -> None:
            if not pattern:
                return
            seen = 0
            for i, line in enumerate(raw_lines):
                if not line.strip():
                    continue
                seen += 1
                if _normalize_repeated(line) == pattern or _PAGE_NUMBER_LINE.match(line.strip()):
                    stripped_flags[i] = True
                if seen >= max_scan:
                    break

        def mark_matching_from_end(pattern: str | None, max_scan: int) -> None:
            if not pattern:
                return
            seen = 0
            for i in range(len(raw_lines) - 1, -1, -1):
                line = raw_lines[i]
                if not line.strip():
                    continue
                seen += 1
                if _normalize_repeated(line) == pattern or _PAGE_NUMBER_LINE.match(line.strip()):
                    stripped_flags[i] = True
                if seen >= max_scan:
                    break

        mark_matching_from_start(header_pat, 1)
        mark_matching_from_end(footer_pat, 1)

        for i, line in enumerate(raw_lines):
            if _PAGE_NUMBER_LINE.match(line.strip()):
                stripped_flags[i] = True

        kept = [ln for ln, drop in zip(raw_lines, stripped_flags) if not drop]
        cleaned.append("\n".join(kept))

    return cleaned


def _strip_page_numbers_only(page: str) -> str:
    lines = page.split("\n")
    kept = []
    nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
    edge = set()
    if nonempty:
        edge.add(nonempty[0])
        edge.add(nonempty[-1])
    for i, ln in enumerate(lines):
        if i in edge and _PAGE_NUMBER_LINE.match(ln.strip()):
            continue
        kept.append(ln)
    return "\n".join(kept)
