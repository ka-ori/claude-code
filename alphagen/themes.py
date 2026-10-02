"""Research themes (``alphagen/data/themes.json``)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache

from .catalog import DATA_DIR

THEMES_PATH = DATA_DIR / "themes.json"


@dataclass
class Theme:
    id: str
    name: str
    cluster: str
    hypothesis: str
    mechanism: str
    citations: list[str]
    horizon: str
    settings: dict
    seeds: list[str]
    cautions: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)

    def format(self) -> str:
        lines = [
            f"{self.id}: {self.name}  (cluster: {self.cluster}, horizon: {self.horizon})",
            f"  hypothesis: {self.hypothesis}",
            f"  mechanism:  {self.mechanism}",
            f"  sources:    {'; '.join(self.citations)}",
            "  settings:   " + ", ".join(f"{k}={v}" for k, v in self.settings.items()),
        ]
        lines += [f"  seed:       {s}" for s in self.seeds]
        lines += [f"  template:   {t}" for t in self.templates]
        lines += [f"  caution:    {c}" for c in self.cautions]
        return "\n".join(lines)


@lru_cache(maxsize=1)
def load_themes() -> dict[str, Theme]:
    data = json.loads(THEMES_PATH.read_text())
    return {t["id"]: Theme(**t) for t in data["themes"]}
