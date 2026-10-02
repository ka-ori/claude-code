"""Semantic validation of Fast Expression programs.

Catches the mistakes that waste BRAIN simulations: unknown operators, wrong
argument counts, vector fields fed to matrix operators, non-group arguments in
group slots, non-constant or oversized lookbacks, and Python-only syntax. It also
emits research warnings (raw price levels, cross-sector fundamental comparisons,
unsmoothed short-horizon signals, excessive complexity).
"""

from __future__ import annotations

import ast
import difflib
from collections import Counter
from dataclasses import dataclass, field

from ..catalog import Catalog, default_catalog
from .operators import BOOL, GROUP, MATRIX, SCALAR, STRING, VECTOR, Operator, Registry, default_registry
from .parser import RESTORE_FUNCS, ParseError, Program, call_name, parse, to_source

UNKNOWN = "unknown"  # type of a node that already produced an error (stops cascades)

NORMALIZERS = {"rank", "zscore", "scale", "normalize", "quantile", "group_rank", "group_zscore", "group_scale", "group_normalize"}
SMOOTHERS = {"ts_decay_linear", "ts_decay_exp_window", "ts_mean", "hump", "trade_when", "ts_target_tvr_decay", "ts_weighted_decay", "jump_decay"}
INDUSTRY_NEUTRALIZATIONS = {"SECTOR", "INDUSTRY", "SUBINDUSTRY"}
CONSTANT_NAMES = {"true": BOOL, "false": BOOL, "nan": SCALAR}
COMPLEXITY_WARN = 14

_UNSUPPORTED_BINOP_HINTS = {
    ast.Pow: "use power(x, y) or signed_power(x, y)",
    ast.BitXor: "`^` is not exponentiation here; use power(x, y) or signed_power(x, y)",
    ast.Mod: "there is no modulo operator",
    ast.FloorDiv: "use floor(x / y)",
    ast.BitAnd: "use and(x, y) or x && y",
    ast.BitOr: "use or(x, y) or x || y",
}


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "note"
    code: str
    message: str
    hint: str | None = None

    def __str__(self) -> str:
        text = f"[{self.severity}] {self.code}: {self.message}"
        return f"{text}\n    hint: {self.hint}" if self.hint else text


@dataclass
class ValidationResult:
    source: str
    canonical: str | None = None
    issues: list[Issue] = field(default_factory=list)
    operators: Counter = field(default_factory=Counter)
    fields: set[str] = field(default_factory=set)
    lookbacks: list[int] = field(default_factory=list)
    n_nodes: int = 0
    depth: int = 0
    program: Program | None = None

    @property
    def ok(self) -> bool:
        return not self.errors

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "canonical": self.canonical,
            "issues": [vars(i) for i in self.issues],
            "operators": dict(self.operators),
            "fields": sorted(self.fields),
            "lookbacks": self.lookbacks,
            "n_operators": sum(self.operators.values()),
            "depth": self.depth,
        }

    def format(self) -> str:
        lines = ["VALID" if self.ok else "INVALID"]
        if self.canonical:
            lines.append(f"canonical: {self.canonical}")
        if self.ok:
            lines.append(
                f"operators: {sum(self.operators.values())}  depth: {self.depth}  "
                f"fields: {', '.join(sorted(self.fields)) or '-'}  lookbacks: {self.lookbacks or '-'}"
            )
        lines.extend(str(i) for i in self.issues)
        return "\n".join(lines)


class Validator:
    def __init__(
        self,
        registry: Registry | None = None,
        catalog: Catalog | None = None,
        *,
        strict_fields: bool = False,
        max_lookback: int = 512,
        neutralization: str | None = None,
        decay: int | None = None,
    ):
        self.registry = registry or default_registry()
        self.catalog = catalog or default_catalog()
        self.strict_fields = strict_fields
        self.max_lookback = max_lookback
        self.neutralization = neutralization.upper() if neutralization else None
        self.decay = decay

    # -- public -------------------------------------------------------------

    def validate(self, source: str) -> ValidationResult:
        result = ValidationResult(source=source)
        try:
            program = parse(source)
        except ParseError as exc:
            result.issues.append(Issue("error", "PARSE", exc.message, exc.hint))
            return result
        result.program = program
        self._result = result
        self._locals: dict[str, str] = {}
        self._used_locals: set[str] = set()
        self._all_targets = {s.target for s in program.statements if s.target}
        self._reported_unknown: set[str] = set()

        for index, stmt in enumerate(program.statements):
            last = index == len(program.statements) - 1
            kind = self._visit(stmt.expr, depth=1)
            if stmt.target:
                if last:
                    self._error("NO_OUTPUT", "the last statement must be the alpha expression, not an assignment",
                                f"add `{stmt.target}` (or an expression using it) as the final statement")
                if stmt.target in self.registry:
                    self._warn("SHADOWS_OPERATOR", f"variable `{stmt.target}` shadows an operator name")
                elif stmt.target in self.catalog:
                    self._warn("SHADOWS_FIELD", f"variable `{stmt.target}` shadows a data field")
                self._locals[stmt.target] = kind
            elif not last:
                self._warn("UNUSED_STATEMENT", "only the last expression is the alpha; earlier bare expressions are ignored")
            if last and kind in (VECTOR, GROUP, STRING):
                self._error("BAD_OUTPUT", f"the alpha must evaluate to numeric weights, got a {kind}",
                            "wrap vectors in vec_avg/vec_sum; groups belong inside group_* operators")

        for name in sorted(self._all_targets - self._used_locals):
            self._warn("UNUSED_VARIABLE", f"variable `{name}` is assigned but never used")

        if result.ok:
            result.canonical = to_source(program)
            self._research_checks(program)
        return result

    # -- reporting ----------------------------------------------------------

    def _error(self, code: str, message: str, hint: str | None = None) -> None:
        self._result.issues.append(Issue("error", code, message, hint))

    def _warn(self, code: str, message: str, hint: str | None = None) -> None:
        self._result.issues.append(Issue("warning", code, message, hint))

    def _note(self, code: str, message: str, hint: str | None = None) -> None:
        self._result.issues.append(Issue("note", code, message, hint))

    # -- type inference -----------------------------------------------------

    def _visit(self, node: ast.expr, depth: int) -> str:
        self._result.n_nodes += 1
        self._result.depth = max(self._result.depth, depth)

        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return BOOL
            if isinstance(node.value, (int, float)):
                return SCALAR
            if isinstance(node.value, str):
                return STRING
            self._error("BAD_CONSTANT", f"unsupported literal {node.value!r}")
            return UNKNOWN

        if isinstance(node, ast.Name):
            return self._resolve_name(node.id)

        if isinstance(node, ast.Call):
            return self._visit_call(node, depth)

        if isinstance(node, ast.BinOp):
            hint = _UNSUPPORTED_BINOP_HINTS.get(type(node.op))
            if hint or not isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
                self._error("UNSUPPORTED_OPERATOR", f"operator `{type(node.op).__name__}` is not Fast Expression", hint)
                return UNKNOWN
            self._result.operators[type(node.op).__name__.lower()] += 1
            left = self._numeric_operand(node.left, depth + 1, "arithmetic")
            right = self._numeric_operand(node.right, depth + 1, "arithmetic")
            if UNKNOWN in (left, right):
                return UNKNOWN
            return SCALAR if left == right == SCALAR else MATRIX

        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Invert):
                self._error("UNSUPPORTED_OPERATOR", "`~` is not Fast Expression", "use not(x)")
                return UNKNOWN
            operand = self._numeric_operand(node.operand, depth + 1, "unary")
            if operand == UNKNOWN:
                return UNKNOWN
            return MATRIX if isinstance(node.op, ast.Not) else operand

        if isinstance(node, ast.Compare):
            if len(node.ops) > 1:
                self._error("CHAINED_COMPARISON", "chained comparisons like a < b < c are not supported",
                            "use and(a < b, b < c)")
                return UNKNOWN
            if isinstance(node.ops[0], (ast.Is, ast.IsNot, ast.In, ast.NotIn)):
                self._error("UNSUPPORTED_OPERATOR", "`is`/`in` are Python, not Fast Expression")
                return UNKNOWN
            self._result.operators["compare"] += 1
            left = self._numeric_operand(node.left, depth + 1, "comparison")
            right = self._numeric_operand(node.comparators[0], depth + 1, "comparison")
            return UNKNOWN if UNKNOWN in (left, right) else MATRIX

        if isinstance(node, ast.BoolOp):
            self._result.operators["and" if isinstance(node.op, ast.And) else "or"] += len(node.values) - 1
            kinds = [self._numeric_operand(v, depth + 1, "logical") for v in node.values]
            return UNKNOWN if UNKNOWN in kinds else MATRIX

        if isinstance(node, ast.IfExp):
            self._error("PYTHON_SYNTAX", "Python `a if c else b` is not Fast Expression", "use if_else(c, a, b)")
            return UNKNOWN

        self._error("PYTHON_SYNTAX", f"`{type(node).__name__}` is not valid Fast Expression",
                    "only operators, fields, numbers, strings, + - * /, comparisons and && || are allowed")
        return UNKNOWN

    def _numeric_operand(self, node: ast.expr, depth: int, context: str) -> str:
        kind = self._visit(node, depth)
        if kind == VECTOR:
            self._error("VECTOR_NOT_REDUCED", f"vector value `{_short(node)}` used in {context}",
                        f"collapse it first, e.g. vec_avg({_short(node)}) or vec_sum({_short(node)})")
            return UNKNOWN
        if kind == GROUP:
            self._error("GROUP_AS_VALUE", f"group `{_short(node)}` used as a number in {context}",
                        "group fields only go in the group argument of group_* operators")
            return UNKNOWN
        if kind == STRING:
            self._error("STRING_AS_VALUE", f"string {_short(node)} used as a number in {context}")
            return UNKNOWN
        return kind

    def _resolve_name(self, name: str) -> str:
        if name in self._locals:
            self._used_locals.add(name)
            return self._locals[name]
        if name in self._all_targets:
            self._error("USE_BEFORE_ASSIGN", f"variable `{name}` is used before it is assigned")
            return UNKNOWN
        if name in CONSTANT_NAMES:
            return CONSTANT_NAMES[name]
        if name in RESTORE_FUNCS or name in self.registry:
            self._error("OPERATOR_AS_VALUE", f"operator `{RESTORE_FUNCS.get(name, name)}` used without arguments")
            return UNKNOWN
        fld = self.catalog.get(name)
        if fld:
            self._result.fields.add(name)
            return fld.kind
        self._result.fields.add(name)
        if name not in self._reported_unknown:
            self._reported_unknown.add(name)
            close = difflib.get_close_matches(name, [f.id for f in self.catalog], n=3)
            hint = f"did you mean {', '.join(close)}?" if close else (
                "check the ID on the BRAIN Data page, then `python -m alphagen fields add`")
            if self.strict_fields:
                self._error("UNKNOWN_FIELD", f"`{name}` is not in the local field dictionary", hint)
            else:
                self._warn("UNKNOWN_FIELD", f"`{name}` is not in the local field dictionary (assumed matrix)", hint)
        return MATRIX

    # -- calls --------------------------------------------------------------

    def _visit_call(self, node: ast.Call, depth: int) -> str:
        name = call_name(node)
        if name is None:
            self._error("PYTHON_SYNTAX", "only plain operator calls like ts_mean(x, 20) are allowed")
            return UNKNOWN
        op = self.registry.get(name)
        if op is None:
            close = difflib.get_close_matches(name, self.registry.names(), n=3)
            self._error("UNKNOWN_OPERATOR", f"`{name}` is not a known operator",
                        f"did you mean {', '.join(close)}?" if close else "see `python -m alphagen operators`")
            for arg in node.args:
                self._visit(arg, depth + 1)
            return UNKNOWN
        if op.unavailable:
            self._error("UNAVAILABLE_OPERATOR", f"`{name}` is marked unavailable on your BRAIN account")
        self._result.operators[name] += 1

        bound, ok = self._bind(op, node)
        failed = not ok
        for param, arg in bound:
            if self._check_arg(op, param, arg, depth + 1) == UNKNOWN:
                failed = True
        return UNKNOWN if failed else op.returns

    def _bind(self, op: Operator, node: ast.Call):
        bound = []
        ok = True
        positional = [p for p in op.params if not p.variadic]
        variadic = op.variadic
        required_count = len(op.positional)
        used: set[str] = set()

        for index, arg in enumerate(node.args):
            if isinstance(arg, ast.Starred):
                self._error("PYTHON_SYNTAX", "`*args` unpacking is not Fast Expression")
                ok = False
                continue
            if index < required_count:
                param = positional[index]
            elif variadic is not None:
                param = variadic
            elif index < len(positional):
                param = positional[index]
                self._warn("POSITIONAL_OPTIONAL",
                           f"optional parameter `{param.name}` of {op.name} passed positionally",
                           f"pass it by keyword: {param.name}={_short(arg)} ({op.signature})")
            else:
                self._error("TOO_MANY_ARGS",
                            f"{op.name} takes {required_count} positional argument(s), got {len(node.args)}",
                            f"signature: {op.signature}")
                ok = False
                self._visit(arg, 2)
                continue
            used.add(param.name)
            bound.append((param, arg))

        for kw in node.keywords:
            if kw.arg is None:
                self._error("PYTHON_SYNTAX", "`**kwargs` unpacking is not Fast Expression")
                ok = False
                continue
            param = op.param(kw.arg)
            if param is None or param.variadic:
                valid = ", ".join(p.name for p in op.params if not p.variadic)
                self._error("UNKNOWN_KEYWORD", f"{op.name} has no parameter `{kw.arg}`", f"valid: {valid}")
                ok = False
                continue
            if param.name in used:
                self._error("DUPLICATE_ARG", f"{op.name} got `{param.name}` twice")
                ok = False
                continue
            used.add(param.name)
            bound.append((param, kw.value))

        missing = [p.name for p in op.positional if p.name not in used]
        if missing:
            self._error("MISSING_ARG", f"{op.name} is missing {', '.join(missing)}", f"signature: {op.signature}")
            ok = False
        if op.one_of and not any(name in used for name in op.one_of):
            self._error("MISSING_ARG", f"{op.name} needs one of: {', '.join(op.one_of)}", f"signature: {op.signature}")
            ok = False
        return bound, ok

    def _check_arg(self, op: Operator, param, arg: ast.expr, depth: int) -> str:
        kind = param.kind
        label = f"{op.name}({param.name}=...)"

        if kind == "lookback":
            value = _constant_number(arg)
            self._result.n_nodes += 1
            if value is None:
                self._error("NON_CONSTANT_LOOKBACK", f"{label}: lookback must be an integer constant",
                            f"got `{_short(arg)}`")
                return UNKNOWN
            if not float(value).is_integer() or value <= 0:
                self._error("BAD_LOOKBACK", f"{label}: lookback must be a positive integer, got {value}")
                return UNKNOWN
            if value > self.max_lookback:
                self._error("LOOKBACK_TOO_LONG", f"{label}: lookback {int(value)} exceeds {self.max_lookback} days")
                return UNKNOWN
            self._result.lookbacks.append(int(value))
            return SCALAR

        if kind in ("int", "number"):
            value = _constant_number(arg)
            self._result.n_nodes += 1
            if value is None:
                self._error("NON_CONSTANT_PARAM", f"{label}: expected a numeric constant, got `{_short(arg)}`")
                return UNKNOWN
            if kind == "int" and not float(value).is_integer():
                self._error("BAD_PARAM", f"{label}: expected an integer, got {value}")
                return UNKNOWN
            bounds = op.ranges.get(param.name)
            if bounds and not (bounds[0] < value <= bounds[1]):
                self._error("OUT_OF_RANGE", f"{label}: {value} outside ({bounds[0]}, {bounds[1]}]")
                return UNKNOWN
            return SCALAR

        if kind == STRING:
            self._result.n_nodes += 1
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                self._error("BAD_PARAM", f"{label}: expected a quoted string, got `{_short(arg)}`")
                return UNKNOWN
            return STRING

        if kind == BOOL:
            self._result.n_nodes += 1
            if isinstance(arg, ast.Constant) and isinstance(arg.value, bool):
                return BOOL
            if isinstance(arg, ast.Name) and arg.id in ("true", "false"):
                return BOOL
            self._error("BAD_PARAM", f"{label}: expected true or false, got `{_short(arg)}`")
            return UNKNOWN

        if kind == GROUP:
            if isinstance(arg, ast.Name) and arg.id not in self._locals and arg.id not in self.catalog \
                    and arg.id not in self._all_targets and arg.id not in CONSTANT_NAMES:
                # Unknown name in a group slot: likely a dataset-specific grouping field.
                self._resolve_name(arg.id)
                return GROUP
            got = self._visit(arg, depth)
            if got in (GROUP, UNKNOWN):
                return got
            self._error("EXPECTED_GROUP", f"{label}: expected a group, got a {got}",
                        'use market/sector/industry/subindustry or bucket(rank(x), range="0,1,0.1")')
            return UNKNOWN

        if kind == VECTOR:
            got = self._visit(arg, depth)
            if got in (VECTOR, UNKNOWN):
                return got
            self._error("EXPECTED_VECTOR", f"{label}: vec_* operators take a vector field, got a {got}",
                        "vector fields are listed with type VECTOR on the BRAIN Data page")
            return UNKNOWN

        # matrix
        got = self._visit(arg, depth)
        if got == VECTOR:
            self._error("VECTOR_NOT_REDUCED", f"{label}: `{_short(arg)}` is a vector field",
                        f"collapse it first, e.g. vec_avg({_short(arg)}) or vec_sum({_short(arg)})")
            return UNKNOWN
        if got == GROUP:
            self._error("GROUP_AS_VALUE", f"{label}: `{_short(arg)}` is a group, not a number",
                        "groups only go in the group argument of group_* operators")
            return UNKNOWN
        if got == STRING:
            self._error("STRING_AS_VALUE", f"{label}: unexpected string {_short(arg)}")
            return UNKNOWN
        return got

    # -- research heuristics -------------------------------------------------

    def _research_checks(self, program: Program) -> None:
        result = self._result
        calls = [n for s in program.statements for n in ast.walk(s.expr) if isinstance(n, ast.Call)]
        names = {call_name(c) for c in calls}
        output = program.output

        if isinstance(output, ast.Name) and output.id in self.catalog:
            self._warn("BARE_FIELD", f"the alpha is the raw field `{output.id}`",
                       "turn it into a comparable signal: a ratio, a change, then rank/zscore")

        bucket_inputs = {id(c.args[0]) for c in calls if call_name(c) == "bucket" and c.args}
        for call in calls:
            name = call_name(call)
            if name in NORMALIZERS and call.args and id(call) not in bucket_inputs:
                inner = call.args[0]
                if isinstance(inner, ast.Name):
                    fld = self.catalog.get(inner.id)
                    if fld and fld.is_level:
                        self._warn("RAW_LEVEL", f"{name}({inner.id}) ranks a raw level that is not comparable across stocks",
                                   "scale it (per share, per asset, per cap) or use its change over time")
                if isinstance(inner, ast.Call) and call_name(inner) in {"rank", "zscore"} and name in {"rank", "zscore"}:
                    self._note("NESTED_NORMALIZER", f"{name}({call_name(inner)}(...)) is usually redundant")

        fundamentals = [f for f in result.fields if (fld := self.catalog.get(f)) and fld.category == "fundamental"]
        has_group_op = any(n and n.startswith("group_") for n in names)
        if fundamentals and not has_group_op and self.neutralization not in INDUSTRY_NEUTRALIZATIONS:
            self._warn("CROSS_SECTOR_FUNDAMENTALS",
                       f"fundamentals ({', '.join(sorted(fundamentals))}) are compared across the whole market",
                       "compare peers: group_rank/group_zscore(..., industry) or neutralize by industry/subindustry")
        if fundamentals and "ts_backfill" not in names:
            self._note("SPARSE_FUNDAMENTALS", "fundamental fields can have gaps between filings",
                       "consider ts_backfill(field, 63) on sparse fields")

        price_volume = [f for f in result.fields if (fld := self.catalog.get(f)) and fld.category == "price_volume"]
        short = [lb for lb in result.lookbacks if lb <= 5]
        if price_volume and short and not names & SMOOTHERS and (self.decay is None or self.decay < 3):
            self._warn("HIGH_TURNOVER_RISK",
                       f"short lookbacks {sorted(set(short))} on price/volume data without smoothing",
                       "expect high turnover: set Decay 4-10, or wrap in ts_decay_linear / trade_when")

        n_ops = sum(result.operators.values())
        if n_ops > COMPLEXITY_WARN:
            self._warn("COMPLEX", f"{n_ops} operators: complex alphas are more likely to be overfit",
                       "prefer the simplest expression that carries the hypothesis")


def _constant_number(node: ast.expr) -> float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        inner = _constant_number(node.operand)
        if inner is not None:
            return -inner if isinstance(node.op, ast.USub) else inner
    return None


def _short(node: ast.expr) -> str:
    from .parser import expr_to_source

    try:
        text = expr_to_source(node)
    except ParseError:
        text = ast.unparse(node)
    return text if len(text) <= 60 else text[:57] + "..."


def validate(source: str, **kwargs) -> ValidationResult:
    return Validator(**kwargs).validate(source)
