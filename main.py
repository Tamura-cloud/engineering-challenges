#!/usr/bin/env python3
"""CLI do pipeline universal de reconstrução societária.

Exemplos::

    # Reconstrução da empresa sujeita do desafio
    python main.py --siren 480489707 --output results_archean.json

    # Qualquer outra empresa do acervo
    python main.py --siren 499979540 --output results_hadean.json

    # Benchmark: re-ancora os eventos do results.json de referência e mede a fidelidade
    python main.py --siren 480489707 --benchmark results.json

    # Utilitários que não tocam a API
    python main.py --siren 480489707 --triage
    python main.py --audit results.json
    python main.py --ground "Le capital social est fixé à la somme de trente sept mille"
    python main.py --list-sirens
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from src import (
    config,
    dossier,
    events_file,
    extractor_llm,
    grounding,
    ocr_audit,
    pipeline,
    report_html,
    report_timeline,
    validator,
)
from src.ocr_loader import list_documents, list_sirens, summarize
from src.prefilter import DEFAULT_MIN_SCORE, triage

EXIT_OK = 0
EXIT_FAILURE = 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Pipeline universal de reconstrução societária a partir do OCR do acervo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--siren", help="SIREN de 9 dígitos a processar")
    parser.add_argument(
        "--output",
        help="arquivo de saída (padrão: results_<siren>.json). Nunca sobrescreve results.json.",
    )
    parser.add_argument("--kind", default="actes", choices=("actes", "bilans"))
    parser.add_argument(
        "--benchmark",
        metavar="REFERENCIA",
        help="re-ancora os eventos de um results.json de referência e reporta divergências",
    )
    parser.add_argument(
        "--audit",
        metavar="ARQUIVO",
        help="audita um results.json existente: invariantes algébricos + schema",
    )
    parser.add_argument("--triage", action="store_true", help="mostra a triagem de páginas e não chama a API")
    parser.add_argument(
        "--events",
        metavar="ARQUIVO",
        help="arquivo de eventos (JSON) de uma empresa; gera o results_<siren>.json",
    )
    parser.add_argument(
        "--report-html",
        metavar="RESULTS",
        help="gera o HTML de verificação visual (imagem + caixa + alegação) de um results.json",
    )
    parser.add_argument(
        "--timeline-html",
        metavar="RESULTS",
        help="gera o HTML da linha do tempo (composição do capital estado a estado) de um results.json",
    )
    parser.add_argument(
        "--sem-imagens",
        action="store_true",
        help="na linha do tempo, não embutir os recortes das páginas (arquivo bem menor)",
    )
    parser.add_argument(
        "--margem",
        type=float,
        default=None,
        metavar="FRAÇÃO",
        help="margem do recorte em volta da caixa, em fração da página (padrão 0.03)",
    )
    parser.add_argument(
        "--extract",
        action="store_true",
        help="lê o OCR de --siren pela API, propõe os eventos e gera o results_<siren>.json",
    )
    parser.add_argument(
        "--ocr-errors",
        action="store_true",
        help="aponta tokens numéricos suspeitos no OCR fornecido (não chama a API)",
    )
    parser.add_argument("--ground", metavar="SNIPPET", help="localiza um trecho no OCR e imprime a bbox")
    parser.add_argument("--doc", help="restringe a busca a um inpi_id")
    parser.add_argument("--page", type=int, help="restringe a busca a uma página")
    parser.add_argument(
        "--min-page-score",
        type=int,
        default=DEFAULT_MIN_SCORE,
        help=f"score mínimo do pré-filtro (padrão: {DEFAULT_MIN_SCORE})",
    )
    parser.add_argument(
        "--ground-min-score",
        type=float,
        default=0.60,
        help="similaridade mínima para aceitar um grounding",
    )
    parser.add_argument("--offline", action="store_true", help="não chama a API da DeepSeek")
    parser.add_argument("--model", help=f"modelo da DeepSeek (padrão: {config.DEEPSEEK_MODEL})")
    parser.add_argument("--list-sirens", action="store_true", help="lista as SIRENs do acervo")
    return parser


def _cmd_list_sirens() -> int:
    sirens = list_sirens()
    print(f"{len(sirens)} SIRENs no acervo:\n")
    for siren in sirens:
        info = summarize(siren)
        actes = info["kinds"]["actes"]
        print(
            f"  {siren}  actes={actes['documents']:>2} com_ocr={actes['with_ocr']:>2} "
            f"paginas={actes['pages']:>4}"
        )
    return EXIT_OK


def _cmd_audit(path: Path) -> int:
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    ok, checks, errors = validator.audit(payload)
    print(validator.format_checks(checks))
    if errors:
        print("\nErros de schema:")
        for error in errors:
            print(f"  - {error}")
    print(
        f"\nAuditoria de {path.name}: {'APROVADO' if ok else 'REPROVADO'} "
        f"({sum(1 for c in checks if c.passed)}/{len(checks)} invariantes, "
        f"{len(errors)} erros de schema)"
    )
    return EXIT_OK if ok else EXIT_FAILURE


def _cmd_ground(snippet: str, siren: str, doc: str | None, page: int | None) -> int:
    match = grounding.ground_siren(siren, snippet, doc_id=doc, page=page)
    if match is None:
        print("Snippet não localizado no OCR do acervo dessa SIREN.")
        return EXIT_FAILURE
    print(f"Documento ... {match.doc_id}")
    print(f"Página ...... {match.page}")
    print(f"bbox ........ {[round(value, 4) for value in match.bbox]}")
    print(f"Similaridade  {match.score:.4f}  ({len(match.line_indices)} linha(s))")
    print(f"Texto casado  {match.matched_text}")
    return EXIT_OK


def _cmd_triage(siren: str, kind: str, min_score: int) -> int:
    rows = triage(siren, kind=kind, min_score=min_score)
    print(f"Triagem de {siren} / {kind} (score mínimo = {min_score})\n")
    print(f"{'inpi_id':<26} {'depósito':<11} {'págs':>5} {'sel':>4}  assunto")
    print("-" * 100)
    for row in rows:
        pages = row.get("pages_total") if row["has_ocr"] else 0
        selected = row.get("pages_selected") if row["has_ocr"] else 0
        note = "" if row["has_ocr"] else "  [SEM OCR]"
        print(
            f"{str(row['doc_id']):<26} {str(row['deposit_date']):<11} "
            f"{pages:>5} {selected:>4}  {str(row['decision'] or '')[:40]}{note}"
        )
    return EXIT_OK


def _cmd_extract(
    siren: str,
    output: str | None,
    kind: str,
    min_page_score: int,
    model: str | None,
    min_score: float,
) -> int:
    """OCR -> API -> eventos candidatos -> results_<siren>.json.

    O modelo propõe as alegações; o grounding, o ledger, os invariantes e o
    schema fazem o resto. Nada que o modelo devolva entra sem passar por lá —
    e a proposta crua fica congelada em disco para ser auditada depois.
    """
    import json

    if not config.has_api_key():
        print(
            "ERRO: DEEPSEEK_API_KEY não definida.\n"
            f"Crie {config.REPO_ROOT / '.env'} e preencha DEEPSEEK_API_KEY=<chave>.",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    documents = [doc for doc in list_documents(siren, kind) if doc.has_ocr]
    if not documents:
        print(f"nenhum documento com OCR para a SIREN {siren}", file=sys.stderr)
        return EXIT_FAILURE

    page_map = pipeline.build_page_map(documents, min_page_score)
    total_pages = sum(len(pages) for pages in page_map.values())
    print(f"{len(documents)} documentos com OCR, {total_pages} páginas enviadas à API")

    extracted, notes = extractor_llm.extract_events(
        documents, page_map=page_map, model=model or config.DEEPSEEK_MODEL
    )
    print(f"o modelo propôs {len(extracted)} eventos")
    for note in notes:
        print(f"  aviso: {note}")

    spec = events_file.from_extracted(siren, extracted, kind=kind)
    candidate = config.REPO_ROOT / "events" / f"events_{siren}_candidate.json"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text(
        json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"proposta congelada em: {candidate}")

    outcome = dossier.build_from_spec(spec, min_score=min_score)
    print()
    print(events_file.render_report(outcome.anchored))
    print()
    print(dossier.render(outcome))

    if not outcome.anchored.events:
        print("\nnenhum evento ancorado — nada a escrever.", file=sys.stderr)
        return EXIT_FAILURE

    destination = Path(output) if output else config.REPO_ROOT / f"results_{siren}.json"
    if destination.resolve() == config.RESULTS_PATH.resolve():
        print("\nRECUSADO: o destino é o artefato de entrega.", file=sys.stderr)
        return EXIT_FAILURE

    written = dossier.write(outcome.payload, destination)
    print(f"\nArquivo escrito em: {written}")
    return EXIT_OK


def _cmd_report(results_path: Path, output: str | None) -> int:
    """Gera o HTML de verificação visual a partir de um results.json."""
    import json

    if not results_path.is_file():
        print(f"arquivo não encontrado: {results_path}", file=sys.stderr)
        return EXIT_FAILURE

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    siren = str(payload.get("siren") or "desconhecido")
    destination = (
        Path(output) if output else config.REPO_ROOT / "reports" / f"verificacao_{siren}.html"
    )
    written = report_html.build_report(payload, destination)
    print(f"{len(payload.get('events') or [])} alegações renderizadas")
    print(f"HTML escrito em: {written}")
    return EXIT_OK


def _cmd_timeline(
    results_path: Path,
    output: str | None,
    margin: float | None,
    embed_images: bool,
) -> int:
    """Gera o HTML da linha do tempo a partir de um results.json."""
    import json

    if not results_path.is_file():
        print(f"arquivo não encontrado: {results_path}", file=sys.stderr)
        return EXIT_FAILURE

    payload = json.loads(results_path.read_text(encoding="utf-8"))
    siren = str(payload.get("siren") or "desconhecido")
    destination = (
        Path(output) if output else config.REPO_ROOT / "reports" / f"timeline_{siren}.html"
    )
    options: dict[str, object] = {"embed_images": embed_images}
    if margin is not None:
        options["margin"] = margin
    written = report_timeline.build_timeline(payload, destination, **options)
    states = len(payload.get("capital_timeline") or [])
    size_kb = written.stat().st_size / 1024.0
    print(f"{states} estados desenhados")
    print(f"HTML escrito em: {written} ({size_kb:,.0f} KB)".replace(",", " "))
    return EXIT_OK


def _cmd_events(events_path: Path, output: str | None, min_score: float) -> int:
    """Gera o results_<siren>.json a partir de um arquivo de eventos.

    Este é o caminho genérico: o arquivo de eventos carrega apenas as alegações
    e as citações; a bbox, a timeline e os totais são todos calculados aqui.
    """
    if not events_path.is_file():
        print(f"arquivo de eventos não encontrado: {events_path}", file=sys.stderr)
        return EXIT_FAILURE

    outcome = dossier.build(events_path, min_score=min_score)
    print(events_file.render_report(outcome.anchored))
    print()
    print(dossier.render(outcome))

    if not outcome.anchored.events:
        print("\nnenhum evento ancorado — nada a escrever.", file=sys.stderr)
        return EXIT_FAILURE

    destination = (
        Path(output) if output else config.REPO_ROOT / f"results_{outcome.anchored.siren}.json"
    )
    if destination.resolve() == config.RESULTS_PATH.resolve():
        print(
            "\nRECUSADO: o destino é o results.json da raiz, que é o artefato de entrega.\n"
            "Use --output com outro nome.",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    written = dossier.write(outcome.payload, destination)
    print(f"\nArquivo escrito em: {written}")
    return EXIT_OK


def _cmd_ocr_errors(siren: str, kind: str, reference: str | None) -> int:
    """Aponta erros do OCR. Com ``--benchmark``, restringe às páginas citadas."""
    import json

    findings = ocr_audit.scan_siren(siren, kind=kind)
    if reference:
        payload = json.loads(Path(reference).read_text(encoding="utf-8"))
        material = ocr_audit.material_findings(findings, payload)
        print(
            f"De {len(findings)} achados no acervo, {len(material)} caem em páginas "
            f"citadas por {Path(reference).name}:\n"
        )
        print(ocr_audit.render(material))
        return EXIT_OK
    print(ocr_audit.render(findings, limit=60))
    return EXIT_OK


def _cmd_benchmark(reference: Path, kind: str) -> int:
    if not reference.is_file():
        print(f"arquivo de referência não encontrado: {reference}")
        return EXIT_FAILURE
    rows, summary = pipeline.benchmark(reference, kind=kind)
    print(pipeline.render_benchmark(rows, summary))
    return EXIT_OK


def _cmd_run(args: argparse.Namespace) -> int:
    options = pipeline.PipelineOptions(
        siren=args.siren,
        kind=args.kind,
        min_page_score=args.min_page_score,
        offline=args.offline,
        ground_min_score=args.ground_min_score,
        model=args.model,
    )

    if args.offline is False and not config.has_api_key():
        print(
            "ERRO: DEEPSEEK_API_KEY não definida.\n"
            f"Crie {config.REPO_ROOT / '.env'} a partir de .env.example, ou rode com --offline.",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    report = pipeline.run(options)
    print(report.render())

    if report.payload is None:
        return EXIT_OK

    destination = Path(args.output) if args.output else config.REPO_ROOT / f"results_{args.siren}.json"
    if destination.resolve() == config.RESULTS_PATH.resolve():
        print(
            "\nRECUSADO: o destino é o results.json da raiz, que é o artefato de entrega.\n"
            "Use --output com outro nome para não sobrescrever o artefato de entrega.",
            file=sys.stderr,
        )
        return EXIT_FAILURE

    written = pipeline.write_payload(report.payload, destination)
    print(f"\nArquivo escrito em: {written}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_sirens:
        return _cmd_list_sirens()

    if args.audit:
        return _cmd_audit(Path(args.audit))

    if args.report_html:
        return _cmd_report(Path(args.report_html), args.output)

    if args.timeline_html:
        return _cmd_timeline(
            Path(args.timeline_html), args.output, args.margem, not args.sem_imagens
        )

    if args.extract:
        if not args.siren:
            parser.error("--extract exige --siren")
        return _cmd_extract(
            args.siren,
            args.output,
            args.kind,
            args.min_page_score,
            args.model,
            args.ground_min_score,
        )

    if args.events:
        return _cmd_events(Path(args.events), args.output, args.ground_min_score)

    if not args.siren:
        parser.error("--siren é obrigatório (ou use --list-sirens / --audit)")

    if args.ocr_errors:
        return _cmd_ocr_errors(args.siren, args.kind, args.benchmark)

    if args.benchmark:
        return _cmd_benchmark(Path(args.benchmark), args.kind)

    if args.triage:
        return _cmd_triage(args.siren, args.kind, args.min_page_score)

    if args.ground:
        return _cmd_ground(args.ground, args.siren, args.doc, args.page)

    return _cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
