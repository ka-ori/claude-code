"""Structural similarity between alphas: an early warning for self-correlation.

BRAIN's self-correlation is computed from daily PnL, which only the platform has.
This module compares what the expressions are built from (fields, operators,
horizons, normalizer, grouping, gating, neutralization) to flag a likely
correlation problem *before* spending a simulation. It is a heuristic, not a
substitute for BRAIN's check.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .catalog import default_catalog
from .fastexpr.parser import call_name
from .fastexpr.validator import NORMALIZERS, Validator
from .journal import Entry

ARITHMETIC = {"add", "sub", "mult", "div", "compare", "and", "or"}
GATES = {"trade_when", "if_else"}
WEIGHTS = {"fields": 0.40, "operators": 0.20, "horizons": 0.15, "normalizer": 0.10, "groups": 0.05,
           "gated": 0.05, "neutralization": 0.05}


@dataclass(frozen=True)
class Features:
    fields: frozenset
    operators: frozenset
    horizons: frozenset
    normalizer: str
    groups: frozenset
    gated: bool
    neutralization: str


def _horizon(lookback: int) -> str:
    if lookback <= 10:
        return "short"
    if lookback <= 63:
        return "medium"
    return "long"


def features(expression: str, neutralization: str = "", validator: Validator | None = None) -> Features | None:
    validator = validator or Validator()
    result = validator.validate(expression)
    if result.program is None:
        return None
    catalog = default_catalog()
    groups = {f for f in result.fields if (fld := catalog.get(f)) and fld.kind == "group"}
    output = result.program.output
    normalizer = ""
    for node in ast.walk(output):
        if isinstance(node, ast.Call) and call_name(node) in NORMALIZERS:
            normalizer = call_name(node)
            break
    ops = {name for name in result.operators if name not in ARITHMETIC}
    return Features(
        fields=frozenset(result.fields - groups),
        operators=frozenset(ops),
        horizons=frozenset(_horizon(lb) for lb in result.lookbacks) or frozenset({"none"}),
        normalizer=normalizer,
        groups=frozenset(groups),
        gated=bool(ops & GATES),
        neutralization=neutralization.upper(),
    )


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def similarity(a: Features, b: Features) -> float:
    score = (
        WEIGHTS["fields"] * _jaccard(a.fields, b.fields)
        + WEIGHTS["operators"] * _jaccard(a.operators, b.operators)
        + WEIGHTS["horizons"] * _jaccard(a.horizons, b.horizons)
        + WEIGHTS["normalizer"] * (a.normalizer == b.normalizer)
        + WEIGHTS["groups"] * _jaccard(a.groups, b.groups)
        + WEIGHTS["gated"] * (a.gated == b.gated)
        + WEIGHTS["neutralization"] * (a.neutralization == b.neutralization)
    )
    return round(score, 3)


def nearest(expression: str, neutralization: str, entries: list[Entry], top: int = 5) -> list[tuple[float, Entry]]:
    validator = Validator()
    target = features(expression, neutralization, validator)
    if target is None:
        return []
    scored = []
    for entry in entries:
        other = features(entry.expression, entry.settings.get("neutralization", ""), validator)
        if other is not None:
            scored.append((similarity(target, other), entry))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[:top]
