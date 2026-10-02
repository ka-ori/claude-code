"""Local data-field dictionary (``alphagen/data/fields.json``)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
FIELDS_PATH = DATA_DIR / "fields.json"
MATRIX, VECTOR, GROUP = "matrix", "vector", "group"
KINDS = (MATRIX, VECTOR, GROUP)


@dataclass
class Field:
    id: str
    kind: str = MATRIX
    category: str = "other"
    dataset: str = ""
    scale: str | None = None
    description: str = ""

    @property
    def is_level(self) -> bool:
        return self.scale == "level"


class Catalog:
    def __init__(self, fields: dict[str, Field], path: Path | None = None, about: str = ""):
        self._fields = fields
        self.path = path
        self.about = about

    @classmethod
    def load(cls, path: Path = FIELDS_PATH) -> "Catalog":
        data = json.loads(Path(path).read_text())
        fields = {f["id"]: Field(**f) for f in data["fields"]}
        return cls(fields, Path(path), data.get("_about", ""))

    def get(self, field_id: str) -> Field | None:
        return self._fields.get(field_id)

    def __contains__(self, field_id: str) -> bool:
        return field_id in self._fields

    def __iter__(self):
        return iter(self._fields.values())

    def __len__(self) -> int:
        return len(self._fields)

    def add(self, field: Field, overwrite: bool = False) -> None:
        if field.kind not in KINDS:
            raise ValueError(f"kind must be one of {KINDS}")
        if field.id in self._fields and not overwrite:
            raise ValueError(f"field {field.id!r} already exists (use --overwrite)")
        self._fields[field.id] = field

    def save(self) -> None:
        if self.path is None:
            raise ValueError("catalog has no backing file")
        rows = sorted(self._fields.values(), key=lambda f: (f.category, f.id))
        body = ",\n".join(f"    {json.dumps(asdict(f))}" for f in rows)
        self.path.write_text(f'{{\n  "_about": {json.dumps(self.about)},\n  "fields": [\n{body}\n  ]\n}}\n')

    def search(self, query: str, limit: int = 20) -> list[Field]:
        terms = [t for t in re.split(r"\W+", query.lower()) if t]
        scored = []
        for f in self._fields.values():
            haystack = f"{f.id} {f.category} {f.dataset} {f.description}".lower()
            score = sum(3 if t in f.id.lower() else 1 for t in terms if t in haystack)
            if score:
                scored.append((score, f.id, f))
        scored.sort(key=lambda item: (-item[0], item[1]))
        return [f for _, _, f in scored[:limit]]


@lru_cache(maxsize=1)
def default_catalog() -> Catalog:
    return Catalog.load()
