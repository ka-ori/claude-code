"""BRAIN simulation settings (the panel next to the expression editor)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace

NEUTRALIZATIONS = ("NONE", "MARKET", "SECTOR", "INDUSTRY", "SUBINDUSTRY")
UNIVERSES = {
    "USA": ("TOP3000", "TOP1000", "TOP500", "TOP200", "TOPSP500"),
}
DECAY_LADDER = (0, 2, 4, 6, 8, 10, 15, 20, 30)


@dataclass(frozen=True)
class SimulationSettings:
    region: str = "USA"
    universe: str = "TOP3000"
    delay: int = 1
    decay: int = 0
    neutralization: str = "SUBINDUSTRY"
    truncation: float = 0.08
    pasteurization: str = "ON"
    unit_handling: str = "VERIFY"
    nan_handling: str = "OFF"

    @classmethod
    def from_dict(cls, data: dict | None) -> "SimulationSettings":
        if not data:
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def to_dict(self) -> dict:
        return asdict(self)

    def with_(self, **changes) -> "SimulationSettings":
        changes = {k: v for k, v in changes.items() if v is not None}
        if "neutralization" in changes:
            changes["neutralization"] = changes["neutralization"].upper()
        return replace(self, **changes)

    def problems(self) -> list[str]:
        """Settings mistakes (errors) and risky choices (prefixed 'warning:')."""
        issues = []
        if self.delay not in (0, 1):
            issues.append("delay must be 0 or 1")
        elif self.delay == 0:
            issues.append("warning: delay 0 trades on same-day data; it needs much higher Sharpe to pass and is fragile")
        if self.decay < 0:
            issues.append("decay must be >= 0")
        if self.neutralization.upper() not in NEUTRALIZATIONS:
            issues.append(f"neutralization should be one of {', '.join(NEUTRALIZATIONS)}")
        elif self.neutralization.upper() == "NONE":
            issues.append("warning: no neutralization leaves market beta in the PnL")
        if not 0 < self.truncation <= 1:
            issues.append("truncation must be in (0, 1]")
        elif not 0.01 <= self.truncation <= 0.10:
            issues.append("warning: truncation outside 0.01-0.10 lets single names dominate or over-constrains weights")
        known = UNIVERSES.get(self.region.upper())
        if known and self.universe.upper() not in known:
            issues.append(f"warning: unusual universe {self.universe} for {self.region} (known: {', '.join(known)})")
        return issues

    def as_table(self) -> str:
        rows = [
            ("Region", self.region),
            ("Universe", self.universe),
            ("Delay", self.delay),
            ("Decay", self.decay),
            ("Neutralization", self.neutralization.title()),
            ("Truncation", self.truncation),
            ("Pasteurization", self.pasteurization.title()),
            ("Unit Handling", self.unit_handling.title()),
            ("NaN Handling", self.nan_handling.title()),
        ]
        width = max(len(k) for k, _ in rows)
        return "\n".join(f"{k.ljust(width)}  {v}" for k, v in rows)

    def short(self) -> str:
        return (f"{self.region}/{self.universe} D{self.delay} decay={self.decay} "
                f"neut={self.neutralization.upper()} trunc={self.truncation}")


def next_decay(current: int) -> int | None:
    for step in DECAY_LADDER:
        if step > current:
            return step
    return None
