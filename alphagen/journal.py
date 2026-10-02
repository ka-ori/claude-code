"""Research journal: every alpha proposed, its settings, and the results pasted back from BRAIN.

Stored as JSON Lines in ``journal/alphas.jsonl`` so it is easy to diff and survives
in git between sessions.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .settings import SimulationSettings

REPO_ROOT = Path(__file__).resolve().parent.parent
JOURNAL_PATH = Path(os.environ.get("ALPHAGEN_JOURNAL", REPO_ROOT / "journal" / "alphas.jsonl"))

STATUSES = ("proposed", "simulated", "submitted", "rejected")
RESULT_KEYS = ("sharpe", "fitness", "turnover", "returns", "drawdown", "margin_bps", "self_corr", "failed_checks")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Entry:
    id: str
    expression: str
    settings: dict
    theme: str = ""
    hypothesis: str = ""
    origin: str = "claude"  # claude | seed | user | mutation | crossover | decay | decorrelate | flip
    parents: list[str] = field(default_factory=list)
    status: str = "proposed"
    result: dict = field(default_factory=dict)
    verdicts: list[str] = field(default_factory=list)
    brain_id: str = ""
    notes: str = ""
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)

    @property
    def sim_settings(self) -> SimulationSettings:
        return SimulationSettings.from_dict(self.settings)

    @property
    def has_result(self) -> bool:
        return self.result.get("sharpe") is not None

    def summary(self) -> str:
        r = self.result
        if self.has_result:
            parts = [f"S={r['sharpe']:.2f}"]
            if r.get("fitness") is not None:
                parts.append(f"F={r['fitness']:.2f}")
            if r.get("turnover") is not None:
                parts.append(f"T={r['turnover']:.0%}")
            if r.get("self_corr") is not None:
                parts.append(f"corr={r['self_corr']:.2f}")
            metrics = " ".join(parts)
        else:
            metrics = "not simulated"
        theme = f"[{self.theme}] " if self.theme else ""
        return f"{self.id} {self.status:<9} {metrics:<34} {theme}{self.expression}"


class Journal:
    def __init__(self, path: Path = JOURNAL_PATH):
        self.path = Path(path)
        self.entries: list[Entry] = []
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                if line.strip():
                    self.entries.append(Entry(**json.loads(line)))

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".alphas-", suffix=".tmp")
        with os.fdopen(fd, "w") as handle:
            for entry in self.entries:
                handle.write(json.dumps(asdict(entry), sort_keys=True) + "\n")
        os.replace(tmp, self.path)

    def next_id(self) -> str:
        highest = max((int(e.id[1:]) for e in self.entries if e.id[1:].isdigit()), default=0)
        return f"A{highest + 1:04d}"

    def get(self, entry_id: str) -> Entry:
        key = entry_id.upper()
        for entry in self.entries:
            if entry.id == key:
                return entry
        raise KeyError(f"no journal entry {entry_id}")

    def find_duplicate(self, canonical: str, settings: SimulationSettings) -> Entry | None:
        for entry in self.entries:
            if entry.expression == canonical and entry.sim_settings == settings:
                return entry
        return None

    def add(self, entry: Entry) -> Entry:
        self.entries.append(entry)
        return entry

    def update_result(self, entry: Entry, result: dict, brain_id: str | None = None, notes: str | None = None) -> None:
        clean = {k: v for k, v in result.items() if k in RESULT_KEYS and v not in (None, [], "")}
        entry.result.update(clean)
        if entry.status == "proposed":
            entry.status = "simulated"
        if brain_id:
            entry.brain_id = brain_id
        if notes:
            entry.notes = f"{entry.notes}\n{notes}".strip()
        entry.updated = _now()

    def set_status(self, entry: Entry, status: str) -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        entry.status = status
        entry.updated = _now()

    # -- queries ------------------------------------------------------------

    def simulated(self) -> list[Entry]:
        return [e for e in self.entries if e.has_result]

    def submitted(self) -> list[Entry]:
        return [e for e in self.entries if e.status == "submitted"]

    def lineage(self, entry: Entry) -> list[Entry]:
        """The entry, its ancestors and all their descendants (one research thread)."""
        by_id = {e.id: e for e in self.entries}
        root = entry
        seen = set()
        while root.parents and root.parents[0] in by_id and root.id not in seen:
            seen.add(root.id)
            root = by_id[root.parents[0]]
        family = {root.id}
        changed = True
        while changed:
            changed = False
            for e in self.entries:
                if e.id not in family and any(p in family for p in e.parents):
                    family.add(e.id)
                    changed = True
        return [e for e in self.entries if e.id in family]

    def top(self, n: int = 10, key: str = "fitness", theme: str | None = None) -> list[Entry]:
        rows = [e for e in self.simulated() if e.result.get(key) is not None]
        if theme:
            rows = [e for e in rows if e.theme == theme]
        return sorted(rows, key=lambda e: e.result[key], reverse=True)[:n]

    def trials(self, theme: str | None = None) -> int:
        rows = self.simulated()
        return len([e for e in rows if e.theme == theme]) if theme else len(rows)
