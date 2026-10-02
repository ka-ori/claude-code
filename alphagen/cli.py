"""Command line: ``python -m alphagen <command>``. Run with no arguments for help."""

from __future__ import annotations

import argparse
import json
import re
import sys

from . import metrics
from .catalog import Field, default_catalog
from .diagnose import diagnose
from .fastexpr.mutate import crossover_valid, mutate
from .fastexpr.operators import default_registry
from .fastexpr.validator import Validator
from .journal import STATUSES, Entry, Journal
from .settings import NEUTRALIZATIONS, SimulationSettings
from .similarity import nearest
from .themes import load_themes

SIMILARITY_WARN = 0.6


def _add_settings_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("simulation settings (default: theme preset, else USA TOP3000 D1)")
    group.add_argument("--region")
    group.add_argument("--universe")
    group.add_argument("--delay", type=int)
    group.add_argument("--decay", type=int)
    group.add_argument("--neutralization", type=str.upper, choices=NEUTRALIZATIONS)
    group.add_argument("--truncation", type=float)


def _settings_from(args, theme_id: str | None = None, base: SimulationSettings | None = None) -> SimulationSettings:
    settings = base or SimulationSettings()
    theme = load_themes().get(theme_id or "")
    if theme and base is None:
        settings = settings.with_(**theme.settings)
    return settings.with_(
        region=args.region, universe=args.universe, delay=args.delay, decay=args.decay,
        neutralization=args.neutralization, truncation=args.truncation,
    )


def _print_issues(result) -> None:
    for issue in result.issues:
        print(f"  {issue}")


# -- commands ---------------------------------------------------------------

def cmd_validate(args) -> int:
    validator = Validator(strict_fields=args.strict_fields, neutralization=args.neutralization, decay=args.decay)
    result = validator.validate(args.expression)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(result.format())
    return 0 if result.ok else 1


def cmd_propose(args) -> int:
    journal = Journal()
    settings = _settings_from(args, args.theme)
    validator = Validator(strict_fields=args.strict_fields, neutralization=settings.neutralization, decay=settings.decay)
    result = validator.validate(args.expression)
    if not result.ok:
        print(result.format())
        print("\nnot saved: fix the errors above first")
        return 1
    if args.theme and args.theme not in load_themes():
        print(f"note: theme '{args.theme}' is not in alphagen/data/themes.json (saved anyway)")

    duplicate = journal.find_duplicate(result.canonical, settings)
    if duplicate and not args.force:
        print(f"already in the journal as {duplicate.id} with the same settings:")
        print(f"  {duplicate.summary()}")
        return 1

    entry = journal.add(Entry(
        id=journal.next_id(),
        expression=result.canonical,
        settings=settings.to_dict(),
        theme=args.theme or "",
        hypothesis=args.hypothesis or "",
        origin=args.origin,
        parents=[p.upper() for p in args.parent or []],
    ))
    journal.save()

    print(f"{entry.id} saved (proposed)\n")
    print("Expression:")
    print(f"  {entry.expression}\n")
    print("Settings:")
    print("\n".join(f"  {line}" for line in settings.as_table().splitlines()))
    problems = settings.problems()
    if problems:
        print("\nSettings notes:")
        print("\n".join(f"  - {p}" for p in problems))
    if result.issues:
        print("\nValidator notes:")
        _print_issues(result)
    close = [(s, e) for s, e in nearest(entry.expression, settings.neutralization, journal.submitted())
             if s >= SIMILARITY_WARN]
    if close:
        print("\nStructurally similar to submitted alphas (self-correlation risk):")
        for score, other in close:
            print(f"  {score:.2f}  {other.id}  {other.expression}")
    return 0


_PASTE_PATTERNS = {
    "sharpe": r"sharpe",
    "turnover": r"turnover",
    "fitness": r"fitness",
    "returns": r"returns?",
    "drawdown": r"drawdown",
    "margin": r"margin",
    "self_corr": r"self[\s_-]*corr(?:elation)?",
}


def parse_pasted(text: str) -> dict:
    """Pull metrics out of text copied from the BRAIN results panel."""
    found = {}
    for key, label in _PASTE_PATTERNS.items():
        match = re.search(rf"\b{label}\b\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(%|‱)?", text, re.IGNORECASE)
        if match:
            number, unit = match.group(1), match.group(2) or ""
            found[key] = number + ("%" if unit == "%" else "")
    return found


def cmd_log(args) -> int:
    journal = Journal()
    entry = journal.get(args.id)
    raw = parse_pasted(args.text) if args.text else {}
    for key in ("sharpe", "fitness", "turnover", "returns", "drawdown", "margin", "self_corr"):
        value = getattr(args, key)
        if value is not None:
            raw[key] = value

    result = {
        "sharpe": metrics.parse_number(raw.get("sharpe")),
        "fitness": metrics.parse_number(raw.get("fitness")),
        "turnover": metrics.parse_rate(raw.get("turnover")),
        "returns": metrics.parse_rate(raw.get("returns")),
        "drawdown": metrics.parse_rate(raw.get("drawdown")),
        "margin_bps": metrics.parse_number(raw.get("margin")),
        "self_corr": metrics.parse_number(raw.get("self_corr")),
        "failed_checks": [c.upper() for c in args.fail or []],
    }
    if result["sharpe"] is None:
        print("need at least --sharpe (or --text with the pasted results)")
        return 1
    if args.settings_json:
        entry.settings = SimulationSettings.from_dict({**entry.settings, **json.loads(args.settings_json)}).to_dict()

    if None not in (result["sharpe"], result["returns"], result["turnover"]):
        implied = metrics.fitness(result["sharpe"], result["returns"], result["turnover"])
        if result["fitness"] is None:
            result["fitness"] = round(implied, 3)
            print(f"fitness not given; computed {implied:.2f} from Sharpe, returns and turnover")
        elif abs(implied - result["fitness"]) > 0.15 * max(1.0, abs(implied)):
            print(f"warning: pasted fitness {result['fitness']} differs from the implied {implied:.2f}; "
                  "check the turnover/returns units")

    journal.update_result(entry, result, brain_id=args.brain_id, notes=args.note)
    report = diagnose(entry, journal)
    entry.verdicts = report.verdicts
    journal.save()
    print(entry.summary())
    print(report.format())
    return 0


def cmd_rerun(args) -> int:
    journal = Journal()
    parent = journal.get(args.id)
    settings = _settings_from(args, base=parent.sim_settings)
    if settings == parent.sim_settings:
        print("give at least one changed setting, e.g. --decay 6")
        return 1
    duplicate = journal.find_duplicate(parent.expression, settings)
    if duplicate:
        print(f"already tried as {duplicate.id}: {duplicate.summary()}")
        return 1
    changed = {k: v for k, v in settings.to_dict().items() if parent.settings.get(k) != v}
    entry = journal.add(Entry(
        id=journal.next_id(),
        expression=parent.expression,
        settings=settings.to_dict(),
        theme=parent.theme,
        hypothesis=parent.hypothesis,
        origin="settings",
        parents=[parent.id],
        notes="re-run of {} with {}".format(parent.id, ", ".join(f"{k}={v}" for k, v in changed.items())),
    ))
    journal.save()
    print(f"{entry.id} saved (proposed): {parent.id} with " + ", ".join(f"{k}={v}" for k, v in changed.items()))
    print(f"\nExpression:\n  {entry.expression}\n\nSettings:")
    print("\n".join(f"  {line}" for line in settings.as_table().splitlines()))
    return 0


def cmd_diagnose(args) -> int:
    journal = Journal()
    entry = journal.get(args.id)
    print(entry.summary())
    print(diagnose(entry, journal).format())
    return 0


def cmd_show(args) -> int:
    entry = Journal().get(args.id)
    for key, value in vars(entry).items():
        if value not in ("", [], {}, None):
            print(f"{key:<11} {json.dumps(value) if isinstance(value, (dict, list)) else value}")
    return 0


def cmd_list(args) -> int:
    journal = Journal()
    rows = journal.entries
    if args.status:
        rows = [e for e in rows if e.status == args.status]
    if args.theme:
        rows = [e for e in rows if e.theme == args.theme]
    for entry in rows[-args.limit:]:
        print(entry.summary())
    if not rows:
        print("journal is empty" if not journal.entries else "no matching entries")
    return 0


def cmd_top(args) -> int:
    for entry in Journal().top(args.n, key=args.by, theme=args.theme):
        print(entry.summary())
    return 0


def cmd_status(args) -> int:
    journal = Journal()
    entry = journal.get(args.id)
    journal.set_status(entry, args.status)
    journal.save()
    print(entry.summary())
    return 0


def cmd_stats(args) -> int:
    journal = Journal()
    simulated = journal.simulated()
    total = len(simulated)
    print(f"journal: {len(journal.entries)} alphas, {total} simulated, {len(journal.submitted())} submitted")
    if not total:
        return 0
    criteria = metrics.SubmissionCriteria()
    by_theme: dict[str, list[Entry]] = {}
    for entry in simulated:
        by_theme.setdefault(entry.theme or "(none)", []).append(entry)
    print(f"\n{'theme':<26}{'tried':>6}{'pass':>6}{'best S':>8}{'best F':>8}")
    for theme, rows in sorted(by_theme.items(), key=lambda kv: -len(kv[1])):
        passes = sum(
            1 for e in rows
            if all(c.passed for c in metrics.evaluate(e.result, metrics.SubmissionCriteria.for_delay(e.sim_settings.delay)))
        )
        best_s = max(e.result["sharpe"] for e in rows)
        best_f = max((e.result.get("fitness") or float("-inf")) for e in rows)
        print(f"{theme:<26}{len(rows):>6}{passes:>6}{best_s:>8.2f}{best_f:>8.2f}")
    hurdle = metrics.required_t(total)
    print(f"\nmultiple-testing hurdle after {total} trials: t >= {hurdle:.2f} "
          f"(Sharpe >= {hurdle / metrics.DEFAULT_IS_YEARS ** 0.5:.2f} over {metrics.DEFAULT_IS_YEARS:g}y in-sample)")
    print(f"platform bar: Sharpe >= {criteria.min_sharpe}, Fitness >= {criteria.min_fitness}")
    return 0


def cmd_similar(args) -> int:
    journal = Journal()
    pool = journal.submitted() if args.submitted else journal.simulated()
    matches = nearest(args.expression, args.neutralization or "", pool, top=args.n)
    if not matches:
        print("nothing to compare against yet")
    for score, entry in matches:
        flag = "  <-- high" if score >= SIMILARITY_WARN else ""
        print(f"{score:.2f}  {entry.summary()}{flag}")
    return 0


def _expression_or_id(value: str) -> str:
    if re.fullmatch(r"[Aa]\d{4,}", value):
        return Journal().get(value).expression
    return value


def cmd_mutate(args) -> int:
    variants = mutate(_expression_or_id(args.expression), kinds=set(args.kind) if args.kind else None)
    for v in variants:
        print(f"[{v.kind}] {v.description}\n    {v.expression}")
    if not variants:
        print("no valid variants")
    return 0


def cmd_crossover(args) -> int:
    for v in crossover_valid(_expression_or_id(args.a), _expression_or_id(args.b)):
        print(f"[{v.kind}] {v.description}\n    {v.expression}")
    return 0


def cmd_fitness(args) -> int:
    returns = metrics.parse_rate(args.returns)
    turnover = metrics.parse_rate(args.turnover)
    value = metrics.fitness(args.sharpe, returns, turnover)
    print(f"fitness = {args.sharpe} * sqrt({returns:.4f} / max({turnover:.4f}, 0.125)) = {value:.3f}")
    ceiling = metrics.max_turnover_for_fitness(args.target, args.sharpe, returns)
    if ceiling is None:
        print(f"fitness {args.target} is out of reach by lowering turnover alone")
    else:
        print(f"fitness {args.target} needs turnover <= {ceiling:.1%} at this Sharpe and returns")
    return 0


def cmd_themes(args) -> int:
    themes = load_themes()
    if args.id:
        print(themes[args.id].format())
        return 0
    for theme in themes.values():
        print(f"{theme.id:<26}{theme.cluster:<22}{theme.name}")
    return 0


def cmd_operators(args) -> int:
    registry = default_registry()
    if args.name:
        op = registry.get(args.name)
        if not op:
            print(f"unknown operator {args.name}")
            return 1
        print(f"{op.signature}  [{op.category}] -> {op.returns}\n  {op.doc}")
        return 0
    for category, ops in registry.by_category().items():
        if args.category and category != args.category:
            continue
        print(f"\n{category}")
        for op in sorted(ops, key=lambda o: o.name):
            print(f"  {op.signature:<70} {op.doc}")
    return 0


def cmd_fields(args) -> int:
    catalog = default_catalog()
    if args.action == "add":
        catalog.add(Field(id=args.id, kind=args.kind, category=args.category, dataset=args.dataset or "",
                          scale=args.scale, description=args.description or ""), overwrite=args.overwrite)
        catalog.save()
        print(f"added {args.id} ({args.kind}, {args.category})")
        return 0
    rows = catalog.search(args.query) if args.action == "search" else sorted(catalog, key=lambda f: (f.category, f.id))
    for f in rows:
        print(f"{f.id:<22}{f.kind:<8}{f.category:<14}{f.dataset:<14}{f.description}")
    return 0


# -- parser -----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="alphagen", description="WorldQuant BRAIN alpha research toolkit")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("validate", help="check a Fast Expression before simulating it")
    p.add_argument("expression")
    p.add_argument("--neutralization", type=str.upper)
    p.add_argument("--decay", type=int)
    p.add_argument("--strict-fields", action="store_true", help="unknown fields are errors")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("propose", help="validate and save an alpha to the journal, print what to paste into BRAIN")
    p.add_argument("expression")
    p.add_argument("--theme")
    p.add_argument("--hypothesis")
    p.add_argument("--origin", default="claude")
    p.add_argument("--parent", action="append")
    p.add_argument("--strict-fields", action="store_true")
    p.add_argument("--force", action="store_true", help="save even if an identical entry exists")
    _add_settings_args(p)
    p.set_defaults(func=cmd_propose)

    p = sub.add_parser("log", help="record BRAIN results for a journal entry and diagnose them")
    p.add_argument("id")
    p.add_argument("--text", help="results text copied from BRAIN")
    p.add_argument("--sharpe")
    p.add_argument("--fitness")
    p.add_argument("--turnover", help="e.g. 34.5%% or 0.345")
    p.add_argument("--returns", help="e.g. 9.1%% or 0.091")
    p.add_argument("--drawdown")
    p.add_argument("--margin", help="in basis points (‱) as shown on BRAIN")
    p.add_argument("--self-corr", dest="self_corr")
    p.add_argument("--fail", action="append", help="name of a failed BRAIN check (repeatable)")
    p.add_argument("--brain-id")
    p.add_argument("--note")
    p.add_argument("--settings-json", help='settings actually used if they differ, e.g. \'{"decay": 6}\'')
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("rerun", help="new journal entry: same expression, changed settings")
    p.add_argument("id")
    _add_settings_args(p)
    p.set_defaults(func=cmd_rerun)

    for name, func, help_text in (("diagnose", cmd_diagnose, "re-run the diagnosis for an entry"),
                                  ("show", cmd_show, "show a journal entry")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("id")
        p.set_defaults(func=func)

    p = sub.add_parser("list", help="list journal entries")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--theme")
    p.add_argument("--limit", type=int, default=30)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("top", help="best simulated alphas")
    p.add_argument("--n", type=int, default=10)
    p.add_argument("--by", default="fitness", choices=["fitness", "sharpe", "returns"])
    p.add_argument("--theme")
    p.set_defaults(func=cmd_top)

    p = sub.add_parser("status", help="set an entry's status (e.g. after submitting on BRAIN)")
    p.add_argument("id")
    p.add_argument("status", choices=STATUSES)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("stats", help="per-theme summary and multiple-testing hurdle")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("similar", help="structural similarity against the journal (self-correlation early warning)")
    p.add_argument("expression")
    p.add_argument("--neutralization", type=str.upper)
    p.add_argument("--submitted", action="store_true", help="compare only against submitted alphas")
    p.add_argument("--n", type=int, default=5)
    p.set_defaults(func=cmd_similar)

    p = sub.add_parser("mutate", help="validated mechanical variants of an expression or journal ID")
    p.add_argument("expression")
    p.add_argument("--kind", action="append",
                   help="lookback, horizon_shift, normalizer_swap, group_change, group_neutralize, "
                        "volume_event_gate, turbulent_regime_gate, calm_regime_gate, decay_wrap, sign_flip")
    p.set_defaults(func=cmd_mutate)

    p = sub.add_parser("crossover", help="combine two expressions or journal IDs")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(func=cmd_crossover)

    p = sub.add_parser("fitness", help="fitness calculator")
    p.add_argument("--sharpe", type=float, required=True)
    p.add_argument("--returns", required=True)
    p.add_argument("--turnover", required=True)
    p.add_argument("--target", type=float, default=1.0)
    p.set_defaults(func=cmd_fitness)

    p = sub.add_parser("themes", help="list research themes or show one")
    p.add_argument("id", nargs="?")
    p.set_defaults(func=cmd_themes)

    p = sub.add_parser("operators", help="operator reference")
    p.add_argument("name", nargs="?")
    p.add_argument("--category")
    p.set_defaults(func=cmd_operators)

    p = sub.add_parser("fields", help="local data-field dictionary")
    fsub = p.add_subparsers(dest="action", required=True)
    fsub.add_parser("list")
    fs = fsub.add_parser("search")
    fs.add_argument("query")
    fa = fsub.add_parser("add")
    fa.add_argument("id")
    fa.add_argument("--kind", default="matrix", choices=["matrix", "vector", "group"])
    fa.add_argument("--category", default="other")
    fa.add_argument("--dataset")
    fa.add_argument("--scale", choices=["level", "ratio"])
    fa.add_argument("--description")
    fa.add_argument("--overwrite", action="store_true")
    p.set_defaults(func=cmd_fields)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyError as exc:
        print(exc.args[0] if exc.args else exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
