from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@lru_cache
def load_seed() -> dict[str, Any]:
    seed = json.loads((DATA_DIR / "seed.json").read_text(encoding="utf-8"))
    extra_path = DATA_DIR / "seed_extra.json"
    if extra_path.exists():
        extra = json.loads(extra_path.read_text(encoding="utf-8"))
        seed.update(extra)
    return seed
