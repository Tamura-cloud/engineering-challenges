"""Linha do tempo do capital, em HTML autocontido.

Irmão de :mod:`src.report_html`, mas com outro propósito. Aquele serve para
*conferir a leitura*: mostra a página com o retângulo e a citação ao lado, para
o revisor ver que o trecho existe mesmo e está no lugar certo. Este serve para
*enxergar a evolução*: quem entra, quem sai, como as cotas se redistribuem e
qual evento causou cada estado.

Os estados não são digitados em lugar nenhum — vêm de :mod:`src.ledger`, que os
deriva aplicando os eventos em ordem. Se a barra de composição estiver errada,
o erro está nos eventos, não no desenho.

O HTML é autocontido: sem CDN, sem fonte externa, sem JavaScript. Um arquivo
só, que abre em qualquer navegador e pode ser versionado.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .ocr_loader import Document, list_documents
from .report_html import render_crop

# Margem do recorte, em fração da página, para além da bbox. Generosa de propósito:
# um recorte colado na caixa prova que o texto existe, mas não *onde* ele está. Com
# contexto em volta dá para ver se a frase é corpo do ato, cabeçalho ou carimbo —
# e é isso que separa "a frase está nesta página" de "a frase é o que eu digo".
DEFAULT_MARGIN = 0.03

# Cores distinguíveis também em impressão P&B, por ordem de contraste.
_PALETTE = (
    "#2f6feb", "#c2410c", "#15803d", "#7e22ce", "#b91c1c",
    "#0e7490", "#a16207", "#4b5563", "#be185d", "#3f6212",
    "#1d4ed8", "#9a3412",
)


# Ordem de entrada no capital -> índice de cor. Atribuir cor por hash dava
# colisão (dois titulares da mesma constituição saíam com a mesma cor, e a barra
# empilhada ficava ambígua). A ordem de entrada é estável entre estados e
# semanticamente melhor: pinta quem chegou primeiro com a primeira cor.
_ORDER: dict[str, int] = {}


def _register(name: str) -> None:
    if name and name not in _ORDER:
        _ORDER[name] = len(_ORDER)


def _colour(name: str) -> str:
    """Cor estável para um titular — o mesmo nome pinta sempre igual."""
    if not name:
        return "#94a3b8"
    return _PALETTE[_ORDER.get(name, len(_ORDER)) % len(_PALETTE)]


def _fmt_int(value: Any) -> str:
    """1234567 -> ``1 234 567`` (espaço fino, como nos atos franceses)."""
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return html.escape(str(value))
    if number != number:  # NaN
        return "—"
    if abs(number - round(number)) < 1e-9:
        return f"{int(round(number)):,}".replace(",", "\u202f")
    return f"{number:,.2f}".replace(",", "\u202f").replace(".", ",")


def _fmt_eur(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):,.2f} €".replace(",", "\u202f").replace(".", ",")
    except (TypeError, ValueError):
        return html.escape(str(value))


def _fmt_pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        text = f"{float(value):.2f}".rstrip("0").rstrip(".")
        return f"{text} %".replace(".", ",")
    except (TypeError, ValueError):
        return html.escape(str(value))


def _holders(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Titulares do estado, indexados por nome."""
    out: dict[str, dict[str, Any]] = {}
    for holder in state.get("holders") or []:
        name = str(holder.get("name") or "").strip()
        if name:
            out[name] = holder
    return out


def _payload_rows(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Achata o payload em pares rótulo/valor, para virar tabela."""
    rows: list[tuple[str, str]] = []
    for key, value in (payload or {}).items():
        if isinstance(value, dict):
            rendered = ", ".join(
                f"{_fmt_int(sub)} {name}" for name, sub in value.items()
            )
            rows.append((key, rendered))
        elif isinstance(value, float) and key.endswith("_eur"):
            rows.append((key, _fmt_eur(value)))
        else:
            rows.append((key, _fmt_int(value)))
    return rows


def _delta(previous: dict[str, Any] | None, current: dict[str, Any]) -> str:
    """O que mudou de um estado para o seguinte."""
    here = _holders(current)
    if previous is None:
        if not here:
            return ""
        chips = "".join(
            f'<span class="chip in">entra {html.escape(name)} '
            f"({_fmt_int(info.get('shares'))})</span>"
            for name, info in sorted(here.items())
        )
        return f'<div class="delta"><span class="lbl">quadro inicial</span>{chips}</div>'

    there = _holders(previous)
    chips: list[str] = []

    for name in sorted(set(here) - set(there)):
        chips.append(
            f'<span class="chip in">entra {html.escape(name)} '
            f"({_fmt_int(here[name].get('shares'))})</span>"
        )
    for name in sorted(set(there) - set(here)):
        chips.append(f'<span class="chip out">sai {html.escape(name)}</span>')

    for name in sorted(set(here) & set(there)):
        before = there[name].get("shares")
        after = here[name].get("shares")
        if before is None or after is None:
            continue
        try:
            moved = float(after) - float(before)
        except (TypeError, ValueError):
            continue
        if abs(moved) < 1e-9:
            continue
        sign = "+" if moved > 0 else "\u2212"
        cls = "up" if moved > 0 else "down"
        chips.append(
            f'<span class="chip {cls}">{html.escape(name)} {sign}{_fmt_int(abs(moved))} cotas</span>'
        )

    if not chips:
        return '<div class="delta"><span class="lbl">sem alteração no quadro de titulares</span></div>'
    return f'<div class="delta"><span class="lbl">Variação</span>{"".join(chips)}</div>'


def _composition(state: dict[str, Any]) -> str:
    """Barra empilhada com a composição percentual do capital."""
    holders = state.get("holders") or []
    with_pct = [h for h in holders if h.get("pct") is not None]
    if not with_pct:
        return '<p class="muted">composição não determinada neste estado.</p>'

    total = sum(float(h["pct"]) for h in with_pct)
    if total <= 0:
        return '<p class="muted">composição não determinada neste estado.</p>'

    segments: list[str] = []
    for holder in sorted(with_pct, key=lambda h: -float(h["pct"])):
        share = float(holder["pct"]) / total * 100.0
        name = str(holder.get("name") or "")
        label = f"{share:.1f} %".replace(".", ",") if share >= 7 else ""
        segments.append(
            f'<span style="width:{share:.4f}%;background:{_colour(name)}" '
            f'title="{html.escape(name)} — {_fmt_pct(holder.get("pct"))}">{label}</span>'
        )

    rows = "".join(
        f"<tr><td><i class='sw' style='background:{_colour(str(h.get('name') or ''))}'></i>"
        f"{html.escape(str(h.get('name') or ''))}</td>"
        f"<td class='num'>{_fmt_int(h.get('shares'))}</td>"
        f"<td class='num'>{_fmt_pct(h.get('pct'))}</td></tr>"
        for h in sorted(with_pct, key=lambda h: -float(h["pct"]))
    )
    return (
        f'<div class="bar">{"".join(segments)}</div>'
        f'<table class="legend"><thead><tr><th>titular</th><th class="num">cotas</th>'
        f'<th class="num">%</th></tr></thead><tbody>{rows}</tbody></table>'
    )


def _crop_figure(
    event: dict[str, Any],
    documents: Mapping[str, Document] | None,
    margin: float,
) -> str:
    """O recorte da página, ao lado da citação.

    Nunca levanta: PDF ausente, página inválida ou geometria estranha viram uma
    nota em vez de derrubar a geração. A página de texto tem de sair de qualquer jeito.
    """
    if not documents:
        return ""
    source = event.get("source") or {}
    document = documents.get(str(source.get("inpi_id") or ""))
    page = source.get("page")
    bbox = source.get("bbox")
    if document is None:
        return '<div class="noimg">documento ausente do acervo em disco</div>'
    if page is None or not bbox:
        return '<div class="noimg">sem página ou sem bbox: nada a recortar</div>'
    try:
        png = render_crop(document, int(page), bbox, margin=margin)
    except Exception as exc:  # noqa: BLE001 — degradar, nunca quebrar
        return f'<div class="noimg">recorte indisponível ({html.escape(type(exc).__name__)})</div>'
    if not png:
        return '<div class="noimg">PDF ausente em disco — recorte não gerado</div>'
    return (
        f'<figure class="crop">'
        f'<img alt="recorte da página {html.escape(str(page))}" '
        f'src="data:image/png;base64,{png}">'
        f"<figcaption>página {html.escape(str(page))} · "
        f"margem {margin:g} além da caixa</figcaption></figure>"
    )


def _event_block(
    event: dict[str, Any],
    documents: Mapping[str, Document] | None = None,
    margin: float = DEFAULT_MARGIN,
) -> str:
    payload = _payload_rows(event.get("payload") or {})
    rows = "".join(
        f"<tr><td>{html.escape(key)}</td><td><code>{html.escape(value)}</code></td></tr>"
        for key, value in payload
    )
    source = event.get("source") or {}
    snippet = str(source.get("snippet") or "").strip()
    where = " · ".join(
        part
        for part in (
            str(source.get("inpi_id") or ""),
            f"página {source.get('page')}" if source.get("page") else "",
            f"depósito {event.get('deposit_date')}" if event.get("deposit_date") else "",
        )
        if part
    )
    quote = (
        f'<blockquote class="quote">{html.escape(snippet)}</blockquote>' if snippet else ""
    )
    figure = _crop_figure(event, documents, margin)
    info = (
        f'<table class="payload">{rows}</table>{quote}'
        f'<div class="src">{html.escape(where)}</div>'
    )
    body = (
        f'<div class="evtbody">{figure}<div class="evtinfo">{info}</div></div>'
        if figure
        else info
    )
    return (
        f'<div class="evt">'
        f'<div class="evthead"><code>{html.escape(str(event.get("event_code") or ""))}</code>'
        f'<span class="eid">{html.escape(str(event.get("event_id") or ""))}</span></div>'
        f"{body}"
        f"</div>"
    )


def _state_block(
    state: dict[str, Any],
    previous: dict[str, Any] | None,
    events_by_id: dict[str, dict[str, Any]],
    documents: Mapping[str, Document] | None = None,
    margin: float = DEFAULT_MARGIN,
) -> str:
    date = str(state.get("as_of") or "—")
    capital = _fmt_eur(state.get("capital_eur"))
    shares = _fmt_int(state.get("shares_total"))
    nominal = _fmt_eur(state.get("nominal_eur"))

    caused = [
        events_by_id[eid]
        for eid in (state.get("caused_by") or [])
        if eid in events_by_id
    ]
    blocks = "".join(_event_block(event, documents, margin) for event in caused)
    details = (
        f'<details><summary>{len(caused)} evento(s) causaram este estado</summary>'
        f"{blocks}</details>"
        if caused
        else ""
    )

    return (
        f'<div class="state"><div class="when">{html.escape(date)}</div>'
        f'<div class="card">'
        f'<div class="metrics">'
        f'<div><span>capital</span><b>{capital}</b></div>'
        f'<div><span>cotas</span><b>{shares}</b></div>'
        f'<div><span>valor nominal</span><b>{nominal}</b></div>'
        f"</div>"
        f"{_composition(state)}"
        f"{_delta(previous, state)}"
        f"{details}"
        f"</div></div>"
    )


def _group_block(group: Any) -> str:
    """Seção do grafo societário, quando o payload traz um."""
    if not isinstance(group, dict):
        return ""
    nodes = group.get("nodes") or []
    edges = group.get("edges") or []
    if not nodes:
        return ""

    rows = "".join(
        f"<tr><td><code>{html.escape(str(edge.get('from') or ''))}</code></td>"
        f"<td>{html.escape(str(edge.get('relation') or edge.get('kind') or ''))}</td>"
        f"<td><code>{html.escape(str(edge.get('to') or ''))}</code></td>"
        f"<td class='num'>{_fmt_pct(edge.get('pct'))}</td></tr>"
        for edge in edges
    )
    return (
        "<h2>Estrutura do grupo</h2>"
        f'<div class="card pad"><p class="muted">{len(nodes)} nós, {len(edges)} arestas.</p>'
        f'<table class="legend"><thead><tr><th>de</th><th>relação</th><th>para</th>'
        f'<th class="num">%</th></tr></thead><tbody>{rows}</tbody></table></div>'
    )


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
.card { background: #fff; border: 1px solid #e2e5ea; border-radius: 12px; overflow: hidden; }
.card.pad { padding: 18px 22px; }
.tl { position: relative; margin-left: 8px; padding-left: 26px; border-left: 2px solid #e2e5ea; }
.state { position: relative; margin-bottom: 26px; }
.state::before { content: ""; position: absolute; left: -35px; top: 8px; width: 11px; height: 11px;
                 border-radius: 50%; background: #2f6feb; border: 2px solid #fff;
                 box-shadow: 0 0 0 2px #cfd6e4; }
.when { font: 600 13px/1 ui-monospace, Consolas, monospace; color: #2f6feb; margin-bottom: 8px; }
.metrics { display: flex; gap: 28px; padding: 14px 18px; border-bottom: 1px solid #eef0f3; flex-wrap: wrap; }
.metrics span { display: block; color: #5b6472; font-size: 11px; text-transform: uppercase;
                letter-spacing: .04em; }
.metrics b { font-size: 17px; }
.bar { display: flex; height: 28px; margin: 16px 18px 10px; border-radius: 7px;
       overflow: hidden; border: 1px solid #e2e5ea; }
.bar span { display: flex; align-items: center; justify-content: center; color: #fff;
            font-size: 11px; font-weight: 600; }
.legend { border-collapse: collapse; width: calc(100% - 36px); margin: 0 18px 6px; }
.legend th { text-align: left; font-size: 11px; text-transform: uppercase; color: #6b7280;
             letter-spacing: .04em; padding: 4px 6px; border-bottom: 1px solid #eef0f3; }
.legend td { padding: 5px 6px; border-bottom: 1px solid #f4f5f7; }
.legend .num, .legend th.num { text-align: right; font-variant-numeric: tabular-nums; }
.sw { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 7px; }
.delta { padding: 10px 18px 14px; display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
.delta .lbl { font-size: 11px; text-transform: uppercase; letter-spacing: .04em; color: #6b7280;
              font-weight: 600; margin-right: 4px; }
.chip { font-size: 12px; padding: 3px 9px; border-radius: 999px; background: #eef1f5; color: #333a45; }
.chip.in, .chip.up { background: #e7f6ec; color: #14683a; }
.chip.out, .chip.down { background: #fdeaea; color: #a41d1d; }
details { border-top: 1px solid #eef0f3; }
summary { cursor: pointer; padding: 11px 18px; font-size: 12.5px; color: #5b6472; font-weight: 600; }
summary:hover { background: #fbfbfc; }
.evt { padding: 12px 18px; border-top: 1px solid #f4f5f7; }
.evthead { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.evthead code { font-weight: 600; }
.eid { font: 11.5px ui-monospace, Consolas, monospace; color: #6b7280; }
.evtbody { display: grid; grid-template-columns: minmax(260px, 40%) 1fr; gap: 18px;
           align-items: start; }
@media (max-width: 900px) { .evtbody { grid-template-columns: 1fr; } }
.evtinfo { min-width: 0; }
.crop { margin: 0; }
.crop img { width: 100%; display: block; background: #fff; border: 1px solid #d8dce2;
            border-radius: 6px; }
.crop figcaption { margin-top: 6px; color: #6b7280; font: 11.5px ui-monospace, Consolas, monospace; }
.noimg { border: 1px dashed #d8dce2; border-radius: 6px; padding: 22px 12px; color: #6b7280;
         font-size: 12px; text-align: center; }
.notice { background: #fff8e6; border: 1px solid #f0e2bd; border-radius: 8px;
          padding: 11px 14px; font-size: 13px; margin: 0 0 22px; }
.payload { border-collapse: collapse; margin-bottom: 8px; }
.payload td { padding: 2px 0; vertical-align: top; }
.payload td:first-child { color: #5b6472; width: 170px; font-size: 12.5px; }
code { font-family: ui-monospace, Consolas, monospace; font-size: 12.5px;
       background: #f2f4f7; padding: 1px 5px; border-radius: 4px; }
.quote { border-left: 3px solid #c9cfd8; padding: 5px 0 5px 12px; margin: 6px 0 8px;
         color: #2b313a; font-style: italic; font-size: 13px; }
.src { font: 11.5px ui-monospace, Consolas, monospace; color: #6b7280; }
.muted { color: #6b7280; font-size: 13px; margin: 0; }
.notes { background: #fff; border: 1px solid #e2e5ea; border-radius: 12px; padding: 18px 22px;
         white-space: pre-wrap; font-size: 13px; }
footer { margin-top: 36px; color: #6b7280; font-size: 12px; }
"""


def _load_corpus(siren: str, kind: str) -> dict[str, Document]:
    """Carrega o acervo, se estiver em disco.

    `data/` não é versionado — 372 MB de documentos de terceiros que o próprio
    NOTICE.md pede para não redistribuir. Então quem clonar o repositório não tem
    PDF nenhum, e isso não é falha: é o caso esperado. A ausência só desliga as
    imagens.
    """
    if not siren:
        return {}
    try:
        return {doc.doc_id: doc for doc in list_documents(siren, kind)}
    except Exception:  # noqa: BLE001
        return {}


def build_timeline(
    payload: dict[str, Any],
    destination: Path,
    documents: Mapping[str, Document] | None = None,
    margin: float = DEFAULT_MARGIN,
    kind: str = "actes",
    embed_images: bool = True,
) -> Path:
    """Escreve o HTML da linha do tempo e devolve o caminho gravado.

    Com o acervo em disco, cada evento sai com o recorte da página ao lado da
    citação — a alegação e a prova visual na mesma tela. Sem o acervo, sai só o
    texto: a página continua válida, apenas não se prova sozinha.
    """
    states = payload.get("capital_timeline") or []
    siren_raw = str(payload.get("siren") or "")
    if not embed_images:
        documents = {}
    elif documents is None:
        documents = _load_corpus(siren_raw, kind)
    events = payload.get("events") or []
    events_by_id = {
        str(event.get("event_id")): event
        for event in events
        if event.get("event_id")
    }

    # Registra os titulares pela ordem de primeira aparição, antes de desenhar:
    # a cor de um nome precisa ser a mesma em todos os estados.
    _ORDER.clear()
    for state in states:
        for holder in state.get("holders") or []:
            _register(str(holder.get("name") or ""))

    dates = [str(s.get("as_of")) for s in states if s.get("as_of")]
    blocks: list[str] = []
    previous: dict[str, Any] | None = None
    for state in states:
        blocks.append(_state_block(state, previous, events_by_id, documents, margin))
        previous = state

    siren = html.escape(siren_raw or "—")
    span = f"{dates[0]} → {dates[-1]}" if dates else "—"

    images_note = ""
    if not documents:
        reason = (
            "os recortes foram desligados a pedido"
            if not embed_images
            else f"o acervo <code>data/{html.escape(siren_raw or '<siren>')}"
            f"/{html.escape(kind)}/</code> não está em disco"
        )
        images_note = (
            f'<p class="notice">Página gerada <b>sem recortes</b>: {reason}. '
            "O corpus não é versionado, então fora da máquina onde os PDFs estão "
            "as imagens não existem — o texto abaixo permanece integral e conferível "
            "contra os documentos, só não se mostra sozinho.</p>"
        )

    notes = str(payload.get("notes") or "").strip()
    notes_block = (
        f"<h2>Notas, lacunas e correções</h2><div class='notes'>{html.escape(notes)}</div>"
        if notes
        else ""
    )

    body = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<title>Linha do tempo do capital — {siren}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>Linha do tempo do capital</h1>
<div class="sub">SIREN <code>{siren}</code> · {span}</div>
{images_note}

<div class="summary">
  <div class="stat"><b>{len(states)}</b><span>estados</span></div>
  <div class="stat"><b>{len(events)}</b><span>eventos</span></div>
  <div class="stat"><b>{len({e.get('event_code') for e in events})}</b><span>tipos de evento</span></div>
  <div class="stat"><b>{len({h.get('name') for s in states for h in (s.get('holders') or [])})}</b><span>titulares</span></div>
</div>

<h2>Composição do capital ao longo do tempo</h2>
<div class="tl">
{''.join(blocks)}
</div>

{_group_block(payload.get('group'))}

{notes_block}

<footer>
  Os estados são lidos do campo <code>capital_timeline</code> do arquivo — este relatório
  não recalcula nada. Como cada arquivo foi produzido está declarado no README: o
  entregável da Archean tem os estados montados à mão e conferidos pelos invariantes
  algébricos; empresas processadas pelo pipeline têm os estados derivados dos eventos
  por <code>src/ledger.py</code>. Cada recorte é a própria página do ato, ampliada em
  volta da citação: é a prova visual da alegação, não uma ilustração. Quando o texto do
  OCR diverge da imagem, a imagem manda.
</footer>
</body>
</html>
"""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(body, encoding="utf-8")
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Gera o HTML da linha do tempo.")
    parser.add_argument("results", help="results.json a visualizar")
    parser.add_argument("--output", "-o", default=None, help="HTML de saída")
    parser.add_argument(
        "--sem-imagens",
        action="store_true",
        help="não embutir recortes das páginas (arquivo muito menor)",
    )
    parser.add_argument(
        "--margem",
        type=float,
        default=DEFAULT_MARGIN,
        help=f"margem do recorte, em fração da página (padrão {DEFAULT_MARGIN})",
    )
    args = parser.parse_args(argv)

    source = Path(args.results)
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination = Path(args.output) if args.output else source.with_suffix(".timeline.html")
    written = build_timeline(
        payload, destination, margin=args.margem, embed_images=not args.sem_imagens
    )
    size_kb = written.stat().st_size / 1024.0
    print(f"linha do tempo escrita em: {written} ({size_kb:,.0f} KB)".replace(",", " "))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
