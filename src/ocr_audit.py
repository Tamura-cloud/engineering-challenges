"""Auditoria dos erros do OCR fornecido.

O próprio ``NOTICE.md`` do acervo avisa: *"It contains errors, as OCR does."*
Este módulo existe para apontá-los em vez de herdá-los em silêncio.

**Achado que motiva o desenho:** o campo ``score`` de cada linha NÃO serve para
encontrar erro material. A linha comprovadamente errada

    "Le capital social est fixé à la somme de trente sept mille (37.0o0) euros."

tem score **0.988** — acima da mediana do acervo (0.991 contra 0.991, e as
piores pontuações são ruído de um caractere como ``o`` ou ``-``). Confiança alta
não é evidência de dígito correto.

A detecção útil é por **padrão**: tokens numéricos que contêm letras da classe de
confusão do OCR (o/0, l/1, s/5, b/8, g/6/9, z/2). É onde um erro custa caro — o
OCR grafa ``200.0euros`` onde o documento diz ``200.000 euros``, um desvio de
fator 1000, com score 0.96.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

from .ocr_loader import Document, list_documents

#: Letras que o OCR troca por dígitos com frequência.
CONFUSABLE_LETTERS = frozenset("oOlISsBbgGZz")

_SPLIT = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^0-9A-Za-z]")


@dataclass(frozen=True)
class OcrFinding:
    """Um token numérico suspeito, com a linha inteira para conferência."""

    doc_id: str
    page: int
    line_score: float
    tokens: tuple[str, ...]
    text: str

    def describe(self) -> str:
        return (
            f"{self.doc_id} p.{self.page} score={self.line_score:.3f} "
            f"token={'|'.join(self.tokens)} :: {self.text[:96]}"
        )


def suspicious_tokens(text: str) -> list[str]:
    """Tokens que misturam dígitos e letras de confusão do OCR.

    Exige ao menos dois dígitos e ao menos uma letra da classe suspeita, o que
    descarta palavras normais e numeração de artigo como ``I.1.1``.
    """
    found: list[str] = []
    for token in _SPLIT.split(text):
        core = _NON_ALNUM.sub("", token)
        if len(core) < 3:
            continue
        digits = sum(character.isdigit() for character in core)
        confusable = sum(character in CONFUSABLE_LETTERS for character in core)
        if digits >= 2 and confusable >= 1:
            found.append(token)
    return found


def scan_document(document: Document) -> list[OcrFinding]:
    """Varre um documento inteiro procurando tokens numéricos suspeitos."""
    findings: list[OcrFinding] = []
    for page in document.iter_pages():
        for line in page.lines:
            tokens = suspicious_tokens(line.text)
            if tokens:
                findings.append(
                    OcrFinding(
                        doc_id=document.doc_id,
                        page=page.number,
                        line_score=line.score,
                        tokens=tuple(tokens),
                        text=line.text,
                    )
                )
    return findings


def scan_siren(siren: str, kind: str = "actes") -> list[OcrFinding]:
    """Varre todos os documentos de uma SIREN."""
    findings: list[OcrFinding] = []
    for document in list_documents(siren, kind):
        if document.has_ocr:
            findings.extend(scan_document(document))
    return findings


def material_findings(
    findings: Sequence[OcrFinding], payload: dict
) -> list[OcrFinding]:
    """Filtra os achados que caem em páginas efetivamente citadas por um results.json.

    São os que importam: o resto do acervo não alimenta nenhuma alegação
    submetida, então não afeta a nota.
    """
    cited: set[tuple[str, int]] = set()
    for event in payload.get("events") or []:
        source = event.get("source") or {}
        if source.get("inpi_id") and source.get("page"):
            cited.add((str(source["inpi_id"]), int(source["page"])))
    for edge in (payload.get("group") or {}).get("edges") or []:
        source = edge.get("source") or {}
        if source.get("inpi_id") and source.get("page"):
            cited.add((str(source["inpi_id"]), int(source["page"])))
    return [item for item in findings if (item.doc_id, item.page) in cited]


def render(findings: Iterable[OcrFinding], limit: int | None = None) -> str:
    """Formata os achados para leitura no terminal."""
    items = list(findings)
    lines = [
        f"encontrados {len(items)} tokens numéricos suspeitos em linhas do OCR",
        f"{'doc':<26} {'pág':>4} {'score':>6}  tokens :: texto",
        "-" * 104,
    ]
    for finding in items[:limit] if limit else items:
        lines.append(
            f"{finding.doc_id:<26} {finding.page:>4} {finding.line_score:>6.3f}  "
            f"{'|'.join(finding.tokens)} :: {finding.text[:58]}"
        )
    return "\n".join(lines)
