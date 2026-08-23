from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed.json"


@lru_cache
def load_seed() -> dict[str, Any]:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))
