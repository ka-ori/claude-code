"""Operator registry for BRAIN Fast Expression.

Signatures live in ``alphagen/data/operators.json`` in a compact form, e.g.
``winsorize(x:matrix, std:number=4)``. This module parses them into
:class:`Operator` objects that the validator uses for arity and type checks.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OPERATORS_PATH = DATA_DIR / "operators.json"

# Value kinds an expression node can evaluate to.
MATRIX = "matrix"   # one number per instrument per day
VECTOR = "vector"   # an array per instrument per day (must be collapsed with vec_*)
GROUP = "group"     # categorical labels (sector, industry, bucket(...))
SCALAR = "scalar"   # numeric constant
STRING = "string"
BOOL = "bool"

PARAM_KINDS = {MATRIX, VECTOR, GROUP, "lookback", "int", "number", STRING, BOOL}

CATEGORY_ORDER = [
    "arithmetic",
    "logical",
    "time_series",
    "cross_sectional",
    "vector",
    "group",
    "transformational",
]

_SIG_RE = re.compile(r"^\s*(\w+)\s*\((.*)\)\s*(?:->\s*(\w+))?\s*$")
_PARAM_RE = re.compile(r"^\s*(\*?)(\w+)\s*:\s*(\w+)\s*(?:=\s*(.+?))?\s*$")


@dataclass(frozen=True)
class Param:
    name: str
    kind: str
    required: bool = True
    default: object = None
    variadic: bool = False

    def display(self) -> str:
        if self.variadic:
            return f"*{self.name}"
        if self.required:
            return self.name
        return f"{self.name}={_format_default(self.default)}"


@dataclass(frozen=True)
class Operator:
    name: str
    category: str
    params: tuple[Param, ...]
    returns: str = MATRIX
    doc: str = ""
    ranges: dict = field(default_factory=dict)
    one_of: tuple[str, ...] = ()
    unavailable: bool = False

    @property
    def signature(self) -> str:
        return f"{self.name}({', '.join(p.display() for p in self.params)})"

    @property
    def positional(self) -> list[Param]:
        return [p for p in self.params if p.required and not p.variadic]

    @property
    def variadic(self) -> Param | None:
        return next((p for p in self.params if p.variadic), None)

    @property
    def optional(self) -> list[Param]:
        return [p for p in self.params if not p.required and not p.variadic]

    def param(self, name: str) -> Param | None:
        return next((p for p in self.params if p.name == name), None)


def _format_default(value: object) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "..."
    if isinstance(value, str):
        return f'"{value}"'
    return str(value)


def _parse_default(raw: str | None) -> object:
    if raw is None:
        return None
    raw = raw.strip()
    if raw in ("true", "false"):
        return raw == "true"
    if raw == "null":
        return None
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    try:
        return int(raw)
    except ValueError:
        return float(raw)


def _split_params(text: str) -> list[str]:
    parts, depth, quote, current = [], 0, False, []
    for ch in text:
        if ch == '"':
            quote = not quote
        elif not quote and ch == "(":
            depth += 1
        elif not quote and ch == ")":
            depth -= 1
        if ch == "," and depth == 0 and not quote:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if "".join(current).strip():
        parts.append("".join(current))
    return parts


def parse_signature(sig: str) -> tuple[str, tuple[Param, ...], str]:
    match = _SIG_RE.match(sig)
    if not match:
        raise ValueError(f"bad operator signature: {sig!r}")
    name, body, returns = match.group(1), match.group(2), match.group(3) or MATRIX
    params = []
    for chunk in _split_params(body):
        pm = _PARAM_RE.match(chunk)
        if not pm:
            raise ValueError(f"bad parameter {chunk!r} in {sig!r}")
        star, pname, kind, raw_default = pm.groups()
        if kind not in PARAM_KINDS:
            raise ValueError(f"unknown kind {kind!r} in {sig!r}")
        params.append(
            Param(
                name=pname,
                kind=kind,
                required=raw_default is None and not star,
                default=_parse_default(raw_default),
                variadic=bool(star),
            )
        )
    return name, tuple(params), returns


class Registry:
    def __init__(self, operators: dict[str, Operator]):
        self._ops = operators

    @classmethod
    def load(cls, path: Path = OPERATORS_PATH) -> "Registry":
        data = json.loads(Path(path).read_text())
        ops = {}
        for entry in data["operators"]:
            name, params, returns = parse_signature(entry["sig"])
            ops[name] = Operator(
                name=name,
                category=entry.get("cat", "other"),
                params=params,
                returns=returns,
                doc=entry.get("doc", ""),
                ranges={k: tuple(v) for k, v in entry.get("ranges", {}).items()},
                one_of=tuple(entry.get("one_of", ())),
                unavailable=entry.get("unavailable", False),
            )
        return cls(ops)

    def get(self, name: str) -> Operator | None:
        return self._ops.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._ops

    def __iter__(self):
        return iter(self._ops.values())

    def names(self) -> list[str]:
        return sorted(self._ops)

    def by_category(self) -> dict[str, list[Operator]]:
        grouped: dict[str, list[Operator]] = {}
        for op in self._ops.values():
            grouped.setdefault(op.category, []).append(op)
        ordered = {c: grouped.pop(c) for c in CATEGORY_ORDER if c in grouped}
        ordered.update(grouped)
        return ordered


@lru_cache(maxsize=1)
def default_registry() -> Registry:
    return Registry.load()
