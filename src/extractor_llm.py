"""Extração semântica estruturada via API da DeepSeek (JSON Mode).

A IA atua como especialista em direito societário francês e devolve eventos em
JSON estrito. Ela **nunca** devolve coordenadas: o modelo só entrega o trecho
literal (``quote_snippet``) e a página, e o ``src.grounding`` resolve a bbox a
partir do OCR. Isso remove a principal fonte de alucinação espacial.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .config import DEEPSEEK_MODEL, DEEPSEEK_TEMPERATURE, EVENT_CODES_PATH, get_client
from .ocr_loader import Document
from .prefilter import build_context

#: Códigos aceitos. O subconjunto pontuável vem de ``event_codes.json``.
FALLBACK_CODES: tuple[str, ...] = (
    "CAPITAL_INCREASE",
    "CAPITAL_DECREASE",
    "SHAREHOLDER_ENTRY",
    "SHAREHOLDER_END",
    "SHAREHOLDER_SHARE_TRANSFER",
    "CAPITAL_DUAL_CLASS",
)


def load_event_codes() -> tuple[str, ...]:
    """Lê os códigos oficiais do schema; usa o fallback se o arquivo faltar."""
    try:
        payload = json.loads(EVENT_CODES_PATH.read_text(encoding="utf-8"))
        codes = tuple(entry["event_code"] for entry in payload.get("codes") or [])
        return codes or FALLBACK_CODES
    except (OSError, KeyError, json.JSONDecodeError):
        return FALLBACK_CODES


SYSTEM_PROMPT = """\
Tu es un expert en droit des sociétés français (Code de commerce) et en
reconstruction de cap tables à partir d'actes déposés au registre du commerce.

Tu reçois le texte OCR, page par page, d'UN acte de société. Tu dois en extraire
UNIQUEMENT les mouvements de capital et d'actionnariat, avec la preuve littérale.

RÈGLES ABSOLUES
1. N'invente jamais un chiffre, un nom ou une date. Si une information n'est pas
   dans le texte fourni, ne la produis pas.
2. `quote_snippet` DOIT être un extrait CONTIGU et LITTÉRAL du texte OCR fourni,
   de 8 à 25 mots, copié caractère pour caractère (y compris les erreurs d'OCR).
   Ne corrige pas l'orthographe, ne reformule pas, ne traduis pas.
3. `page` est le numéro de page 1-indexé où se trouve cet extrait, tel qu'indiqué
   par les balises `### page=N` du texte fourni.
4. `event_date` est la date à laquelle la décision a pris effet (la date de
   l'assemblée ou de la décision), au format YYYY-MM-DD. Ce n'est PAS la date de
   dépôt. Si elle est introuvable, mets null.
5. Hors périmètre: commissaires aux comptes, dirigeants, transferts de siège,
   changements d'objet social ou de dénomination. Ignore-les.
6. `nominal_eur` est la valeur nominale d'UNE part (ex. 10), jamais le capital.
   Indique-la dès qu'elle apparaît dans le texte.
7. NE CONFONDS PAS composition et NOMBRE de titres. Quand une augmentation de
   capital attribue des titres nouveaux aux associés existants, les
   POURCENTAGES peuvent rester identiques (ex. 51/49) alors que le NOMBRE de
   titres change. Ce n'est PAS « aucun mouvement »: la cap table a changé.
   Émets l'événement ET remplis `allocation` avec les titres attribués à
   chacun. Ne conclus jamais à l'absence de mouvement au seul motif que les
   pourcentages sont stables.

CODES D'ÉVÉNEMENT AUTORISÉS
- CAPITAL_INCREASE  : le capital social nominal augmente.
  payload: amount_eur, capital_after_eur, nominal_eur, method,
           allocation — OBLIGATOIRE si des titres nouveaux sont attribués
           nommément. C'est le nombre de titres NOUVEAUX créés pour chacun
           (un delta), PAS le total détenu après l'opération, sous la forme
           {"Nom Prénom": nombre_de_titres_nouveaux, ...}
  method ∈ {numeraire, incorporation de reserves, apport en nature, autre}
- CAPITAL_DECREASE : le capital social nominal diminue.
  payload: amount_eur, capital_after_eur, nominal_eur, method
- SHAREHOLDER_ENTRY : une personne entre au capital.
  payload: holder_name, shares (optionnel)
- SHAREHOLDER_END : une personne sort totalement du capital.
  payload: holder_name, shares (optionnel)
- SHAREHOLDER_SHARE_TRANSFER : des titres passent d'un cédant à un cessionnaire.
  payload: from_name, to_name, shares, price_eur (optionnel)
- CAPITAL_DUAL_CLASS : division de la valeur nominale ou création de classes
  d'actions préférentielles.
  payload: split_factor (optionnel), nominal_before_eur, nominal_after_eur,
           amount_eur (optionnel)

Attention: une cession et une entrée/sortie peuvent décrire le même mouvement vu
de deux côtés. Émets les deux si le texte le justifie, sans dupliquer.

FORMAT DE SORTIE — réponds UNIQUEMENT avec un objet JSON:
{
  "events": [
    {
      "event_code": "CAPITAL_INCREASE",
      "event_date": "2006-10-20",
      "page": 3,
      "quote_snippet": "extrait littéral contigu du texte OCR",
      "payload": {"amount_eur": 50000, "capital_after_eur": 200000,
                  "nominal_eur": 10, "method": "numeraire"},
      "confidence": 0.0
    },
    {
      "event_code": "CAPITAL_INCREASE",
      "event_date": "2022-01-20",
      "page": 3,
      "quote_snippet": "extrait littéral contigu du texte OCR",
      "payload": {"amount_eur": 40000, "capital_after_eur": 50000,
                  "nominal_eur": 10, "method": "incorporation de reserves",
                  "allocation": {"Madame A": 3000, "Monsieur B": 1000}},
      "confidence": 0.0
    }
  ],
  "notes": "ambiguïtés, contradictions, informations manquantes"
}
S'il n'y a aucun mouvement de capital dans ce document, renvoie
{"events": [], "notes": "..."}. N'ajoute aucun texte hors du JSON.
"""


@dataclass(frozen=True)
class ExtractedEvent:
    """Evento proposto pelo modelo, ainda **não** ancorado espacialmente."""

    event_code: str
    event_date: str | None
    page: int | None
    quote_snippet: str
    payload: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    doc_id: str | None = None

    def key(self) -> tuple[str, str | None, str]:
        return (self.event_code, self.event_date, self.quote_snippet[:60].lower())


@dataclass
class ExtractionResult:
    events: list[ExtractedEvent] = field(default_factory=list)
    notes: str = ""
    raw: dict[str, Any] | None = None
    error: str | None = None


def _coerce_page(value: Any) -> int | None:
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if page >= 1 else None


def _coerce_date(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    return match.group(0) if match else None


def _coerce_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def parse_response(content: str, doc_id: str | None = None) -> ExtractionResult:
    """Converte a resposta bruta do modelo em eventos tipados."""
    result = ExtractionResult()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        result.error = f"JSON inválido devolvido pelo modelo: {exc}"
        return result

    if not isinstance(payload, dict):
        result.error = "a resposta não é um objeto JSON"
        return result

    result.raw = payload
    notes = payload.get("notes")
    result.notes = notes if isinstance(notes, str) else ""

    allowed = set(load_event_codes()) | set(FALLBACK_CODES)
    for entry in payload.get("events") or []:
        if not isinstance(entry, dict):
            continue
        code = str(entry.get("event_code") or "").strip().upper()
        snippet = entry.get("quote_snippet") or entry.get("snippet") or ""
        if code not in allowed or not isinstance(snippet, str) or len(snippet.strip()) < 4:
            continue
        try:
            confidence = float(entry.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        result.events.append(
            ExtractedEvent(
                event_code=code,
                event_date=_coerce_date(entry.get("event_date")),
                page=_coerce_page(entry.get("page")),
                quote_snippet=snippet.strip(),
                payload=_coerce_payload(entry.get("payload")),
                confidence=confidence,
                doc_id=doc_id,
            )
        )
    return result


def extract_document(
    document: Document,
    pages: Sequence[int] | None = None,
    client: Any | None = None,
    model: str = DEEPSEEK_MODEL,
    temperature: float = DEEPSEEK_TEMPERATURE,
    max_chars_per_page: int = 6000,
) -> ExtractionResult:
    """Extrai os eventos de capital de um único documento."""
    if not document.has_ocr:
        return ExtractionResult(error="documento sem OCR disponível")

    selected = list(pages) if pages else document.ocr_pages
    if not selected:
        return ExtractionResult(error="nenhuma página selecionada para extração")

    from .prefilter import PageScore

    context = build_context(
        document,
        [PageScore(page=p, score=0, hits={}, relevant_lines=()) for p in selected],
        max_chars_per_page=max_chars_per_page,
    )

    header = (
        f"Document: {document.kind} déposé le {document.deposit_date}, "
        f"inpi_id={document.doc_id}"
    )
    if document.decision:
        header += f", objet déclaré: {document.decision}"

    active = client if client is not None else get_client()
    completion = active.chat.completions.create(
        model=model,
        temperature=temperature,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{header}\n\n{context}"},
        ],
    )
    content = completion.choices[0].message.content or ""
    return parse_response(content, doc_id=document.doc_id)


def extract_events(
    documents: Iterable[Document],
    page_map: dict[str, Sequence[int]] | None = None,
    client: Any | None = None,
    model: str = DEEPSEEK_MODEL,
) -> tuple[list[ExtractedEvent], list[str]]:
    """Percorre vários documentos, acumulando eventos e avisos."""
    events: list[ExtractedEvent] = []
    notes: list[str] = []
    for document in documents:
        pages = (page_map or {}).get(document.doc_id)
        outcome = extract_document(document, pages=pages, client=client, model=model)
        if outcome.error:
            notes.append(f"{document.doc_id}: {outcome.error}")
            continue
        events.extend(outcome.events)
        if outcome.notes:
            notes.append(f"{document.doc_id}: {outcome.notes}")

    deduped: list[ExtractedEvent] = []
    seen: set[tuple[str, str | None, str]] = set()
    for event in events:
        signature = event.key()
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(event)

    return deduped, notes
