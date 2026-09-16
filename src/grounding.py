"""Resolução espacial de grounding: snippet -> bbox normalizada [0, 1].

Conversão validada empiricamente contra as bboxes do ``results.json``
submetido — que é **reconstrução nossa**, não um gabarito externo: a Takeovers
declara explicitamente que não publica um. O que a validação demonstra é que a
bbox declarada é reproduzível a partir do OCR, não que a interpretação esteja
certa::

    x_norm = x_px / (page_width_points  * 300/72)
    y_norm = y_px / (page_height_points * 300/72)

Evidência da validação — o evento de constituição registrado no arquivo traz
``bbox = [0.1201, 0.3994, 0.6591, 0.4146]`` (página 3 do acte
``63e9593b8be6eb9f9d257ec5``). Aplicando a fórmula aos pixels do OCR da linha
"Le capital social est fixé à la somme de trente sept mille…" obtém-se
``827.7 / 3915.8 / 4542.4 / 4064.8`` px, enquanto o OCR bruto traz
``828 / 3916 / 4542 / 4065`` — coincidência exata nos quatro cantos.

O matcher é tolerante ao ruído de OCR (``o``/``0``, ``l``/``1``/``I``,
``s``/``5``, ``b``/``8``, ``g``/``6``/``9``, ``z``/``2``), a acentos, a
pontuação e a quebras de linha: o snippet registrado no arquivo diz ``(37.000)``
onde o OCR bruto traz ``(37.0o0)``.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Sequence

from .config import DPI_OF_OCR, POINTS_PER_INCH
from .ocr_loader import Document, OcrLine, list_documents
from .prefilter import strip_accents

PX_PER_POINT = DPI_OF_OCR / POINTS_PER_INCH

#: Classes de confusão típicas do OCR, fundidas numa forma canônica.
_FOLD = {
    "o": "o", "0": "o",
    "l": "l", "1": "l", "i": "l", "|": "l", "!": "l",
    "s": "s", "5": "s",
    "b": "b", "8": "b",
    "g": "g", "6": "g", "9": "g",
    "z": "z", "2": "z",
    "a": "a", "4": "a",
    "e": "e", "3": "e",
    "t": "t", "7": "t",
    "c": "c", "(": "c",
}


def match_key(text: str) -> str:
    """Chave de comparação tolerante a ruído: só letras, sem espaços nem pontuação."""
    folded = "".join(_FOLD.get(ch, ch) for ch in strip_accents(text).lower())
    return re.sub(r"[^a-z]+", "", folded)


def read_key(text: str) -> str:
    """Chave legível para relatório: minúsculas, sem acentos, espaços colapsados."""
    return re.sub(r"\s+", " ", strip_accents(text).lower()).strip()


@dataclass(frozen=True)
class LocatedSpan:
    """Trecho localizado dentro de uma página."""

    line_indices: tuple[int, ...]
    matched_text: str
    score: float


@dataclass(frozen=True)
class GroundingMatch:
    """Grounding resolvido: página, bbox unitária e o texto efetivamente casado."""

    doc_id: str
    page: int
    bbox: list[float]
    snippet: str
    matched_text: str
    score: float
    line_indices: tuple[int, ...]
    page_size_px: tuple[float, float]

    @property
    def is_valid(self) -> bool:
        return bbox_is_valid(self.bbox)

    def as_source(self) -> dict[str, object]:
        """Formato pronto para ``events[].source`` do schema oficial."""
        return {
            "inpi_id": self.doc_id,
            "page": self.page,
            "bbox": [round(value, 4) for value in self.bbox],
            "snippet": self.snippet,
        }

    def describe(self) -> str:
        box = ", ".join(f"{value:.4f}" for value in self.bbox)
        return (
            f"{self.doc_id} p.{self.page} [{box}] "
            f"score={self.score:.3f} linhas={len(self.line_indices)}"
        )


def polygon_to_norm(
    polygon: tuple[tuple[float, float], ...] | list[list[float]],
    page_w_pt: float,
    page_h_pt: float,
) -> list[float]:
    """Polígono em pixels de 300 dpi -> ``[x0, y0, x1, y1]`` normalizado 0-1."""
    w_px = page_w_pt * PX_PER_POINT
    h_px = page_h_pt * PX_PER_POINT
    if w_px <= 0 or h_px <= 0:
        raise ValueError("dimensões de página inválidas para normalização")
    xs = [float(pt[0]) for pt in polygon]
    ys = [float(pt[1]) for pt in polygon]
    return [min(xs) / w_px, min(ys) / h_px, max(xs) / w_px, max(ys) / h_px]


def bbox_is_valid(bbox: list[float]) -> bool:
    """Confere o contrato do schema: 4 valores em [0, 1] e ordenados."""
    if len(bbox) != 4:
        return False
    x0, y0, x1, y1 = bbox
    if any(not isinstance(value, (int, float)) for value in bbox):
        return False
    if any(value < 0.0 or value > 1.0 for value in bbox):
        return False
    return x0 <= x1 and y0 <= y1


def reading_order_indices(lines: tuple[OcrLine, ...]) -> list[int]:
    """Ordena as linhas em ordem de leitura: faixa horizontal, depois x.

    O OCR devolve as linhas na ordem em que as detectou, o que mistura o corpo
    do ato com carimbos, selos e anotações de margem. Sem reordenar, frases
    legítimas ficam partidas e o grounding as considera ausentes.
    """
    if not lines:
        return []
    heights = sorted(line.y_max - line.y_min for line in lines)
    median_height = heights[len(heights) // 2] or 1.0
    band = max(median_height * 0.75, 1.0)
    return sorted(
        range(len(lines)),
        key=lambda index: (
            round((lines[index].y_min + lines[index].y_max) / 2.0 / band),
            lines[index].x_min,
        ),
    )


def _index_order(
    lines: tuple[OcrLine, ...], order: Sequence[int]
) -> tuple[str, list[int]]:
    """Concatena as chaves na ordem dada e mapeia cada caractere para sua linha."""
    chunks: list[str] = []
    owners: list[int] = []
    for index in order:
        key = match_key(lines[index].text)
        if not key:
            continue
        chunks.append(key)
        owners.extend([index] * len(key))
    return "".join(chunks), owners


def _search_order(
    lines: tuple[OcrLine, ...],
    order: Sequence[int],
    snippet: str,
    needle: str,
    min_coverage: float,
) -> LocatedSpan | None:
    """Procura o needle numa ordem específica de linhas."""
    haystack, owners = _index_order(lines, order)
    if not haystack:
        return None

    position = haystack.find(needle)
    if position >= 0:
        start, end = position, position + len(needle)
    else:
        matcher = difflib.SequenceMatcher(None, needle, haystack, autojunk=False)
        block = matcher.find_longest_match(0, len(needle), 0, len(haystack))
        if block.size < min_coverage * len(needle):
            return None
        start, end = block.b, block.b + block.size

    indices = sorted({owners[i] for i in range(start, min(end, len(owners)))})
    if not indices:
        return None

    matched_text = " ".join(lines[i].text for i in indices)
    score = difflib.SequenceMatcher(
        None, read_key(snippet), read_key(matched_text), autojunk=False
    ).ratio()
    return LocatedSpan(line_indices=tuple(indices), matched_text=matched_text, score=score)


def locate_in_lines(
    lines: tuple[OcrLine, ...],
    snippet: str,
    min_coverage: float = 0.80,
) -> LocatedSpan | None:
    """Localiza um snippet nas linhas de uma página, tolerando ruído de OCR.

    Tenta duas ordens de leitura — a de detecção do OCR e a reconstruída — e
    devolve a melhor correspondência. A segunda só entra quando a primeira
    falha, de modo que nenhum grounding hoje válido regride.
    """
    needle = match_key(snippet)
    if not needle or len(needle) < 4:
        return None

    candidates = [
        _search_order(lines, range(len(lines)), snippet, needle, min_coverage),
        _search_order(
            lines, reading_order_indices(lines), snippet, needle, min_coverage
        ),
    ]
    found = [candidate for candidate in candidates if candidate is not None]
    if not found:
        return None
    return max(found, key=lambda candidate: candidate.score)


def bbox_from_lines(
    lines: tuple[OcrLine, ...],
    indices: tuple[int, ...],
    page_size_px: tuple[float, float],
) -> list[float]:
    """União das caixas das linhas indicadas, normalizada pelo tamanho da página."""
    w_px, h_px = page_size_px
    if w_px <= 0 or h_px <= 0:
        raise ValueError("dimensões de página inválidas")
    selected = [lines[i] for i in indices]
    return [
        min(line.x_min for line in selected) / w_px,
        min(line.y_min for line in selected) / h_px,
        max(line.x_max for line in selected) / w_px,
        max(line.y_max for line in selected) / h_px,
    ]


def ground_page(
    document: Document,
    page: int,
    snippet: str,
    min_score: float = 0.60,
) -> GroundingMatch | None:
    """Resolve um snippet numa página específica de um documento."""
    ocr_page = document.load_page(page)
    if ocr_page is None or not ocr_page.lines:
        return None
    size_px = document.page_size_px(page)
    if size_px is None:
        return None

    located = locate_in_lines(ocr_page.lines, snippet)
    if located is None or located.score < min_score:
        return None

    bbox = bbox_from_lines(ocr_page.lines, located.line_indices, size_px)
    if not bbox_is_valid(bbox):
        return None

    return GroundingMatch(
        doc_id=document.doc_id,
        page=page,
        bbox=bbox,
        snippet=snippet,
        matched_text=located.matched_text,
        score=located.score,
        line_indices=located.line_indices,
        page_size_px=size_px,
    )


def ground_document(
    document: Document,
    snippet: str,
    page: int | None = None,
    min_score: float = 0.60,
) -> GroundingMatch | None:
    """Varre o documento (ou uma página) até casar o snippet."""
    if not document.has_ocr:
        return None
    pages = [page] if page else document.ocr_pages
    best: GroundingMatch | None = None
    for number in pages:
        match = ground_page(document, number, snippet, min_score=min_score)
        if match is None:
            continue
        if best is None or match.score > best.score:
            best = match
        if match.score >= 0.999:
            break
    return best


def ground_siren(
    siren: str,
    snippet: str,
    kind: str = "actes",
    doc_id: str | None = None,
    page: int | None = None,
    min_score: float = 0.60,
) -> GroundingMatch | None:
    """Busca o snippet em todos os documentos de uma SIREN."""
    best: GroundingMatch | None = None
    for document in list_documents(siren, kind):
        if doc_id and document.doc_id != doc_id:
            continue
        match = ground_document(document, snippet, page=page, min_score=min_score)
        if match is None:
            continue
        if best is None or match.score > best.score:
            best = match
        if match.score >= 0.999:
            break
    return best
