"""Parse BRAIN Fast Expression source with Python's ``ast`` module.

Fast Expression is close enough to Python expression syntax that the standard
library parser can build its syntax tree after a light preprocessing pass:

* comments (``#`` / ``//`` to end of line) are dropped and lines are joined, since
  BRAIN statements are separated by ``;`` rather than newlines;
* ``&&`` / ``||`` become Python ``and`` / ``or``;
* the function forms ``and(...)``, ``or(...)``, ``not(...)`` collide with Python
  keywords, so they are renamed to private identifiers and restored on output;
* ternaries (``c ? a : b``) and bare ``!`` are rejected with a hint.

``to_source`` turns the tree back into canonical Fast Expression text, so the
string that was validated is exactly the string you paste into BRAIN.
"""

from __future__ import annotations

import ast
import io
import re
import tokenize
from dataclasses import dataclass

KEYWORD_FUNCS = {"and": "_kw_and", "or": "_kw_or", "not": "_kw_not"}
RESTORE_FUNCS = {v: k for k, v in KEYWORD_FUNCS.items()}

# Tokens after which an identifier sits in operand position (so `and(` is a call).
_OPERAND_PREFIX = {
    "(", ",", "=", "+", "-", "*", "/", "<", ">", "<=", ">=", "==", "!=", ";",
}


class ParseError(Exception):
    def __init__(self, message: str, hint: str | None = None, column: int | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.column = column


@dataclass
class Statement:
    target: str | None  # variable name for `name = expr`, None for a bare expression
    expr: ast.expr


@dataclass
class Program:
    statements: list[Statement]

    @property
    def output(self) -> ast.expr:
        return self.statements[-1].expr

    @property
    def assignments(self) -> list[Statement]:
        return [s for s in self.statements if s.target is not None]


def _strip_comments_and_join(source: str) -> str:
    out_lines = []
    for line in source.splitlines():
        in_string = False
        cut = len(line)
        for i, ch in enumerate(line):
            if ch == '"':
                in_string = not in_string
            elif not in_string and (ch == "#" or line.startswith("//", i)):
                cut = i
                break
        out_lines.append(line[:cut])
    return " ".join(part.strip() for part in out_lines if part.strip())


def preprocess(source: str) -> str:
    text = _strip_comments_and_join(source.replace("'", '"'))
    if not text:
        raise ParseError("empty expression")
    if "?" in text:
        raise ParseError(
            "ternary `cond ? a : b` is not supported here",
            hint="use if_else(cond, a, b)",
            column=text.index("?"),
        )
    bang = re.search(r"!(?!=)", text)
    if bang:
        raise ParseError(
            "bare `!` is ambiguous",
            hint="use not(x) for logical negation",
            column=bang.start(),
        )
    text = text.replace("&&", " and ").replace("||", " or ")
    return _rename_keyword_calls(text)


def _rename_keyword_calls(text: str) -> str:
    try:
        tokens = [
            t
            for t in tokenize.generate_tokens(io.StringIO(text).readline)
            if t.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.ENDMARKER, tokenize.INDENT, tokenize.DEDENT)
        ]
    except tokenize.TokenError as exc:
        raise ParseError("unbalanced parentheses or unterminated string", hint=str(exc)) from exc
    except IndentationError as exc:  # leading whitespace oddities
        raise ParseError("unexpected indentation", hint=str(exc)) from exc

    edits = []
    for i, tok in enumerate(tokens):
        if tok.type != tokenize.NAME or tok.string not in KEYWORD_FUNCS:
            continue
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        if nxt is None or nxt.string != "(":
            continue
        prev = tokens[i - 1] if i > 0 else None
        operand_position = (
            prev is None
            or (prev.type == tokenize.OP and prev.string in _OPERAND_PREFIX)
            or (prev.type == tokenize.NAME and prev.string in KEYWORD_FUNCS)
        )
        if operand_position:
            edits.append((tok.start[1], tok.end[1], KEYWORD_FUNCS[tok.string]))

    for start, end, replacement in reversed(edits):
        text = text[:start] + replacement + text[end:]
    return text


def parse(source: str) -> Program:
    text = preprocess(source)
    try:
        module = ast.parse(text, mode="exec")
    except SyntaxError as exc:
        hint = None
        if "keyword argument" in (exc.msg or ""):
            hint = "keyword arguments must come after positional ones"
        raise ParseError(f"syntax error: {exc.msg}", hint=hint, column=(exc.offset or 1) - 1) from exc

    statements = []
    for node in module.body:
        if isinstance(node, ast.Expr):
            statements.append(Statement(None, node.value))
        elif isinstance(node, ast.Assign):
            if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                raise ParseError("only simple assignments like `a = expr;` are allowed")
            statements.append(Statement(node.targets[0].id, node.value))
        else:
            raise ParseError(
                f"`{type(node).__name__}` statements are not Fast Expression",
                hint="use `name = expr;` assignments and end with the alpha expression",
            )
    if not statements:
        raise ParseError("empty expression")
    return Program(statements)


# ---------------------------------------------------------------------------
# Canonical printer
# ---------------------------------------------------------------------------

_BINOP_SYMBOL = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/"}
_CMP_SYMBOL = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
}
_PREC_COMPARE, _PREC_ADD, _PREC_MUL, _PREC_UNARY, _PREC_ATOM = 1, 2, 3, 4, 5


def _precedence(node: ast.expr) -> int:
    if isinstance(node, ast.Compare):
        return _PREC_COMPARE
    if isinstance(node, ast.BinOp):
        return _PREC_ADD if isinstance(node.op, (ast.Add, ast.Sub)) else _PREC_MUL
    if isinstance(node, ast.UnaryOp) and not isinstance(node.op, ast.Not):
        return _PREC_UNARY
    return _PREC_ATOM


def _wrap(node: ast.expr, needs_parens: bool) -> str:
    text = expr_to_source(node)
    return f"({text})" if needs_parens else text


def call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return RESTORE_FUNCS.get(node.func.id, node.func.id)
    return None


def expr_to_source(node: ast.expr) -> str:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, str):
            return f'"{value}"'
        if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
            return repr(value)
        return repr(value)
    if isinstance(node, ast.Name):
        return RESTORE_FUNCS.get(node.id, node.id)
    if isinstance(node, ast.Call):
        name = call_name(node) or expr_to_source(node.func)
        args = [expr_to_source(a) for a in node.args]
        args += [f"{kw.arg}={expr_to_source(kw.value)}" for kw in node.keywords]
        return f"{name}({', '.join(args)})"
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOP_SYMBOL:
        prec = _precedence(node)
        left = _wrap(node.left, _precedence(node.left) < prec)
        right = _wrap(node.right, _precedence(node.right) <= prec)
        return f"{left} {_BINOP_SYMBOL[type(node.op)]} {right}"
    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.Not):
            return f"not({expr_to_source(node.operand)})"
        symbol = "-" if isinstance(node.op, ast.USub) else "+"
        operand = node.operand
        needs = _precedence(operand) < _PREC_ATOM and not (
            isinstance(operand, ast.Constant) and not isinstance(operand.value, (str, bool))
        )
        return f"{symbol}{_wrap(operand, needs)}"
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMP_SYMBOL:
        left = _wrap(node.left, _precedence(node.left) <= _PREC_COMPARE)
        right = _wrap(node.comparators[0], _precedence(node.comparators[0]) <= _PREC_COMPARE)
        return f"{left} {_CMP_SYMBOL[type(node.ops[0])]} {right}"
    if isinstance(node, ast.BoolOp):
        name = "and" if isinstance(node.op, ast.And) else "or"
        values = [expr_to_source(v) for v in node.values]
        text = values[0]
        for value in values[1:]:
            text = f"{name}({text}, {value})"
        return text
    raise ParseError(f"cannot print `{type(node).__name__}` as Fast Expression")


def to_source(program: Program) -> str:
    parts = []
    for stmt in program.statements:
        text = expr_to_source(stmt.expr)
        parts.append(f"{stmt.target} = {text}" if stmt.target else text)
    return "; ".join(parts)


def canonicalize(source: str) -> str:
    return to_source(parse(source))
