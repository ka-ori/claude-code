"""Turn pasted BRAIN results into a verdict and concrete next simulations."""

from __future__ import annotations

from dataclasses import dataclass, field

from .fastexpr.mutate import Variant, crossover_valid, mutate
from .journal import Entry, Journal
from .metrics import (
    DEFAULT_IS_YEARS,
    TURNOVER_FLOOR,
    Check,
    SubmissionCriteria,
    evaluate,
    haircut_sharpe,
    max_turnover_for_fitness,
    required_t,
    t_stat,
)
from .settings import NEUTRALIZATIONS, next_decay

# Ordered decorrelation pivots; see knowledge/correlation-playbook.md.
DECORRELATION_KINDS = ("volume_event_gate", "turbulent_regime_gate", "calm_regime_gate",
                       "normalizer_swap", "group_change", "horizon_shift")


@dataclass
class Action:
    kind: str
    title: str
    detail: str = ""
    expression: str | None = None
    settings: dict = field(default_factory=dict)

    def format(self, index: int) -> str:
        lines = [f"{index}. [{self.kind}] {self.title}"]
        if self.detail:
            lines.append(f"   {self.detail}")
        if self.expression:
            lines.append(f"   expression: {self.expression}")
        if self.settings:
            lines.append("   settings: " + ", ".join(f"{k}={v}" for k, v in self.settings.items()))
        return "\n".join(lines)


@dataclass
class Diagnosis:
    verdicts: list[str]
    checks: list[Check]
    actions: list[Action]
    lessons: list[str]
    stats: dict

    def format(self) -> str:
        lines = ["verdict: " + ", ".join(self.verdicts)]
        lines += [f"  {c}" for c in self.checks]
        if self.stats:
            lines.append("  " + "  ".join(f"{k}={v}" for k, v in self.stats.items()))
        if self.actions:
            lines.append("next steps:")
            lines += [a.format(i) for i, a in enumerate(self.actions, 1)]
        if self.lessons:
            lines.append("lesson candidates (add to journal/LESSONS.md if they generalize):")
            lines += [f"  - {lesson}" for lesson in self.lessons]
        return "\n".join(lines)


def _variant_action(variant: Variant, kind: str) -> Action:
    return Action(kind, variant.description, expression=variant.expression)


def diagnose(entry: Entry, journal: Journal, years: float = DEFAULT_IS_YEARS) -> Diagnosis:
    settings = entry.sim_settings
    criteria = SubmissionCriteria.for_delay(settings.delay)
    r = entry.result
    checks = evaluate(r, criteria)
    verdicts: list[str] = []
    actions: list[Action] = []
    lessons: list[str] = []
    stats: dict = {}

    sharpe = r.get("sharpe")
    if sharpe is None:
        return Diagnosis(["NO_RESULT"], checks, [Action("log", "paste the BRAIN results first")], [], {})

    fit = r.get("fitness")
    turnover = r.get("turnover")
    returns = r.get("returns")
    corr = r.get("self_corr")
    failed = {name.upper() for name in r.get("failed_checks", [])}
    family = journal.lineage(entry)
    tried_decays = {e.sim_settings.decay for e in family if e.expression == entry.expression}
    tried_neuts = {e.sim_settings.neutralization.upper() for e in family if e.expression == entry.expression}

    trials = max(1, journal.trials())
    t = t_stat(sharpe, years)
    hurdle = required_t(trials)
    stats.update({
        "t_stat": round(t, 2),
        "t_hurdle": round(hurdle, 2),
        "trials_so_far": trials,
        "haircut_sharpe": round(haircut_sharpe(sharpe, trials, years), 2),
    })

    # 1. Inverted signal
    if sharpe <= -0.8 * criteria.min_sharpe:
        verdicts.append("INVERTED")
        flip = mutate(entry.expression, kinds={"sign_flip"})
        if flip:
            actions.append(Action("flip", "the signal works in reverse: flip the sign",
                                  "only keep it if the reversed story makes economic sense; it counts as another trial",
                                  expression=flip[0].expression))
        lessons.append(f"{entry.theme or 'this idea'}: `{entry.expression}` had Sharpe {sharpe:.2f} (inverted)")
        return Diagnosis(verdicts, checks, actions, lessons, stats)

    strong = sharpe >= 0.9 * criteria.min_sharpe

    # 2. Turnover problems
    too_fast = turnover is not None and turnover > criteria.max_turnover
    turnover_drags_fitness = (
        strong and fit is not None and fit < criteria.min_fitness
        and turnover is not None and turnover > TURNOVER_FLOOR * 1.2
    )
    if too_fast or turnover_drags_fitness:
        verdicts.append("HIGH_TURNOVER")
        ceiling = max_turnover_for_fitness(criteria.min_fitness, sharpe, returns) if returns is not None else None
        target = 0.8 * min(criteria.max_turnover, ceiling or criteria.max_turnover)
        ratio = (turnover or 0) / target if target else 1
        jumps = 1 if ratio < 1.5 else 2 if ratio < 2.5 else 3
        step = settings.decay
        for _ in range(jumps):
            step = next_decay(step) if step is not None else None
        while step is not None and step in tried_decays:
            step = next_decay(step)
        if returns is not None:
            if ceiling is None:
                detail = ("even at 12.5% turnover this Sharpe/returns pair cannot reach the fitness bar; "
                          "decay alone will not fix it, the signal needs to be stronger")
            else:
                detail = (f"fitness {criteria.min_fitness} needs turnover <= {ceiling:.0%} at the current Sharpe and returns "
                          "(decay usually costs some Sharpe, so aim lower)")
        else:
            detail = "decay smooths positions and cuts turnover"
        if step is not None:
            actions.append(Action("decay", f"re-run with Decay {step}", detail, settings={"decay": step}))
        # For fast signals (reversal), cutting turnover often costs more Sharpe than it saves;
        # raising returns with magnitude-weighted positions (rank -> zscore) can work better.
        for variant in mutate(entry.expression, kinds={"normalizer_swap"}):
            if "zscore" in variant.description.split("->")[-1]:
                actions.append(Action("concentrate", f"{variant.description}: raise returns instead of cutting turnover",
                                      "Fitness = Sharpe^1.5 * sqrt(vol / turnover); a magnitude-weighted signal raises vol",
                                      expression=variant.expression))
        for variant in mutate(entry.expression, kinds={"volume_event_gate", "decay_wrap"}):
            actions.append(_variant_action(variant, "smooth"))
        lessons.append(f"{entry.theme or 'signal'} at decay {settings.decay} had turnover {turnover:.0%}"
                       if turnover is not None else "high turnover")
    elif turnover is not None and turnover < criteria.min_turnover:
        verdicts.append("LOW_TURNOVER")
        lower = max((d for d in (0, 2, 4, 6, 8, 10) if d < settings.decay), default=None)
        if lower is not None:
            actions.append(Action("decay", f"re-run with Decay {lower}", settings={"decay": lower}))
        for variant in mutate(entry.expression, kinds={"lookback"})[:2]:
            actions.append(_variant_action(variant, "faster"))

    # 3. Weak or near-miss signal
    if 0 < sharpe < criteria.min_sharpe and "HIGH_TURNOVER" not in verdicts:
        if sharpe >= 0.7 * criteria.min_sharpe:
            verdicts.append("NEAR_MISS")
            for neut in ("SUBINDUSTRY", "INDUSTRY", "SECTOR", "MARKET"):
                if neut not in tried_neuts and neut in NEUTRALIZATIONS:
                    actions.append(Action("neutralization", f"re-run with Neutralization {neut.title()}",
                                          settings={"neutralization": neut}))
                    break
            for variant in mutate(entry.expression, kinds={"group_change", "group_neutralize", "lookback"})[:3]:
                actions.append(_variant_action(variant, "refine"))
            partners = [e for e in journal.top(5) if e.id != entry.id and e.theme != entry.theme]
            if partners:
                for variant in crossover_valid(entry.expression, partners[0].expression)[:1]:
                    actions.append(Action("crossover", f"{variant.description} with {partners[0].id}",
                                          expression=variant.expression))
        else:
            verdicts.append("WEAK")
            actions.append(Action("drop", "move on: the hypothesis shows little edge in this setup",
                                  "try a different dataset or universe for the same theme, or a new theme"))
            lessons.append(f"{entry.theme or 'idea'}: `{entry.expression}` weak (Sharpe {sharpe:.2f}) "
                           f"in {settings.universe} {settings.neutralization}")
    elif sharpe <= 0 and "INVERTED" not in verdicts:
        verdicts.append("WEAK")
        actions.append(Action("drop", "no edge: drop it or rethink the hypothesis"))

    # 4. Low fitness with acceptable turnover: returns too small for the trading
    if strong and fit is not None and fit < criteria.min_fitness and "HIGH_TURNOVER" not in verdicts:
        verdicts.append("LOW_RETURNS")
        actions.append(Action("strengthen", "returns are too small for the trading it does",
                              "try a smaller, more liquid universe (TOP1000/TOP500), a coarser neutralization, "
                              "or combine with a complementary signal"))

    # 5. Self-correlation
    if (corr is not None and corr >= criteria.max_self_correlation) or "SELF_CORRELATION" in failed:
        verdicts.append("SELF_CORRELATED")
        for variant in mutate(entry.expression, kinds=set(DECORRELATION_KINDS)):
            actions.append(_variant_action(variant, "decorrelate"))
        actions.append(Action("decorrelate", "same hypothesis, different dataset or horizon class",
                              "see knowledge/correlation-playbook.md; small parameter tweaks will not break correlation"))
        lessons.append(f"`{entry.expression}` correlated {corr:.2f} with the portfolio" if corr is not None
                       else f"`{entry.expression}` failed self-correlation")

    # 6. Other platform checks
    if any("CONCENTRAT" in name for name in failed):
        verdicts.append("CONCENTRATED")
        actions.append(Action("truncation", "lower Truncation to 0.05 and make sure the output is ranked",
                              settings={"truncation": 0.05}))
    if any("SUB_UNIVERSE" in name for name in failed):
        verdicts.append("SUB_UNIVERSE")
        actions.append(Action("universe", "edge lives in the less liquid names: test on TOP1000 and add a liquidity filter",
                              settings={"universe": "TOP1000"}))

    if all(c.passed for c in checks) and not verdicts:
        if t < hurdle:
            verdicts.append("PASS_UNPROVEN")
            actions.append(Action("caution", f"passes BRAIN, but t={t:.2f} is below the multiple-testing hurdle {hurdle:.2f}",
                                  "check it has an economic story and is not a lucky variant before submitting"))
        else:
            verdicts.append("PASS")
        if corr is None:
            actions.append(Action("submit", "run BRAIN's submission check (self-correlation) before submitting",
                                  "then record it: python -m alphagen status <ID> submitted"))
        else:
            actions.append(Action("submit", "submit on BRAIN, then: python -m alphagen status <ID> submitted"))

    if not verdicts:
        verdicts.append("REVIEW")
    return Diagnosis(verdicts, checks, actions, lessons, stats)
