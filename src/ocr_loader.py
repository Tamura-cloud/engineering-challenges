"""Leitor universal do acervo de OCR e metadados do INPI.

Layout real do corpus — **um diretório por documento, um JSON por página**:

    data/{siren}/actes/meta/acte_{YYYY-MM-DD}_{inpi_id}.json
    data/{siren}/actes/ocr/{inpi_id}/page_NNN.json
    data/{siren}/actes/pdf/acte_{YYYY-MM-DD}_{inpi_id}.pdf

A mesma forma vale para ``bilans/``. A cobertura de OCR é irregular: alguns
documentos simplesmente não possuem pasta em ``ocr/`` — nesse caso
``Document.has_ocr`` é ``False`` e o pipeline deve degradar com aviso, nunca
inventar coordenadas.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from .config import DATA_DIR, PX_PER_POINT

KINDS = ("actes", "bilans")

_STEM_RE = re.compile(
    r"^(?P<kind>[A-Za-z]+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<doc_id>[0-9a-fA-F]{16,40})$"
)
_PAGE_RE = re.compile(r"^page_(\d+)\.json$")


@dataclass(frozen=True)
class OcrLine:
    """Linha de OCR com polígono em pixels a 300 dpi (origem no canto superior esquerdo)."""

    page: int
    text: str
    polygon: tuple[tuple[float, float], ...]
    score: float = 0.0
    orientation_angle: int = 0

    @property
    def x_min(self) -> float:
        return min(pt[0] for pt in self.polygon)

    @property
    def x_max(self) -> float:
        return max(pt[0] for pt in self.polygon)

    @property
    def y_min(self) -> float:
        return min(pt[1] for pt in self.polygon)

    @property
    def y_max(self) -> float:
        return max(pt[1] for pt in self.polygon)


@dataclass(frozen=True)
class OcrPage:
    """Uma página de OCR: número 1-indexado e suas linhas."""

    number: int
    lines: tuple[OcrLine, ...]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)

    def __bool__(self) -> bool:
        return bool(self.lines)


@dataclass
class Document:
    """Um acte (ou bilan) do acervo, com metadados, OCR e PDF associados."""

    siren: str
    kind: str
    doc_id: str
    deposit_date: str
    stem: str
    meta_path: Path | None = None
    ocr_dir: Path | None = None
    pdf_path: Path | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    _pdf: Any = field(default=None, repr=False, compare=False)
    _sizes: dict[int, tuple[float, float]] = field(default_factory=dict, repr=False, compare=False)

    # ---------------------------------------------------------------- meta
    @property
    def denomination(self) -> str | None:
        value = self.meta.get("denomination")
        return value.strip() if isinstance(value, str) else None

    @property
    def decision(self) -> str | None:
        """Assunto declarado pelo registro (``typeRdd[].decision``)."""
        for entry in self.meta.get("typeRdd") or []:
            if isinstance(entry, dict):
                decision = entry.get("decision")
                if isinstance(decision, str) and decision.strip():
                    return decision.strip()
        return None

    @property
    def label(self) -> str:
        return f"{self.kind[:-1]}#{self.doc_id[:8]}…({self.deposit_date})"

    # ----------------------------------------------------------------- OCR
    @property
    def has_ocr(self) -> bool:
        return self.ocr_dir is not None and self.ocr_dir.is_dir()

    @property
    def ocr_pages(self) -> list[int]:
        """Números de página com OCR disponível, em ordem crescente."""
        if not self.ocr_dir or not self.ocr_dir.is_dir():
            return []
        found: list[int] = []
        for path in self.ocr_dir.glob("page_*.json"):
            match = _PAGE_RE.match(path.name)
            if match:
                found.append(int(match.group(1)))
        return sorted(found)

    def ocr_page_path(self, page: int) -> Path | None:
        if self.ocr_dir is None:
            return None
        candidate = self.ocr_dir / f"page_{page:03d}.json"
        return candidate if candidate.is_file() else None

    def load_page(self, page: int) -> OcrPage | None:
        """Carrega uma página de OCR, devolvendo ``None`` se ausente."""
        path = self.ocr_page_path(page)
        if path is None:
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        lines: list[OcrLine] = []
        for item in raw.get("ocr") or []:
            polygon = item.get("polygon") or []
            text = item.get("text") or ""
            if len(polygon) < 2 or not text.strip():
                continue
            lines.append(
                OcrLine(
                    page=page,
                    text=text,
                    polygon=tuple((float(pt[0]), float(pt[1])) for pt in polygon),
                    score=float(item.get("score") or 0.0),
                    orientation_angle=int(item.get("orientation_angle") or 0),
                )
            )
        return OcrPage(number=page, lines=tuple(lines))

    def iter_pages(self) -> Iterator[OcrPage]:
        for page in self.ocr_pages:
            loaded = self.load_page(page)
            if loaded is not None:
                yield loaded

    def page_text(self, page: int) -> str:
        loaded = self.load_page(page)
        return loaded.text if loaded else ""

    def full_text(self) -> str:
        return "\n\n".join(page.text for page in self.iter_pages())

    # ------------------------------------------------------------ geometria
    def _ensure_pdf(self) -> Any:
        if self._pdf is not None:
            return self._pdf
        if self.pdf_path is None or not self.pdf_path.is_file():
            return None
        try:
            import pymupdf
        except ImportError:  # pragma: no cover - fallback para o nome legado
            import fitz as pymupdf
        self._pdf = pymupdf.open(self.pdf_path)
        return self._pdf

    @property
    def pdf_page_count(self) -> int | None:
        doc = self._ensure_pdf()
        return None if doc is None else int(doc.page_count)

    def page_size_points(self, page: int) -> tuple[float, float] | None:
        """Dimensões da página em pontos, conforme declaradas pelo PDF."""
        if page in self._sizes:
            return self._sizes[page]
        doc = self._ensure_pdf()
        if doc is None or not 1 <= page <= doc.page_count:
            return None
        rect = doc[page - 1].rect
        size = (float(rect.width), float(rect.height))
        self._sizes[page] = size
        return size

    def page_size_px(self, page: int) -> tuple[float, float] | None:
        """Dimensões da página no espaço de pixels do OCR (pontos x 300/72)."""
        size = self.page_size_points(page)
        if size is None:
            return None
        return (size[0] * PX_PER_POINT, size[1] * PX_PER_POINT)

    def close(self) -> None:
        if self._pdf is not None:
            self._pdf.close()
            self._pdf = None


def _document_from_stem(siren: str, kind: str, stem: str) -> Document | None:
    match = _STEM_RE.match(stem)
    if not match:
        return None
    return Document(
        siren=siren,
        kind=kind,
        doc_id=match.group("doc_id"),
        deposit_date=match.group("date"),
        stem=stem,
    )


def list_documents(siren: str, kind: str = "actes") -> list[Document]:
    """Lista os documentos de uma SIREN, ordenados cronologicamente pelo depósito.

    A união é feita sobre ``meta/``, ``ocr/`` e ``pdf/``, de modo que um
    documento sem metadados (ou sem OCR) ainda apareça no resultado.
    """
    base = DATA_DIR / siren / kind
    documents: dict[str, Document] = {}

    def slot(stem: str) -> Document | None:
        doc = _document_from_stem(siren, kind, stem)
        if doc is None:
            return None
        return documents.setdefault(doc.doc_id, doc)

    meta_dir = base / "meta"
    if meta_dir.is_dir():
        for path in sorted(meta_dir.glob("*.json")):
            doc = slot(path.stem)
            if doc is None:
                continue
            doc.meta_path = path
            try:
                doc.meta = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                doc.meta = {}

    ocr_root = base / "ocr"
    if ocr_root.is_dir():
        for child in sorted(ocr_root.iterdir()):
            if not child.is_dir():
                continue
            existing = documents.get(child.name)
            if existing is None:
                # Documento sem meta nem pdf conhecido: usa a data do depósito
                # apenas se o nome da pasta não a fornecer.
                existing = Document(
                    siren=siren,
                    kind=kind,
                    doc_id=child.name,
                    deposit_date="",
                    stem=f"{kind[:-1]}__{child.name}",
                )
                documents[child.name] = existing
            existing.ocr_dir = child

    pdf_dir = base / "pdf"
    if pdf_dir.is_dir():
        for path in sorted(pdf_dir.glob("*.pdf")):
            doc = slot(path.stem)
            if doc is not None:
                doc.pdf_path = path

    return sorted(
        documents.values(),
        key=lambda d: (d.deposit_date or "9999", d.doc_id),
    )


def load_company(siren: str) -> dict[str, list[Document]]:
    """Carrega os documentos de todos os tipos disponíveis para uma SIREN."""
    return {kind: list_documents(siren, kind) for kind in KINDS}


def list_sirens() -> list[str]:
    """Todas as SIRENs presentes no acervo, em ordem numérica."""
    if not DATA_DIR.is_dir():
        return []
    return sorted(p.name for p in DATA_DIR.iterdir() if p.is_dir() and p.name.isdigit())


def summarize(siren: str) -> dict[str, Any]:
    """Resumo de cobertura: útil para diagnóstico rápido via CLI."""
    summary: dict[str, Any] = {"siren": siren, "kinds": {}}
    for kind in KINDS:
        documents = list_documents(siren, kind)
        with_ocr = [d for d in documents if d.has_ocr]
        summary["kinds"][kind] = {
            "documents": len(documents),
            "with_ocr": len(with_ocr),
            "pages": sum(len(d.ocr_pages) for d in with_ocr),
            "missing_ocr": [d.doc_id for d in documents if not d.has_ocr],
        }
    return summary
