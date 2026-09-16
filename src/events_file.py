"""Eventos em arquivo e ancoragem automática das citações.

Separa definitivamente os dois papéis do projeto:

* **quem lê** (uma IA ou uma pessoa) escreve apenas as **alegações** — código do
  evento, data de efeito, valores e a **citação literal** com documento e página;
* **o código** resolve a bbox, dobra o ledger, calcula totais e percentuais,
  confere os invariantes e valida o schema.

A bbox **nunca** vem do arquivo de entrada: é sempre recalculada a partir da
citação. Um evento cuja citação não é localizável não entra em ``events[]`` —
mas também não desaparece: vai para as notas, como o brief exige
(*"an event you cannot ground is still worth reporting, with a note saying so"*).

Formato de entrada::

    {
      "siren": "820561470",
      "denomination": "SARL PAUTET",
      "kind": "actes",
      "events": [
        {
          "event_id": "evt_2016-05-18_incorp_capital",
          "event_code": "CAPITAL_INCREASE",
          "event_date": "2016-05-18",
          "payload": {"capital_after_eur": 10000.0, "nominal_eur": 10.0},
          "evidence": {
            "doc_id": "63e1f90fd0f29b5aaa069b71",
            "page": 2,
            "snippet": "Société à Responsabilité Limitée au capital de 10 000,00 euros"
          }
        }
      ]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from . import grounding
from .ocr_loader import list_documents


@dataclass
class AnchorReport:
    """Resultado da ancoragem de um evento."""

    event_id: str
    grounded: bool
    page: int | None = None
    bbox: list[float] | None = None
    score: float | None = None
    reason: str = ""
    claim: str = ""


@dataclass
class Anchored:
    siren: str
    denomination: str = ""
    kind: str = "actes"
    events: list[dict[str, Any]] = field(default_factory=list)
    reports: list[AnchorReport] = field(default_factory=list)

    @property
    def grounded_count(self) -> int:
        return sum(1 for report in self.reports if report.grounded)

    @property
    def notes(self) -> list[str]:
        return [
            f"SEM GROUNDING — {report.claim}; {report.reason}" for report in self.reports if not report.grounded
        ]


def load_events_file(path: Path) -> dict[str, Any]:
    """Lê o arquivo de eventos escrito por quem leu os documentos."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or "siren" not in payload or "events" not in payload:
        raise ValueError(f"{path.name}: esperado um objeto com as chaves 'siren' e 'events'")
    return payload


def anchor(spec: dict[str, Any], min_score: float = 0.60) -> Anchored:
    """Ancora cada evento de uma especificação no OCR do acervo."""
    siren = str(spec["siren"])
    kind = str(spec.get("kind") or "actes")
    documents = {document.doc_id: document for document in list_documents(siren, kind)}

    result = Anchored(siren=siren, denomination=str(spec.get("denomination") or ""), kind=kind)

    for entry in spec.get("events") or []:
        event_id = str(entry.get("event_id") or "?")
        evidence = entry.get("evidence") or {}
        doc_id = str(evidence.get("doc_id") or "")
        page = evidence.get("page")
        snippet = str(evidence.get("snippet") or "")
        claim = f"{entry.get('event_code')} em {entry.get('event_date')}"

        document = documents.get(doc_id)
        if document is None:
            result.reports.append(
                AnchorReport(event_id, False, reason=f"documento {doc_id or '(vazio)'} não existe no acervo", claim=claim)
            )
            continue
        if not document.has_ocr:
            result.reports.append(
                AnchorReport(event_id, False, reason=f"{doc_id} não tem OCR", claim=claim)
            )
            continue

        wanted = int(page) if isinstance(page, int) else None
        match = grounding.ground_document(document, snippet, page=wanted, min_score=min_score)
        if match is None:
            result.reports.append(
                AnchorReport(
                    event_id,
                    False,
                    reason=f"citação não localizada em {doc_id} p.{wanted}: {snippet[:70]!r}",
                    claim=claim,
                )
            )
            continue

        result.events.append(
            {
                "event_id": event_id,
                "event_code": str(entry.get("event_code") or ""),
                "event_date": str(entry.get("event_date") or document.deposit_date),
                "payload": entry.get("payload") or {},
                "source": match.as_source(),
            }
        )
        result.reports.append(
            AnchorReport(event_id, True, page=match.page, bbox=match.bbox, score=match.score, claim=claim)
        )

    return result


def render_report(anchored: Anchored) -> str:
    """Resumo legível da ancoragem, para o terminal."""
    lines = [
        f"{anchored.denomination or anchored.siren}: "
        f"{anchored.grounded_count}/{len(anchored.reports)} eventos ancorados",
        f"{'evento':<46} {'pág':>4} {'similaridade':>12}  bbox",
        "-" * 104,
    ]
    for report in anchored.reports:
        if report.grounded:
            box = ", ".join(f"{value:.4f}" for value in report.bbox or [])
            lines.append(f"{report.event_id[:46]:<46} {report.page:>4} {report.score:>12.3f}  [{box}]")
        else:
            lines.append(f"{report.event_id[:46]:<46} {'—':>4} {'FALHA':>12}  {report.reason}")
    return "\n".join(lines)
