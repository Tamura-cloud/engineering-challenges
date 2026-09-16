"""Dossiê: de um arquivo de eventos a um ``results.json`` validado.

Este é o caminho genérico do projeto. Recebe **dados** (a leitura de quem
analisou os documentos) e devolve o artefato, executando sempre a mesma cadeia:

    arquivo de eventos
        -> ancoragem (bbox calculada a partir da citação)
        -> ledger (timeline calculada por aritmética)
        -> 6 invariantes algébricos
        -> validação contra o schema oficial
        -> results_<siren>.json

Nenhum total, capital ou percentual vem do arquivo de entrada. Nenhuma
coordenada vem do arquivo de entrada. É essa restrição que faz o mesmo código
servir para qualquer empresa do acervo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import events_file, ledger, ocr_audit, validator
from .config import SUBJECT_SIREN


@dataclass
class Dossier:
    """Resultado completo: o payload pronto e a auditoria que o sustenta."""

    payload: dict[str, Any]
    anchored: events_file.Anchored
    checks: list[validator.Check] = field(default_factory=list)
    schema_errors: list[str] = field(default_factory=list)
    ocr_findings: list[ocr_audit.OcrFinding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks) and not self.schema_errors


def build(spec_path: Path, min_score: float = 0.60, scan_ocr: bool = True) -> Dossier:
    """Monta o dossiê de uma empresa a partir do arquivo de eventos."""
    spec = events_file.load_events_file(spec_path)
    anchored = events_file.anchor(spec, min_score=min_score)

    timeline = ledger.build_timeline(anchored.events)

    notes: list[str] = []
    notes.extend(anchored.notes)
    if anchored.siren != SUBJECT_SIREN:
        notes.append(
            "O schema oficial fixa a SIREN 480489707 como constante; para esta empresa a "
            "validação é feita com essa restrição relaxada em runtime (marcada como "
            "'x-relaxed-siren' no schema)."
        )

    payload: dict[str, Any] = {
        "siren": anchored.siren,
        "events": anchored.events,
        "capital_timeline": timeline,
    }
    if anchored.denomination:
        payload["group"] = {
            "nodes": [{"name": anchored.denomination, "siren": anchored.siren, "resolved": True}],
            "edges": [],
        }

    _, checks = validator.verify_algebraic_invariants(timeline)
    checks.extend(validator.check_holder_continuity(timeline, anchored.events))
    checks.extend(validator.check_event_vs_deposit(payload))
    schema_ok, schema_errors = validator.validate_schema(payload, siren=anchored.siren)

    findings: list[ocr_audit.OcrFinding] = []
    if scan_ocr and anchored.events:
        all_findings = ocr_audit.scan_siren(anchored.siren, kind=anchored.kind)
        findings = ocr_audit.material_findings(all_findings, payload)
        if findings:
            notes.append(
                f"{len(findings)} erro(s) de transcrição do OCR nas páginas citadas "
                f"(todos com score alto — a confiança do motor não os detecta): "
                + "; ".join(f"{item.doc_id[-6:]} p.{item.page} {'|'.join(item.tokens)}" for item in findings)
            )

    failed = [check for check in checks if not check.passed]
    if failed:
        notes.append(
            "Verificações que NÃO passaram: "
            + "; ".join(f"{check.name} [{check.scope}]: {check.detail}" for check in failed)
        )
    if schema_errors:
        notes.append("Erros de schema: " + "; ".join(schema_errors))

    if notes:
        payload["notes"] = " | ".join(notes)

    return Dossier(
        payload=payload,
        anchored=anchored,
        checks=checks,
        schema_errors=schema_errors,
        ocr_findings=findings,
    )


def write(payload: dict[str, Any], destination: Path) -> Path:
    """Escreve o dossiê formatado."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return destination


def render(dossier: Dossier) -> str:
    """Resumo legível: invariantes, schema e contagens."""
    lines = [validator.format_checks(dossier.checks)]
    if dossier.schema_errors:
        lines.append("")
        lines.append("Erros de schema:")
        lines.extend(f"  - {error}" for error in dossier.schema_errors)
    passed = sum(1 for check in dossier.checks if check.passed)
    lines.append("")
    lines.append(
        f"eventos={len(dossier.payload['events'])}  "
        f"estados={len(dossier.payload['capital_timeline'])}  "
        f"invariantes={passed}/{len(dossier.checks)}  "
        f"erros_schema={len(dossier.schema_errors)}  "
        f"-> {'APROVADO' if dossier.ok else 'REPROVADO'}"
    )
    return "\n".join(lines)
