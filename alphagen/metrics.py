"""Performance math: BRAIN Fitness, submission thresholds, and multiple-testing hurdles.

All rates (returns, turnover, drawdown) are fractions: 0.12 means 12%.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from statistics import NormalDist

TURNOVER_FLOOR = 0.125  # Fitness never rewards turnover below 12.5%
HLZ_T_HURDLE = 3.0      # Harvey, Liu & Zhu (2016) t-stat hurdle for a new factor
DEFAULT_IS_YEARS = 5.0  # length of the BRAIN in-sample window used for t-stats; adjust if yours differs


def fitness(sharpe: float, returns: float, turnover: float) -> float:
    """BRAIN Fitness = Sharpe * sqrt(|Returns| / max(Turnover, 0.125))."""
    return sharpe * math.sqrt(abs(returns) / max(turnover, TURNOVER_FLOOR))


def max_turnover_for_fitness(target: float, sharpe: float, returns: float) -> float | None:
    """Highest turnover at which the same Sharpe and returns would reach `target` fitness.

    None means the target is out of reach by cutting turnover alone (the 12.5% floor binds).
    """
    if sharpe <= 0 or returns == 0 or target <= 0:
        return None
    needed = sharpe * sharpe * abs(returns) / (target * target)
    return needed if needed >= TURNOVER_FLOOR else None


def t_stat(sharpe: float, years: float = DEFAULT_IS_YEARS) -> float:
    """t-statistic of mean returns implied by an annualized Sharpe over `years`."""
    return sharpe * math.sqrt(years)


def required_t(n_trials: int, alpha: float = 0.05, floor: float = HLZ_T_HURDLE) -> float:
    """Bonferroni-adjusted two-sided t hurdle for `n_trials` tests, never below the HLZ floor."""
    n = max(1, n_trials)
    bonferroni = NormalDist().inv_cdf(1 - alpha / (2 * n))
    return max(floor, bonferroni)


def haircut_sharpe(sharpe: float, n_trials: int, years: float = DEFAULT_IS_YEARS) -> float:
    """Sharpe after a Bonferroni haircut for the number of alphas tried (Harvey & Liu 2015 style)."""
    t = abs(t_stat(sharpe, years))
    p = 2 * (1 - NormalDist().cdf(t))
    p_adj = min(1.0, p * max(1, n_trials))
    if p_adj >= 1.0:
        return 0.0
    t_adj = NormalDist().inv_cdf(1 - p_adj / 2)
    return math.copysign(t_adj / math.sqrt(years), sharpe)


@dataclass(frozen=True)
class SubmissionCriteria:
    """Default BRAIN in-sample submission thresholds. The checks shown on the website are authoritative."""

    min_sharpe: float = 1.25
    min_fitness: float = 1.0
    min_turnover: float = 0.01
    max_turnover: float = 0.70
    max_self_correlation: float = 0.70

    @classmethod
    def for_delay(cls, delay: int) -> "SubmissionCriteria":
        if delay == 0:
            return cls(min_sharpe=2.0, min_fitness=1.3)
        return cls()


@dataclass
class Check:
    name: str
    passed: bool
    value: float | None
    limit: str

    def __str__(self) -> str:
        mark = "PASS" if self.passed else "FAIL"
        value = "n/a" if self.value is None else f"{self.value:.4g}"
        return f"{mark:4}  {self.name:<18} {value:>8}  (needs {self.limit})"


def evaluate(result: dict, criteria: SubmissionCriteria) -> list[Check]:
    checks = []
    sharpe = result.get("sharpe")
    if sharpe is not None:
        checks.append(Check("sharpe", sharpe >= criteria.min_sharpe, sharpe, f">= {criteria.min_sharpe}"))
    fit = result.get("fitness")
    if fit is not None:
        checks.append(Check("fitness", fit >= criteria.min_fitness, fit, f">= {criteria.min_fitness}"))
    turnover = result.get("turnover")
    if turnover is not None:
        checks.append(Check("turnover_min", turnover >= criteria.min_turnover, turnover, f">= {criteria.min_turnover:.0%}"))
        checks.append(Check("turnover_max", turnover <= criteria.max_turnover, turnover, f"<= {criteria.max_turnover:.0%}"))
    corr = result.get("self_corr")
    if corr is not None:
        checks.append(Check("self_correlation", corr < criteria.max_self_correlation, corr,
                            f"< {criteria.max_self_correlation}"))
    for name in result.get("failed_checks", []):
        checks.append(Check(name.lower(), False, None, "reported failed on BRAIN"))
    return checks


def parse_rate(value: str | float | None) -> float | None:
    """Parse '32.1%', '0.321' or 32.1 into a fraction. Bare numbers above 1.5 are read as percents."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number / 100 if abs(number) > 1.5 else number
    text = str(value).strip().replace(",", "")
    is_percent = text.endswith("%")
    number = float(text.rstrip("%").strip())
    if is_percent or abs(number) > 1.5:
        return number / 100
    return number


def parse_number(value: str | float | None) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = re.sub(r"[^\d.\-eE+]", "", str(value))
    return float(text) if text else None
