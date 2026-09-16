"""Pré-filtro léxico de páginas e blocos societários.

Um acte tem dezenas de páginas de trâmite burocrático irrelevante. Enviar tudo
para a API encarece a execução e degrada a extração, porque dilui o sinal. Este
módulo reduz o contexto às páginas com vocabulário societário francês
relevante, **preservando a referência** (documento + página + linha) para que o
grounding posterior consiga resolver as coordenadas.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .ocr_loader import Document, OcrPage

#: Termos de ALTO sinal: ocorrem nas cláusulas de capital e de movimentação de
#: títulos. Cada um vale 3 pontos.
STRONG_TERMS: tuple[str, ...] = (
    "capital social",
    "article 7",
    "article 6",
    "cession",
    "feuille de présence",
    "parts sociales",
    "augmentation",
    "réduction",
    "valeur nominale",
    "registre des mouvements de titres",
    "résolution",
)

#: Termos de BAIXO sinal: aparecem em praticamente toda página de estatutos, de
#: modo que sozinhos não devem selecionar nada. Cada um vale 1 ponto.
WEAK_TERMS: tuple[str, ...] = (
    "actions",
    "associé",
    "actionnaire",
    "titres",
    "souscription",
    "assemblée générale",
    "quorum",
    "répartition",
    "statuts",
    "apport",
    "détenues par",
    "entièrement libérées",
)

ALL_TERMS: tuple[str, ...] = STRONG_TERMS + WEAK_TERMS

#: Nomenclatura usada pela diretiva técnica.
CORE_TERMS: tuple[str, ...] = STRONG_TERMS
EXTRA_TERMS: tuple[str, ...] = WEAK_TERMS

#: Peso de cada termo na triagem.
TERM_WEIGHTS: dict[str, int] = {
    **{term: 3 for term in STRONG_TERMS},
    **{term: 1 for term in WEAK_TERMS},
}

#: Score padrão: 3 exige ao menos um termo de alto sinal.
DEFAULT_MIN_SCORE = 3


def strip_accents(text: str) -> str:
    """Remove diacríticos preservando o comprimento aproximado do texto."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize(text: str) -> str:
    """Minúsculas, sem acentos, sem pontuação e com espaços colapsados."""
    lowered = strip_accents(text).lower()
    lowered = re.sub(r"[^\w%€]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


_NORMALIZED_TERMS: tuple[tuple[str, str], ...] = tuple(
    (term, normalize(term)) for term in ALL_TERMS
)
_STRONG_NORMALIZED = frozenset(normalize(term) for term in STRONG_TERMS)


@dataclass(frozen=True)
class PageScore:
    """Resultado da triagem de uma página."""

    page: int
    score: int
    hits: dict[str, int]
    relevant_lines: tuple[int, ...]

    @property
    def is_relevant(self) -> bool:
        return self.score > 0

    @property
    def matched_terms(self) -> tuple[str, ...]:
        return tuple(self.hits)


def scan_text(text: str) -> dict[str, int]:
    """Conta ocorrências de cada termo societário no texto informado."""
    haystack = normalize(text)
    hits: dict[str, int] = {}
    for term in ALL_TERMS:
        occurrences = haystack.count(normalize(term))
        if occurrences:
            hits[term] = occurrences
    return hits


def score_page(page: OcrPage) -> PageScore:
    """Pontua uma página (soma ponderada dos termos) e marca as linhas úteis."""
    hits = scan_text(page.text)
    weighted = sum(TERM_WEIGHTS.get(term, 1) for term in hits)

    relevant: list[int] = []
    terms_normalized = [(raw, norm) for raw, norm in ((t, normalize(t)) for t in hits)]
    for index, line in enumerate(page.lines):
        normalized_line = normalize(line.text)
        if any(norm in normalized_line for _, norm in terms_normalized):
            relevant.append(index)

    return PageScore(
        page=page.number,
        score=weighted,
        hits=hits,
        relevant_lines=tuple(relevant),
    )


def select_pages(
    document: Document,
    min_score: int = DEFAULT_MIN_SCORE,
    require_core: bool = True,
    page_range: tuple[int, int] | None = None,
) -> list[PageScore]:
    """Seleciona as páginas de um documento dignas de ir para a API.

    ``require_core`` exige a presença de ao menos um termo de alto sinal. Sem
    isso, a palavra "actions" — onipresente nos estatutos — faria o filtro
    devolver todas as páginas, anulando o ganho de contexto.
    """
    selected: list[PageScore] = []
    for page in document.iter_pages():
        if page_range and not (page_range[0] <= page.number <= page_range[1]):
            continue
        scored = score_page(page)
        if scored.score < min_score:
            continue
        if require_core and not (_STRONG_NORMALIZED & {normalize(t) for t in scored.hits}):
            continue
        selected.append(scored)
    return selected


def build_context(
    document: Document,
    pages: list[PageScore] | list[int],
    max_chars_per_page: int = 6000,
) -> str:
    """Monta o contexto textual de um documento, com marcadores de página.

    O formato ``### page=N`` é consumido pelo extrator para reportar o número
    da página de cada snippet e permitir o grounding posterior.
    """
    numbers = [p.page if isinstance(p, PageScore) else p for p in pages]
    blocks: list[str] = [f"### document inpi_id={document.doc_id} kind={document.kind}"]
    for number in numbers:
        text = document.page_text(number)
        if not text:
            continue
        if len(text) > max_chars_per_page:
            text = text[:max_chars_per_page] + "\n[TRUNCADO]"
        blocks.append(f"### page={number}\n{text}")
    return "\n\n".join(blocks)
DEFAULT_MIN_SCORE

def triage(siren: str, kind: str = "actes", min_score: int = 2) -> list[dict[str, object]]:
    """Triagem completa de uma empresa: páginas relevantes por documento."""
    from .ocr_loader import list_documents

    report: list[dict[str, object]] = []
    for document in list_documents(siren, kind):
        if not document.has_ocr:
            report.append(
                {
                    "doc_id": document.doc_id,
                    "deposit_date": document.deposit_date,
                    "decision": document.decision,
                    "has_ocr": False,
                    "pages_total": 0,
                    "pages_selected": 0,
                    "terms": {},
                }
            )
            continue
        selected = select_pages(document, min_score=min_score)
        merged: dict[str, int] = {}
        for item in selected:
            for term, count in item.hits.items():
                merged[term] = merged.get(term, 0) + count
        report.append(
            {
                "doc_id": document.doc_id,
                "deposit_date": document.deposit_date,
                "decision": document.decision,
                "has_ocr": True,
                "pages_total": len(document.ocr_pages),
                "pages_selected": len(selected),
                "selected": [p.page for p in selected],
                "terms": merged,
            }
        )
    return report
