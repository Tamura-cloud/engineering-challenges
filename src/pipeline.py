"""Orquestrador de ponta a ponta e benchmark contra um results.json de referência.

Fluxo::

    OCR + meta -> pré-filtro -> extração (DeepSeek) -> grounding -> ledger
              -> invariantes -> schema -> results_{siren}.json

O módulo **nunca** sobrescreve ``results.json`` da raiz por acidente: o destino
é sempre explícito, e o arquivo de referência é aberto apenas para leitura.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import extractor_llm, grounding, validator
from .config import CONTEXT_MAX_CHARS_PER_PAGE, SUBJECT_SIREN
from .ocr_loader import Document, list_documents, list_sirens
from .prefilter import DEFAULT_MIN_SCORE, select_pages

#: Ordem canônica de agrupamento dos estados de capital.
_CAPITAL_CODES = {"CAPITAL_INCREASE", "CAPITAL_DECREASE", "CAPITAL_DUAL_CLASS"}


@dataclass
class PipelineOptions:
    siren: str
    kind: str = "actes"
    min_page_score: int = DEFAULT_MIN_SCORE
    offline: bool = False
    ground_min_score: float = 0.60
    max_chars_per_page: int = CONTEXT_MAX_CHARS_PER_PAGE
    model: str | None = None
    doc_ids: list[str] = field(default_factory=list)


@dataclass
class PipelineReport:
    siren: str
    documents: int
    documents_with_ocr: int
    pages_selected: int
    events_extracted: int
    events_grounded: int
    events_dropped: int
    notes: list[str] = field(default_factory=list)
    payload: dict[str, Any] | None = None

    def render(self) -> str:
        lines = [
            f"SIREN .................. {self.siren}",
            f"Documentos ............. {self.documents} ({self.documents_with_ocr} com OCR)",
            f"Páginas selecionadas ... {self.pages_selected}",
            f"Eventos extraídos ...... {self.events_extracted}",
            f"Eventos ancorados ...... {self.events_grounded}",
            f"Eventos descartados .... {self.events_dropped}",
        ]
        if self.notes:
            lines.append("Avisos:")
            lines.extend(f"  - {note}" for note in self.notes)
        return "\n".join(lines)


# --------------------------------------------------------------------- ledger
def build_timeline(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dobra os eventos num ledger de conservação de ações e emite snapshots.

    O ledger é deliberadamente conservador: só calcula o que é inferível. Quando
    falta informação, o campo correspondente fica ``None`` em vez de ser
    estimado — o validador trata isso como falha, e é assim que deve ser.
    """
    ordered = sorted(
        events,
        key=lambda e: (str(e.get("event_date") or "9999-99-99"), str(e.get("event_id") or "")),
    )

    capital: float | None = None
    nominal: float | None = None
    holders: dict[str, float] = {}
    timeline: list[dict[str, Any]] = []
    pending: list[str] = []

    def snapshot(as_of: str) -> None:
        total = sum(holders.values()) if holders else None
        rows = []
        for name, shares in sorted(holders.items()):
            pct = None
            if total:
                pct = round(shares / total * 100.0, 2)
            rows.append(
                {
                    "name": name,
                    "siren": "499979540" if name.strip().upper() == "HADEAN" else None,
                    "kind": "COMPANY" if shares else "UNKNOWN",
                    "shares": shares,
                    "pct": pct,
                }
            )
        timeline.append(
            {
                "as_of": as_of,
                "capital_eur": capital,
                "shares_total": total,
                "nominal_eur": nominal,
                "holders": rows,
                "caused_by": list(pending),
            }
        )
        pending.clear()

    for event in ordered:
        code = str(event.get("event_code") or "")
        payload = event.get("payload") or {}
        as_of = str(event.get("event_date") or "")
        event_id = str(event.get("event_id") or "")
        if event_id:
            pending.append(event_id)

        if code in _CAPITAL_CODES:
            after = payload.get("capital_after_eur")
            if isinstance(after, (int, float)):
                capital = float(after)
            elif isinstance(payload.get("amount_eur"), (int, float)) and capital is not None:
                delta = float(payload["amount_eur"])
                capital = capital - delta if code == "CAPITAL_DECREASE" else capital + delta

            for key in ("nominal_after_eur", "nominal_eur"):
                value = payload.get(key)
                if isinstance(value, (int, float)) and value > 0:
                    nominal = float(value)
                    break
            if capital is not None and nominal:
                holders = {
                    name: shares * (nominal / nominal) for name, shares in holders.items()
                }

        elif code == "SHAREHOLDER_ENTRY":
            name = str(payload.get("holder_name") or "").strip()
            shares = payload.get("shares")
            if name:
                holders[name] = holders.get(name, 0.0) + (
                    float(shares) if isinstance(shares, (int, float)) else 0.0
                )

        elif code == "SHAREHOLDER_END":
            name = str(payload.get("holder_name") or "").strip()
            if name:
                holders.pop(name, None)

        elif code == "SHAREHOLDER_SHARE_TRANSFER":
            source = str(payload.get("from_name") or "").strip()
            target = str(payload.get("to_name") or "").strip()
            shares = payload.get("shares")
            if source and target and isinstance(shares, (int, float)):
                amount = float(shares)
                if source in holders:
                    holders[source] = max(0.0, holders[source] - amount)
                holders[target] = holders.get(target, 0.0) + amount

        if as_of and code in _CAPITAL_CODES:
            snapshot(as_of)

    return timeline


# ----------------------------------------------------------------- pipeline
def select_documents(options: PipelineOptions) -> tuple[list[Document], int]:
    """Seleciona documentos e conta páginas relevantes pelo pré-filtro."""
    documents = list_documents(options.siren, options.kind)
    if options.doc_ids:
        wanted = set(options.doc_ids)
        documents = [d for d in documents if d.doc_id in wanted]
    total_pages = 0
    for document in documents:
        if document.has_ocr:
            total_pages += len(select_pages(document, min_score=options.min_page_score))
    return documents, total_pages


def build_page_map(documents: Iterable[Document], min_score: int) -> dict[str, list[int]]:
    mapping: dict[str, list[int]] = {}
    for document in documents:
        if not document.has_ocr:
            continue
        chosen = select_pages(document, min_score=min_score)
        if chosen:
            mapping[document.doc_id] = [item.page for item in chosen]
    return mapping


def annotate_events(
    extracted: Sequence[extractor_llm.ExtractedEvent],
    documents: Sequence[Document],
    ground_min_score: float = 0.60,
) -> tuple[list[dict[str, Any]], list[str], int]:
    """Ancora cada evento extraído no OCR, descartando o que não for verificável."""
    index = {document.doc_id: document for document in documents}
    grounded: list[dict[str, Any]] = []
    notes: list[str] = []
    dropped = 0

    for order, event in enumerate(extracted, start=1):
        document = index.get(event.doc_id or "")
        if document is None:
            dropped += 1
            notes.append(f"descartado (documento desconhecido): {event.event_code}")
            continue
        match = grounding.ground_document(
            document,
            event.quote_snippet,
            page=event.page,
            min_score=ground_min_score,
        )
        if match is None:
            # O BRIEF é explícito: "An event you cannot ground is still worth
            # reporting, with a note saying so." O evento não entra em events[]
            # (o schema exige source completo), mas a alegação é preservada
            # integralmente para o campo notes em vez de sumir em silêncio.
            dropped += 1
            notes.append(
                "SEM GROUNDING — alegação preservada para notes: "
                f"{event.event_code} em {event.event_date or 'data não determinada'}; "
                f"trecho não localizado em {document.doc_id} p.{event.page}; "
                f"payload={event.payload}; trecho={event.quote_snippet[:80]!r}"
            )
            continue

        date = event.event_date or document.deposit_date
        grounded.append(
            {
                "event_id": f"evt_{date}_{event.event_code.lower()}_{order:03d}",
                "event_code": event.event_code,
                "event_date": date,
                "payload": event.payload,
                "source": match.as_source(),
                "grounding": {
                    "score": round(match.score, 4),
                    "matched_text": match.matched_text,
                },
            }
        )
    return grounded, notes, dropped


def run(options: PipelineOptions) -> PipelineReport:
    """Executa o pipeline completo conforme as opções dadas."""
    documents, pages_selected = select_documents(options)
    with_ocr = [document for document in documents if document.has_ocr]
    report = PipelineReport(
        siren=options.siren,
        documents=len(documents),
        documents_with_ocr=len(with_ocr),
        pages_selected=pages_selected,
        events_extracted=0,
        events_grounded=0,
        events_dropped=0,
    )

    if options.offline:
        report.notes.append("modo offline: extração por LLM não executada")
        return report

    page_map = build_page_map(with_ocr, options.min_page_score)
    events, extraction_notes = extractor_llm.extract_events(
        with_ocr,
        page_map=page_map,
        model=options.model or extractor_llm.DEEPSEEK_MODEL,
    )
    report.events_extracted = len(events)
    report.notes.extend(extraction_notes)

    grounded, grounding_notes, dropped = annotate_events(
        events, with_ocr, ground_min_score=options.ground_min_score
    )
    report.notes.extend(grounding_notes)
    report.events_grounded = len(grounded)
    report.events_dropped = dropped

    timeline = build_timeline(grounded)
    payload: dict[str, Any] = {
        "siren": options.siren,
        "events": grounded,
        "capital_timeline": timeline,
    }
    if options.siren != SUBJECT_SIREN:
        payload["notes"] = (
            "Gerado para SIREN distinto da empresa sujeita do desafio "
            f"({SUBJECT_SIREN}); o schema oficial fixa a SIREN como constante."
        )
    ok, checks, errors = validator.audit(payload)
    report.payload = payload
    if not ok:
        report.notes.append("auditoria algébrica/schema não passou:")
        report.notes.extend(f"  {check}" for check in checks if not check.passed)
        report.notes.extend(f"  schema: {error}" for error in errors)
    return report


def write_payload(payload: dict[str, Any], output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return output


# ---------------------------------------------------------------- benchmark
@dataclass
class BenchmarkRow:
    event_id: str
    cited_doc: str
    cited_page: int | None
    status: str
    found_docs: list[str]
    bbox_delta: float | None


def benchmark(reference_path: Path, kind: str = "actes") -> tuple[list[BenchmarkRow], dict[str, Any]]:
    """Re-ancora os eventos de um results.json de referência, medindo o grounding.

    A referência é uma reconstrução nossa, não um gabarito externo: o que a
    checagem mede é a consistência entre a alegação e a evidência no OCR, não a
    correção da interpretação.

    Para cada evento do arquivo de referência: procura o ``snippet`` no OCR de
    todos os documentos da empresa e, se não achar, no resto do acervo.

    A segunda passada não é conveniência. O BRIEF avisa que algumas dessas
    relações não aparecem nos documentos da própria empresa e exigem ir olhar a
    controladora. Quando um ato da HADEAN é a prova de uma saída na cap table da
    Archean, uma conferência que só olhasse a pasta da Archean diria AUSENTE — e
    estaria errada.
    """
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    siren = str(reference.get("siren") or SUBJECT_SIREN)
    primary = [doc for doc in list_documents(siren, kind) if doc.has_ocr]

    lines_cache: dict[tuple[str, int], tuple] = {}

    def page_lines(document: Document, page: int) -> tuple:
        cached = lines_cache.get((document.doc_id, page))
        if cached is None:
            loaded = document.load_page(page)
            cached = loaded.lines if loaded else ()
            lines_cache[(document.doc_id, page)] = cached
        return cached

    def scan(documents: Sequence[Document], snippet: str) -> list[str]:
        hits: list[str] = []
        for document in documents:
            for page in document.ocr_pages:
                if grounding.locate_in_lines(page_lines(document, page), snippet):
                    hits.append(f"{document.doc_id} p{page}")
        return hits

    elsewhere: list[Document] = []
    elsewhere_loaded = False

    rows: list[BenchmarkRow] = []
    for event in reference.get("events") or []:
        source = event.get("source") or {}
        snippet = source.get("snippet") or ""
        found = scan(primary, snippet)
        if not found:
            if not elsewhere_loaded:
                elsewhere = [
                    doc
                    for other in list_sirens()
                    if other != siren
                    for doc in list_documents(other, kind)
                    if doc.has_ocr
                ]
                elsewhere_loaded = True
            found = scan(elsewhere, snippet)

        cited_doc = str(source.get("inpi_id") or "")
        cited_page = source.get("page")
        if not found:
            status = "AUSENTE_NO_ACERVO"
        elif any(item.startswith(cited_doc) for item in found):
            status = "CITADO_OK"
        else:
            status = "DOC_ERRADO"

        delta: float | None = None
        document = next(
            (doc for doc in (primary + elsewhere) if doc.doc_id == cited_doc), None
        )
        if status == "CITADO_OK" and document is not None:
            match = grounding.ground_document(
                document, snippet, page=cited_page, min_score=0.0
            )
            declared = source.get("bbox")
            if match is not None and isinstance(declared, list) and len(declared) == 4:
                delta = max(abs(a - b) for a, b in zip(match.bbox, declared))

        rows.append(
            BenchmarkRow(
                event_id=str(event.get("event_id") or ""),
                cited_doc=cited_doc,
                cited_page=cited_page,
                status=status,
                found_docs=found,
                bbox_delta=delta,
            )
        )

    summary = {
        "total": len(rows),
        "citado_ok": sum(1 for row in rows if row.status == "CITADO_OK"),
        "doc_errado": sum(1 for row in rows if row.status == "DOC_ERRADO"),
        "ausente": sum(1 for row in rows if row.status == "AUSENTE_NO_ACERVO"),
        "bbox_exata": sum(
            1 for row in rows if row.bbox_delta is not None and row.bbox_delta < 0.002
        ),
    }
    return rows, summary


def render_benchmark(rows: Sequence[BenchmarkRow], summary: dict[str, Any]) -> str:
    icon = {"CITADO_OK": "OK       ", "DOC_ERRADO": "DOC_ERRADO", "AUSENTE_NO_ACERVO": "AUSENTE  "}
    lines = [f"{'evento':<46} {'status':<10} {'delta':>7}  evidência"]
    lines.append("-" * 110)
    for row in rows:
        delta = f"{row.bbox_delta:.4f}" if row.bbox_delta is not None else "-"
        evidence = ", ".join(row.found_docs) or "-"
        lines.append(
            f"{row.event_id[:46]:<46} {icon[row.status]:<10} {delta:>7}  {evidence}"
        )
    lines.append("-" * 110)
    lines.append(
        "total={total}  citado_ok={citado_ok}  doc_errado={doc_errado}  "
        "ausente={ausente}  bbox_exata={bbox_exata}".format(**summary)
    )
    return "\n".join(lines)
