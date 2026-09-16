"""Ledger societário: calcula a linha do tempo a partir dos eventos.

A regra que justifica este módulo existir: **ninguém digita a timeline.**

Um erro real do projeto — a cap table de 2005 registrada com 803/637 quando o
documento diz 823/617 — só foi possível porque a timeline era um segundo texto
escrito à mão. O valor correto já estava numa citação do mesmo arquivo; os dois
nunca se falaram.

Aqui o fluxo é inverso: recebe-se apenas os **eventos** (cada um com sua
citação) e o ledger **deriva** capital, total de títulos e percentuais por
aritmética. Digitar um total passa a ser impossível.

Convenções de ``payload`` por código::

    CAPITAL_INCREASE      capital_after_eur, nominal_eur?, allocation?{nome: títulos}
    CAPITAL_DECREASE      capital_after_eur, cancelled_shares?
    SHAREHOLDER_ENTRY     holder_name, shares?
    SHAREHOLDER_END       holder_name
    SHAREHOLDER_SHARE_TRANSFER  from_name, to_name, shares
    CAPITAL_DUAL_CLASS    nominal_after_eur?, split_factor?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


class LedgerError(Exception):
    """Erro de consistência que impede a dobra do ledger."""


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


@dataclass
class _State:
    capital: float | None = None
    nominal: float | None = None
    holders: dict[str, float] = field(default_factory=dict)
    dirty: bool = False

    def total_shares(self) -> float | None:
        if self.holders:
            return sum(self.holders.values())
        if self.capital is not None and self.nominal:
            derived = self.capital / self.nominal
            return derived if abs(derived - round(derived)) < 1e-6 else derived
        return None


def _apply(state: _State, event: dict[str, Any]) -> None:
    code = str(event.get("event_code") or "")
    payload = event.get("payload") or {}

    if code == "CAPITAL_INCREASE":
        after = _number(payload.get("capital_after_eur"))
        if after is not None:
            state.capital = after
            state.dirty = True
        nominal = _number(payload.get("nominal_eur"))
        if nominal:
            state.nominal = nominal
            state.dirty = True
        allocation = payload.get("allocation")
        if isinstance(allocation, dict):
            for name, shares in allocation.items():
                value = _number(shares)
                if value is not None:
                    state.holders[str(name)] = value
            state.dirty = True

    elif code == "CAPITAL_DECREASE":
        after = _number(payload.get("capital_after_eur"))
        if after is not None:
            state.capital = after
            state.dirty = True
        cancelled = _number(payload.get("cancelled_shares"))
        if cancelled and state.holders:
            total = sum(state.holders.values())
            if total > 0:
                factor = max(0.0, (total - cancelled) / total)
                state.holders = {name: value * factor for name, value in state.holders.items()}
                state.dirty = True

    elif code == "SHAREHOLDER_ENTRY":
        name = str(payload.get("holder_name") or "").strip()
        shares = _number(payload.get("shares"))
        if name:
            state.holders[name] = state.holders.get(name, 0.0) + (shares or 0.0)
            state.dirty = True

    elif code == "SHAREHOLDER_END":
        name = str(payload.get("holder_name") or "").strip()
        if name and name in state.holders:
            del state.holders[name]
            state.dirty = True

    elif code == "SHAREHOLDER_SHARE_TRANSFER":
        source = str(payload.get("from_name") or "").strip()
        target = str(payload.get("to_name") or "").strip()
        shares = _number(payload.get("shares"))
        if source and target and shares:
            available = state.holders.get(source, 0.0)
            moved = min(shares, available) if available else shares
            state.holders[source] = max(0.0, available - moved)
            state.holders[target] = state.holders.get(target, 0.0) + moved
            state.dirty = True

    elif code == "CAPITAL_DUAL_CLASS":
        nominal = _number(payload.get("nominal_after_eur"))
        if nominal:
            state.nominal = nominal
        factor = _number(payload.get("split_factor"))
        if factor and factor > 1 and state.holders:
            state.holders = {name: value * factor for name, value in state.holders.items()}
            state.dirty = True
        state.dirty = state.dirty or bool(nominal or factor)


def _snapshot(state: _State, as_of: str, caused_by: Sequence[str]) -> dict[str, Any]:
    total = state.total_shares()
    rows: list[dict[str, Any]] = []
    for name in sorted(state.holders, key=lambda key: -state.holders[key]):
        shares = state.holders[name]
        pct = round(shares / total * 100.0, 2) if total else None
        rows.append(
            {
                "name": name,
                "siren": "499979540" if name.strip().upper().startswith("HADEAN") else None,
                "kind": "COMPANY" if name.strip().upper().startswith("HADEAN") else "UNKNOWN",
                "shares": shares if shares != int(shares) else int(shares),
                "pct": pct,
            }
        )
    if not rows and state.capital is not None:
        rows.append(
            {"name": "TITULAIRE NON DÉTERMINÉ", "siren": None, "kind": "UNKNOWN", "shares": total, "pct": 100.0 if total else None}
        )
    return {
        "as_of": as_of,
        "capital_eur": state.capital,
        "shares_total": total,
        "nominal_eur": state.nominal,
        "holders": rows,
        "caused_by": list(caused_by),
    }


def build_timeline(events: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dobra os eventos por data de efeito e devolve os estados de capital.

    Agrupa por ``event_date`` para que uma constituição (capital + entradas dos
    sócios no mesmo dia) produza **um** estado, e não três.
    """
    ordered = sorted(
        (event for event in events if event.get("event_date")),
        key=lambda event: (str(event["event_date"]), str(event.get("event_id") or "")),
    )

    state = _State()
    timeline: list[dict[str, Any]] = []
    current_date: str | None = None
    pending_ids: list[str] = []

    def flush() -> None:
        nonlocal pending_ids
        if state.dirty and current_date:
            timeline.append(_snapshot(state, current_date, pending_ids))
            state.dirty = False
        pending_ids = []

    for event in ordered:
        date = str(event["event_date"])
        if current_date is not None and date != current_date:
            flush()
        current_date = date
        pending_ids.append(str(event.get("event_id") or ""))
        _apply(state, event)

    flush()
    return timeline
