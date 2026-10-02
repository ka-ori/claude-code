"""Deterministic mutations and crossovers of Fast Expression programs.

These are the cheap, mechanical moves (lookback jumps, normalizer swaps, group
changes, event/regime gating). Claude adds the semantic ones in conversation.
Every variant returned here has passed the validator.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import dataclass

from .operators import Registry, default_registry
from .parser import Program, call_name, expr_to_source, parse, to_source
from .validator import Validator

HORIZONS = (3, 5, 10, 20, 40, 60, 120, 250, 500)
GROUP_LEVELS = ("market", "sector", "industry", "subindustry")
NORMALIZER_SWAPS = {
    "rank": "zscore",
    "zscore": "rank",
    "group_rank": "group_zscore",
    "group_zscore": "group_rank",
    "ts_rank": "ts_zscore",
    "ts_zscore": "ts_rank",
}

VOLUME_EVENT = "volume > ts_mean(volume, 20)"
TURBULENT = "ts_std_dev(returns, 20) > ts_std_dev(returns, 60)"
CALM = "ts_std_dev(returns, 20) < ts_std_dev(returns, 60)"


@dataclass
class Variant:
    kind: str
    description: str
    expression: str


def _lookback_slots(program: Program, registry: Registry) -> list[tuple[int, int, int]]:
    """(statement index, walk index, value) for every constant lookback argument."""
    slots = []
    for s_index, stmt in enumerate(program.statements):
        for w_index, node in enumerate(ast.walk(stmt.expr)):
            if not isinstance(node, ast.Call):
                continue
            op = registry.get(call_name(node) or "")
            if op is None:
                continue
            positional = [p for p in op.params if not p.variadic]
            for i, arg in enumerate(node.args):
                if i < len(positional) and positional[i].kind == "lookback":
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, int):
                        slots.append((s_index, w_index, i))
    return slots


def _node_at(program: Program, s_index: int, w_index: int) -> ast.AST:
    return list(ast.walk(program.statements[s_index].expr))[w_index]


def _neighbour_horizons(value: int) -> list[int]:
    lower = [h for h in HORIZONS if h < value * 0.75]
    higher = [h for h in HORIZONS if h > value * 1.33]
    return ([lower[-1]] if lower else []) + ([higher[0]] if higher else [])


def lookback_variants(program: Program, registry: Registry) -> list[Variant]:
    variants = []
    slots = _lookback_slots(program, registry)
    for s_index, w_index, arg_index in slots:
        call = _node_at(program, s_index, w_index)
        value = call.args[arg_index].value
        for new in _neighbour_horizons(value):
            clone = copy.deepcopy(program)
            target = _node_at(clone, s_index, w_index)
            target.args[arg_index] = ast.Constant(new)
            variants.append(Variant("lookback", f"{call_name(call)}: lookback {value} -> {new}", to_source(clone)))
    if len(slots) > 1:
        for factor, label in ((2, "longer"), (0.5, "shorter")):
            clone = copy.deepcopy(program)
            for s_index, w_index, arg_index in _lookback_slots(clone, registry):
                node = _node_at(clone, s_index, w_index)
                value = node.args[arg_index].value
                node.args[arg_index] = ast.Constant(max(2, min(500, int(round(value * factor)))))
            variants.append(Variant("horizon_shift", f"all lookbacks x{factor} ({label} horizon)", to_source(clone)))
    return variants


def normalizer_swaps(program: Program) -> list[Variant]:
    variants = []
    for s_index, stmt in enumerate(program.statements):
        for w_index, node in enumerate(ast.walk(stmt.expr)):
            if isinstance(node, ast.Call) and call_name(node) in NORMALIZER_SWAPS:
                old = call_name(node)
                new = NORMALIZER_SWAPS[old]
                clone = copy.deepcopy(program)
                target = _node_at(clone, s_index, w_index)
                target.func = ast.Name(new)
                target.keywords = []
                variants.append(Variant("normalizer_swap", f"{old} -> {new} (changes weight distribution)", to_source(clone)))
    return variants


def group_variants(program: Program) -> list[Variant]:
    variants = []
    has_group_op = False
    for s_index, stmt in enumerate(program.statements):
        for w_index, node in enumerate(ast.walk(stmt.expr)):
            if not (isinstance(node, ast.Call) and (call_name(node) or "").startswith("group_")):
                continue
            has_group_op = True
            for a_index, arg in enumerate(node.args):
                if isinstance(arg, ast.Name) and arg.id in GROUP_LEVELS:
                    for level in GROUP_LEVELS:
                        if level in (arg.id, "market"):
                            continue
                        clone = copy.deepcopy(program)
                        target = _node_at(clone, s_index, w_index)
                        target.args[a_index] = ast.Name(level)
                        variants.append(Variant("group_change", f"{call_name(node)}: {arg.id} -> {level}", to_source(clone)))
    if not has_group_op:
        for level in ("industry", "subindustry"):
            variants.append(_wrap(program, f"group_neutralize({{x}}, {level})", "group_neutralize",
                                  f"neutralize within {level} inside the expression"))
    return variants


def _wrap(program: Program, template: str, kind: str, description: str) -> Variant:
    prefix = [f"{s.target} = {expr_to_source(s.expr)}" for s in program.statements[:-1]]
    body = template.format(x=expr_to_source(program.output))
    return Variant(kind, description, "; ".join(prefix + [body]))


def gating_variants(program: Program) -> list[Variant]:
    return [
        _wrap(program, f"trade_when({VOLUME_EVENT}, {{x}}, -1)", "volume_event_gate",
              "only update positions on abnormal-volume days (event-driven, lower turnover)"),
        _wrap(program, f"trade_when({TURBULENT}, {{x}}, -1)", "turbulent_regime_gate",
              "only update positions when short-term volatility exceeds its 60-day baseline"),
        _wrap(program, f"trade_when({CALM}, {{x}}, -1)", "calm_regime_gate",
              "only update positions in calm regimes"),
        _wrap(program, "ts_decay_linear({x}, 5)", "decay_wrap", "smooth inside the expression (5-day linear decay)"),
    ]


def sign_flip(program: Program) -> Variant:
    return _wrap(program, "-({x})", "sign_flip", "reverse the bet (only if the opposite hypothesis is economically sensible)")


def _rename_variables(program: Program, suffix: str) -> Program:
    targets = {s.target for s in program.statements if s.target}
    clone = copy.deepcopy(program)

    class Renamer(ast.NodeTransformer):
        def visit_Name(self, node):
            if node.id in targets:
                return ast.copy_location(ast.Name(node.id + suffix), node)
            return node

    for stmt in clone.statements:
        stmt.expr = Renamer().visit(stmt.expr)
        if stmt.target:
            stmt.target += suffix
    return clone


def crossover(source_a: str, source_b: str) -> list[Variant]:
    a = parse(source_a)
    b = _rename_variables(parse(source_b), "_b")
    prefix = [f"{s.target} = {expr_to_source(s.expr)}" for s in a.statements[:-1] + b.statements[:-1]]
    xa, xb = expr_to_source(a.output), expr_to_source(b.output)

    def build(body: str) -> str:
        return "; ".join(prefix + [body])

    return [
        Variant("regime_switch", "A in turbulent regimes, B in calm regimes",
                build(f"if_else({TURBULENT}, {xa}, {xb})")),
        Variant("conditional_gate", "trade A only where B ranks in the top half",
                build(f"trade_when(rank({xb}) > 0.5, {xa}, -1)")),
        Variant("blend", "equal-weight rank blend (raises correlation with both parents)",
                build(f"rank({xa}) + rank({xb})")),
    ]


def mutate(source: str, registry: Registry | None = None, validator: Validator | None = None,
           kinds: set[str] | None = None) -> list[Variant]:
    registry = registry or default_registry()
    validator = validator or Validator(registry=registry)
    program = parse(source)
    original = to_source(program)
    candidates = (
        lookback_variants(program, registry)
        + normalizer_swaps(program)
        + group_variants(program)
        + gating_variants(program)
        + [sign_flip(program)]
    )
    return _keep_valid(candidates, validator, exclude={original}, kinds=kinds)


def crossover_valid(source_a: str, source_b: str, validator: Validator | None = None) -> list[Variant]:
    return _keep_valid(crossover(source_a, source_b), validator or Validator(), exclude=set())


def _keep_valid(candidates: list[Variant], validator: Validator, exclude: set[str],
                kinds: set[str] | None = None) -> list[Variant]:
    seen = set(exclude)
    kept = []
    for variant in candidates:
        if kinds and variant.kind not in kinds:
            continue
        result = validator.validate(variant.expression)
        if not result.ok or result.canonical in seen:
            continue
        seen.add(result.canonical)
        kept.append(Variant(variant.kind, variant.description, result.canonical))
    return kept
