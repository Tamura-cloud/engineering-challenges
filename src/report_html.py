"""Relatório HTML de verificação visual do grounding.

Para cada evento do ``results.json``: renderiza a **página do PDF** recortada na
região da citação, desenha a caixa declarada por cima, e mostra lado a lado a
alegação do arquivo e o texto bruto que o OCR põe dentro daquela caixa.

O desenho é deliberado. Comparar JSON com OCR é verificação circular: o OCR é
justamente o que está sob suspeita. A única fonte de verdade é a imagem — já
aconteceu de o OCR ler ``(37.0o0)`` onde a imagem diz ``(37.000)``. Por isso os
três aparecem juntos, e o humano olha **a imagem**, usando o OCR apenas como
indício.

A geometria é lida **por página**, nunca por constante: no mesmo acervo as
páginas medem 595x842 pt, 1653x2375 pt, 1654x2353 pt e 1664x2353 pt.
"""

from __future__ import annotations

import base64
import html
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from . import grounding
from .ocr_loader import Document, list_documents, list_sirens

_MAX_RENDER_PX = 1500
_MIN_DPI = 80
_MAX_DPI = 220


@dataclass(frozen=True)
class Evidence:
    """Uma alegação pronta para ser conferida a olho."""

    event_id: str
    event_code: str
    event_date: str
    payload: dict[str, Any]
    doc_id: str
    page: int
    bbox: list[float]
    snippet: str
    matched_text: str
    score: float
    png_base64: str
    png_page: str
    ocr_in_box: str

    @property
    def reproducible(self) -> bool:
        return self.score >= 0.99


def _open_pdf(document: Document):
    try:
        import pymupdf
    except ImportError:  # pragma: no cover
        import fitz as pymupdf
    return pymupdf.open(document.pdf_path)


def render_crop(document: Document, page: int, bbox: Sequence[float], margin: float = 0.012) -> str:
    """Recorta a região da bbox e devolve um PNG em base64.

    A resolução é escolhida para que a largura final fique legível sem estourar
    um tamanho fixo de pixels — a mesma lógica para páginas de qualquer tamanho.
    """
    if document.pdf_path is None or not document.pdf_path.is_file():
        return ""
    size = document.page_size_points(page)
    if size is None:
        return ""

    import pymupdf

    width_pt, height_pt = size
    x0, y0, x1, y1 = bbox
    clip = pymupdf.Rect(
        max(0.0, x0 - margin) * width_pt,
        max(0.0, y0 - margin) * height_pt,
        min(1.0, x1 + margin) * width_pt,
        min(1.0, y1 + margin) * height_pt,
    )
    if clip.is_empty:
        return ""

    width_inches = max(clip.width, 1.0) / 72.0
    dpi = int(min(_MAX_DPI, max(_MIN_DPI, _MAX_RENDER_PX / width_inches)))

    pdf = _open_pdf(document)
    try:
        pixmap = pdf[page - 1].get_pixmap(dpi=dpi, clip=clip)
        return base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    finally:
        pdf.close()


def render_page_with_box(
    document: Document, page: int, bbox: Sequence[float], target_width: int = 760
) -> str:
    """Página inteira com a bbox desenhada, para conferir **posição**.

    O recorte ampliado mostra o que está dentro da caixa; esta vista mostra se a
    caixa está no lugar certo da página — coisa que um recorte sozinho esconde.
    """
    if document.pdf_path is None or not document.pdf_path.is_file():
        return ""
    size = document.page_size_points(page)
    if size is None:
        return ""

    import pymupdf

    width_pt, height_pt = size
    rect = pymupdf.Rect(
        bbox[0] * width_pt, bbox[1] * height_pt, bbox[2] * width_pt, bbox[3] * height_pt
    )
    dpi = int(min(160, max(50, target_width / max(width_pt / 72.0, 0.1))))

    pdf = _open_pdf(document)
    try:
        target = pdf[page - 1]
        target.draw_rect(rect, color=(0.85, 0.1, 0.1), width=1.4)
        pixmap = target.get_pixmap(dpi=dpi)
        return base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    finally:
        pdf.close()


def ocr_text_in_box(document: Document, page: int, bbox: Sequence[float]) -> str:
    """Texto que o OCR coloca dentro da caixa declarada."""
    loaded = document.load_page(page)
    if loaded is None:
        return ""
    x0, y0, x1, y1 = bbox
    size = document.page_size_px(page)
    if size is None:
        return ""
    w_px, h_px = size
    picked = []
    for line in loaded.lines:
        cx = (line.x_min + line.x_max) / 2 / w_px
        cy = (line.y_min + line.y_max) / 2 / h_px
        if x0 - 0.01 <= cx <= x1 + 0.01 and y0 - 0.01 <= cy <= y1 + 0.01:
            picked.append(line.text)
    return " ".join(picked)


class _Corpus:
    """Índice do acervo, com busca fora da pasta do sujeito quando preciso.

    O BRIEF avisa que algumas dessas relações *"do not appear in the company's own
    documents"*. Um ato da controladora pode ser a única prova de uma saída na cap
    table da Archean; um relatório que só olhasse a pasta da Archean deixaria esses
    eventos sem cartão — e o leitor concluiria que a citação não tem prova, quando
    a prova existe, só está em outra pasta.

    A segunda varredura é preguiçosa de propósito: só custa quando algum documento
    realmente está fora.
    """

    def __init__(self, siren: str, kind: str) -> None:
        self.siren = siren
        self.kind = kind
        self.primary = {
            document.doc_id: document for document in list_documents(siren, kind)
        }
        self._elsewhere: dict[str, Document] | None = None

    def get(self, doc_id: str) -> Document | None:
        document = self.primary.get(doc_id)
        if document is not None:
            return document
        if self._elsewhere is None:
            self._elsewhere = {
                document.doc_id: document
                for other in list_sirens()
                if other != self.siren
                for document in list_documents(other, self.kind)
            }
        return self._elsewhere.get(doc_id)


def _survey(
    payload: dict[str, Any], kind: str = "actes"
) -> tuple[list[Evidence], list[tuple[str, str]]]:
    """Coleta a evidência de cada evento e registra o que não pôde ser mostrado.

    Evento sem cartão é lacuna do relatório, e lacuna silenciosa é pior que lacuna
    declarada: quem confere precisa saber que faltou, senão lê uma soma menor como
    se fosse o total.
    """
    siren = str(payload.get("siren") or "")
    corpus = _Corpus(siren, kind)

    items: list[Evidence] = []
    missing: list[tuple[str, str]] = []
    for event in payload.get("events") or []:
        event_id = str(event.get("event_id") or "?")
        source = event.get("source") or {}
        doc_id = str(source.get("inpi_id") or "")
        page = source.get("page")
        bbox = source.get("bbox") or []

        document = corpus.get(doc_id)
        if document is None:
            missing.append((event_id, f"documento {doc_id or '?'} ausente do acervo"))
            continue
        if not isinstance(page, int) or len(bbox) != 4:
            missing.append((event_id, "citação sem página ou bbox declarada"))
            continue

        snippet = str(source.get("snippet") or "")
        match = grounding.ground_document(document, snippet, page=page, min_score=0.0)
        items.append(
            Evidence(
                event_id=event_id,
                event_code=str(event.get("event_code") or "?"),
                event_date=str(event.get("event_date") or "?"),
                payload=event.get("payload") or {},
                doc_id=doc_id,
                page=page,
                bbox=[float(value) for value in bbox],
                snippet=snippet,
                matched_text=match.matched_text if match else "",
                score=match.score if match else 0.0,
                png_base64=render_crop(document, page, bbox),
                png_page=render_page_with_box(document, page, bbox),
                ocr_in_box=ocr_text_in_box(document, page, bbox),
            )
        )
    return items, missing


def collect_evidence(payload: dict[str, Any], kind: str = "actes") -> list[Evidence]:
    """Monta a evidência visual de cada evento do arquivo."""
    return _survey(payload, kind=kind)[0]


_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 32px; font: 14px/1.55 -apple-system, "Segoe UI", Roboto, sans-serif;
       background: #f6f7f9; color: #14161a; }
h1 { font-size: 22px; margin: 0 0 4px; }
h2 { font-size: 16px; margin: 36px 0 12px; }
.sub { color: #5b6472; margin-bottom: 24px; }
.summary { display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 28px; }
.stat { background: #fff; border: 1px solid #e2e5ea; border-radius: 10px; padding: 12px 18px; }
.stat b { display: block; font-size: 22px; }
.stat span { color: #5b6472; font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }
.card { background: #fff; border: 1px solid #e2e5ea; border-radius: 12px; margin-bottom: 22px; overflow: hidden; }
.card > header { padding: 12px 18px; border-bottom: 1px solid #eef0f3; display: flex;
                 align-items: center; gap: 12px; flex-wrap: wrap; }
.card > header .id { font-weight: 600; font-family: ui-monospace, Consolas, monospace; font-size: 13px; }
.badge { font-size: 11px; padding: 3px 9px; border-radius: 999px; font-weight: 600;
         text-transform: uppercase; letter-spacing: .04em; }
.ok { background: #e7f6ec; color: #14683a; }
.warn { background: #fff4e0; color: #8a5300; }
.grid { display: grid; grid-template-columns: minmax(360px, 1.25fr) 1fr; gap: 0; }
@media (max-width: 1100px) { .grid { grid-template-columns: 1fr; } }
figure { margin: 0; padding: 18px; background: #fbfbfc; border-right: 1px solid #eef0f3; }
figure img { width: 100%; border: 1px solid #d8dce2; border-radius: 6px; display: block; }
figure figcaption { margin-top: 10px; color: #5b6472; font-size: 12px; }
.pageview { width: auto; max-width: 100%; max-height: 380px; margin-top: 4px;
            border: 1px solid #d8dce2; border-radius: 6px; }
.claim { padding: 18px; }
table { border-collapse: collapse; width: 100%; margin-bottom: 14px; }
td { padding: 5px 0; vertical-align: top; }
td:first-child { color: #5b6472; width: 118px; }
code { font-family: ui-monospace, Consolas, monospace; font-size: 12.5px;
       background: #f2f4f7; padding: 1px 5px; border-radius: 4px; }
.quote { border-left: 3px solid #c9cfd8; padding: 6px 0 6px 12px; margin: 0 0 14px;
         color: #2b313a; font-style: italic; }
.label { font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
         color: #6b7280; margin: 14px 0 5px; font-weight: 600; }
.ocrbox { background: #fff8e6; border: 1px solid #f0e2bd; border-radius: 6px;
          padding: 9px 11px; font-family: ui-monospace, Consolas, monospace; font-size: 12px;
          white-space: pre-wrap; word-break: break-word; }
.notes { background: #fff; border: 1px solid #e2e5ea; border-radius: 12px; padding: 18px 22px; }
.notes p { margin: 0 0 10px; }
footer { margin-top: 36px; color: #6b7280; font-size: 12px; }
"""


def _badge(evidence: Evidence) -> str:
    if evidence.reproducible:
        return '<span class="badge ok">citação exata</span>'
    return '<span class="badge warn">conferir a olho</span>'


def _card(evidence: Evidence) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(str(key))}</td><td><code>{html.escape(json.dumps(value, ensure_ascii=False))}</code></td></tr>"
        for key, value in evidence.payload.items()
    )
    image = (
        f'<img alt="recorte da página {evidence.page}" src="data:image/png;base64,{evidence.png_base64}">'
        if evidence.png_base64
     
        else "<p><em>PDF indisponível para renderizar.</em></p>"
    )
    page_view = (
        '<div class="label">Página inteira, com a caixa em vermelho</div>'
        f'<img class="pageview" alt="página {evidence.page} com a caixa" '
        f'src="data:image/png;base64,{evidence.png_page}">'
        if evidence.png_page
        else ""
    )
    return f"""
    <article class="card">
      <header>
        <span class="id">{html.escape(evidence.event_id)}</span>
        {_badge(evidence)}
        <span class="badge ok" style="background:#eef1f5;color:#414a57">{html.escape(evidence.event_code)}</span>
        <span class="badge ok" style="background:#eef1f5;color:#414a57">{html.escape(evidence.event_date)}</span>
      </header>
      <div class="grid">
        <figure>
          {image}
          <figcaption>doc <code>{html.escape(evidence.doc_id)}</code> · página {evidence.page} ·
          bbox <code>[{", ".join(f"{v:.4f}" for v in evidence.bbox)}]</code></figcaption>
          {page_view}
        </figure>
        <div class="claim">
          <div class="label">Alegação</div>
          <table>{rows}</table>
          <div class="label">Citação declarada</div>
          <p class="quote">{html.escape(evidence.snippet)}</p>
          <div class="label">Texto que o OCR põe dentro da caixa</div>
          <div class="ocrbox">{html.escape(evidence.ocr_in_box) or "(nada)"}</div>
          <div class="label">Similaridade citação ↔ OCR</div>
          <div>{evidence.score:.4f}</div>
        </div>
      </div>
    </article>
    """


def build_report(payload: dict[str, Any], destination: Path, kind: str = "actes") -> Path:
    """Gera o HTML autocontido de verificação visual."""
    items, missing = _survey(payload, kind=kind)
    exact = sum(1 for item in items if item.reproducible)
    siren = html.escape(str(payload.get("siren") or ""))
    notes = str(payload.get("notes") or "")
    eventos = len(items) + len(missing)

    cards = "\n".join(_card(item) for item in items)
    notes_block = (
        f'<h2>Notas declaradas no arquivo</h2><div class="notes"><p>{html.escape(notes)}</p></div>'
        if notes
        else ""
    )
    missing_block = ""
    if missing:
        rows = "\n".join(
            f"<li><code>{html.escape(event_id)}</code> — {html.escape(reason)}</li>"
            for event_id, reason in missing
        )
        missing_block = (
            f'<h2>Eventos sem cartão neste relatório ({len(missing)})</h2>'
            f'<div class="notes"><p>Estes eventos existem no arquivo mas não têm '
            f'evidência renderizada aqui. O motivo está declarado em cada linha.</p>'
            f"<ul>{rows}</ul></div>"
        )

    document = f"""<!doctype html>
<html lang="pt-BR">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Verificação visual — {siren}</title>
<style>{_CSS}</style>
<body>
  <h1>Verificação visual do grounding — SIREN {siren}</h1>
  <p class="sub">Cada cartão traz a página renderizada com a caixa declarada, a alegação do
  arquivo e o texto que o OCR coloca dentro da caixa. <strong>A imagem é a fonte de verdade</strong>;
  o OCR serve apenas para localizar.</p>

  <div class="summary">
    <div class="stat"><b>{len(items)}</b><span>de {eventos} eventos com cartão</span></div>
    <div class="stat"><b>{exact}</b><span>citação exata</span></div>
    <div class="stat"><b>{len(items) - exact}</b><span>conferir a olho</span></div>
  </div>

  {cards}
  {missing_block}
  {notes_block}

  <footer>Gerado em {datetime.now():%Y-%m-%d %H:%M} por <code>src/report_html.py</code>.
  Recortes derivados do PDF do acervo — não redistribuir.</footer>
</body>
</html>
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(document, encoding="utf-8")
    return destination
