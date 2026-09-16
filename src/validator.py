"""Juiz determinístico: invariantes algébricos e aderência ao schema oficial.

O modelo de linguagem pode alucinar ou errar aritmética elementar. Este módulo
é a autoridade final: nenhum estado de capital é aceito sem que a álgebra feche.

Invariantes auditados:

1. ``Capital Total = Σ(Ações × Valor Nominal)``
2. ``Σ Ações dos sócios = Total de ações``
3. ``Σ Percentuais = 100%``
4. ``Conservação de fluxo``: entre estados consecutivos, ``entradas - saídas``
   é exatamente a variação do total de ações.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import jsonschema

from .config import SCHEMA_PATH, SUBJECT_SIREN


@dataclass(frozen=True)
class Check:
    """Resultado de uma verificação algébrica pontual."""

    name: str
    scope: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        flag = "OK   " if self.passed else "FALHA"
        return f"[{flag}] {self.name} · {self.scope}: {self.detail}"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _shares_map(state: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for holder in state.get("holders") or []:
        name = str(holder.get("name") or "?")
        result[name] = result.get(name, 0.0) + (_number(holder.get("shares")) or 0.0)
    return result


# --------------------------------------------------------------------- checks
def check_capital_identity(state: dict[str, Any], tol: float = 1e-4) -> Check:
    """Invariante 1: capital == ações x valor nominal."""
    as_of = str(state.get("as_of"))
    capital = _number(state.get("capital_eur"))
    shares = _number(state.get("shares_total"))
    nominal = _number(state.get("nominal_eur"))
    if capital is None or shares is None or nominal is None:
        return Check(
            "Invariante 1 (Capital)",
            as_of,
            False,
            "campos ausentes — são necessários capital_eur, shares_total e nominal_eur",
        )
    expected = shares * nominal
    tolerance = max(tol, tol * abs(capital))
    ok = abs(capital - expected) <= tolerance
    detail = (
        f"{capital:,.2f} € {'==' if ok else '!='} {shares:,.0f} ações x {nominal:g} € "
        f"(esperado {expected:,.2f} €)"
    )
    return Check("Invariante 1 (Capital)", as_of, ok, detail)


def check_share_closure(state: dict[str, Any]) -> Check:
    """Invariante 2: a soma das ações dos sócios fecha com o total."""
    as_of = str(state.get("as_of"))
    shares = _number(state.get("shares_total"))
    if shares is None:
        return Check("Invariante 2 (Fechamento)", as_of, False, "shares_total ausente")
    holders = _shares_map(state)
    total = sum(holders.values())
    ok = abs(total - shares) <= 1e-6
    detail = f"soma das cotas ({total:,.0f}) {'==' if ok else '!='} total ({shares:,.0f})"
    return Check("Invariante 2 (Fechamento)", as_of, ok, detail)


def check_percentage_closure(state: dict[str, Any], tol: float = 0.1) -> Check:
    """Invariante 3: os percentuais de todos os sócios somam 100%."""
    as_of = str(state.get("as_of"))
    percentages = [
        value
        for holder in state.get("holders") or []
        if (value := _number(holder.get("pct"))) is not None
    ]
    if not percentages:
        return Check("Invariante 3 (Percentuais)", as_of, False, "nenhum percentual informado")
    total = sum(percentages)
    ok = abs(total - 100.0) <= tol
    detail = f"soma percentual = {total:.2f}% (esperado 100% ± {tol:g})"
    return Check("Invariante 3 (Percentuais)", as_of, ok, detail)


def check_flow_conservation(
    timeline: Sequence[dict[str, Any]], tol: float = 1e-6
) -> list[Check]:
    """Invariante 4: entre estados consecutivos, entradas - saídas == variação do total."""
    checks: list[Check] = []
    for previous, current in zip(timeline, timeline[1:]):
        scope = f"{previous.get('as_of')} -> {current.get('as_of')}"
        before = _shares_map(previous)
        after = _shares_map(current)
        names = set(before) | set(after)

        inflow = sum(max(0.0, after.get(n, 0.0) - before.get(n, 0.0)) for n in names)
        outflow = sum(max(0.0, before.get(n, 0.0) - after.get(n, 0.0)) for n in names)
        net_delta = inflow - outflow

        delta_total = (_number(current.get("shares_total")) or 0.0) - (
            _number(previous.get("shares_total")) or 0.0
        )
        ok = abs(net_delta - delta_total) <= tol
        detail = (
            f"entradas {inflow:,.0f} - saídas {outflow:,.0f} = {net_delta:,.0f} "
            f"{'==' if ok else '!='} variação do total ({delta_total:,.0f})"
        )
        checks.append(Check("Invariante 4 (Fluxo)", scope, ok, detail))
    return checks


def check_holder_continuity(
    timeline: Sequence[dict[str, Any]],
    events: Sequence[dict[str, Any]] | None = None,
) -> list[Check]:
    """Invariante 5: toda mudança de quadro societário tem evento que a explique.

    Um sócio que aparece num estado sem um evento de entrada (ou desaparece sem
    um de saída) é erro de modelagem — e nenhum dos invariantes algébricos
    detecta isso, porque a soma continua fechando.
    """
    if not events:
        return []

    codes = {
        str(event.get("event_id")): str(event.get("event_code")) for event in events
    }
    entry_codes = {"SHAREHOLDER_ENTRY", "SHAREHOLDER_SHARE_TRANSFER"}
    exit_codes = {"SHAREHOLDER_END", "SHAREHOLDER_SHARE_TRANSFER"}

    checks: list[Check] = []
    for previous, current in zip(timeline, timeline[1:]):
        before = set(_shares_map(previous))
        after = set(_shares_map(current))
        added = after - before
        removed = before - after
        if not added and not removed:
            continue

        caused = [
            codes.get(str(item), "") for item in (current.get("caused_by") or [])
        ]
        problems: list[str] = []
        if added and not (set(caused) & entry_codes):
            problems.append(f"entraram {sorted(added)} sem SHAREHOLDER_ENTRY/TRANSFER")
        if removed and not (set(caused) & exit_codes):
            problems.append(f"saíram {sorted(removed)} sem SHAREHOLDER_END/TRANSFER")

        scope = f"{previous.get('as_of')} -> {current.get('as_of')}"
        detail = "; ".join(problems) or (
            f"entradas {sorted(added) or '-'} / saídas {sorted(removed) or '-'} "
            f"explicadas por {[c for c in caused if c]}"
        )
        checks.append(Check("Invariante 5 (Continuidade)", scope, not problems, detail))
    return checks


def check_event_vs_deposit(
    payload: dict[str, Any], siren: str | None = None
) -> list[Check]:
    """Invariante 6: a data de efeito não pode ser posterior ao depósito do ato.

    Um ato só pode registrar decisão que já aconteceu. Se a data declarada for
    posterior ao depósito, ou a data está errada ou o documento é outro.
    """
    from .ocr_loader import list_documents  # import tardio, evita ciclo

    target = str(siren or payload.get("siren") or SUBJECT_SIREN)
    deposits = {document.doc_id: document.deposit_date for document in list_documents(target)}

    checks: list[Check] = []
    for event in payload.get("events") or []:
        source = event.get("source") or {}
        doc_id = str(source.get("inpi_id") or "")
        deposit = deposits.get(doc_id)
        event_date = str(event.get("event_date") or "")
        scope = str(event.get("event_id") or doc_id or "?")
        if not deposit or not event_date:
            checks.append(
                Check("Invariante 6 (Datas)", scope, False, "data de efeito ou depósito ausente")
            )
            continue
        ok = event_date <= deposit
        detail = f"efeito {event_date} {'<=' if ok else '>'} depósito {deposit} ({doc_id[:12]}…)"
        checks.append(Check("Invariante 6 (Datas)", scope, ok, detail))
    return checks


def check_state_vs_events(
    timeline: Sequence[dict[str, Any]],
    events: Sequence[dict[str, Any]],
) -> list[Check]:
    """Cobra a frase do BRIEF: "the state of the cap table after each of those
    events". O estado tem de ser *posterior* às suas causas, as causas têm de
    existir, e todo evento tem de desembocar num estado.

    É o único invariante que liga os dois artefatos; os outros conferem a
    aritmética de cada um isoladamente. Por isso deixaram passar um estado
    datado de 2005-05-17 cujas causas eram todas de 2005-08-16 — cada artefato
    fechava sozinho, e nada comparava os dois.
    """
    checks: list[Check] = []
    by_id = {str(event.get("event_id")): event for event in events if event.get("event_id")}

    for state in timeline:
        as_of = str(state.get("as_of") or "?")
        causes = [str(cid) for cid in state.get("caused_by") or []]
        problems: list[str] = []
        for cause in causes:
            event = by_id.get(cause)
            if event is None:
                problems.append(f"{cause} não existe em events[]")
                continue
            date = str(event.get("event_date") or "")
            if date and date > as_of:
                problems.append(f"{cause} é de {date}, posterior ao estado")
        detail = (
            "; ".join(problems)
            if problems
            else f"{len(causes)} causa(s) existem e antecedem o estado"
        )
        checks.append(Check("Invariante 7 (Estado←Eventos)", as_of, not problems, detail))

    # Cobertura: todo evento precisa de um estado com a sua data de efeito.
    state_dates = {str(state.get("as_of")) for state in timeline}
    event_dates = {str(event.get("event_date")) for event in events if event.get("event_date")}
    orphan_dates = sorted(event_dates - state_dates)
    detail = (
        f"datas de efeito sem estado: {orphan_dates}"
        if orphan_dates
        else f"{len(event_dates)} datas de efeito, todas com estado"
    )
    checks.append(
        Check("Invariante 7 (Estado←Eventos)", "cobertura", not orphan_dates, detail)
    )

    return checks


def verify_algebraic_invariants(
    timeline: Sequence[dict[str, Any]],
) -> tuple[bool, list[Check]]:
    """Roda a auditoria completa sobre uma linha do tempo de capital."""
    checks: list[Check] = []
    for state in timeline:
        checks.append(check_capital_identity(state))
        checks.append(check_share_closure(state))
        checks.append(check_percentage_closure(state))
    checks.extend(check_flow_conservation(timeline))
    return all(check.passed for check in checks), checks


def format_checks(checks: Iterable[Check]) -> str:
    return "\n".join(str(check) for check in checks)


# -------------------------------------------------------------------- schema
def load_schema(path: Any = SCHEMA_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def schema_for_siren(siren: str, path: Any = SCHEMA_PATH) -> dict[str, Any]:
    """Carrega o schema relaxando a constante ``siren`` quando não é a sujeita.

    O schema oficial fixa ``"siren": {"const": "480489707"}``. Isso torna
    impossível validar qualquer outra empresa — por isso, para as demais SIRENs,
    a constante é substituída por um padrão de 9 dígitos. O resultado é marcado
    com ``x-relaxed-siren`` para deixar o relaxamento auditável.
    """
    schema = copy.deepcopy(load_schema(path))
    if siren != SUBJECT_SIREN:
        properties = schema.setdefault("properties", {})
        properties["siren"] = {
            "type": "string",
            "pattern": "^[0-9]{9}$",
            "description": "Relaxado em runtime: o schema oficial fixa 480489707.",
        }
        schema["x-relaxed-siren"] = siren
    return schema


def validate_schema(
    payload: dict[str, Any],
    siren: str = SUBJECT_SIREN,
    path: Any = SCHEMA_PATH,
) -> tuple[bool, list[str]]:
    """Valida o payload contra o schema, devolvendo todos os erros encontrados."""
    schema = schema_for_siren(siren, path)
    validator_class = jsonschema.validators.validator_for(schema)
    validator = validator_class(schema)
    errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
    messages = [
        f"{'/'.join(str(part) for part in error.path) or '<raiz>'}: {error.message}"
        for error in errors
    ]
    return not errors, messages


def audit(payload: dict[str, Any]) -> tuple[bool, list[Check], list[str]]:
    """Auditoria completa: invariantes + schema. Devolve ``(ok, checks, erros)``."""
    timeline = payload.get("capital_timeline") or []
    events = payload.get("events") or []

    _, checks = verify_algebraic_invariants(timeline)
    checks.extend(check_holder_continuity(timeline, events))
    checks.extend(check_event_vs_deposit(payload))
    checks.extend(check_state_vs_events(timeline, events))

    algebra_ok = all(check.passed for check in checks)
    schema_ok, errors = validate_schema(payload, siren=str(payload.get("siren") or SUBJECT_SIREN))
    return algebra_ok and schema_ok, checks, errors
