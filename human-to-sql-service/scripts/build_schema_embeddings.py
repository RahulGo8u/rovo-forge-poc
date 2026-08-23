"""Build the vector half of the schema index.

Embeds one document per table (name plus column names) with Gemini and writes
schema/<env>/<server>/<db>/embeddings.json. Retrieval works without this file,
using BM25 alone; running it upgrades retrieval to hybrid.

Usage:
    python scripts/build_schema_embeddings.py
    python scripts/build_schema_embeddings.py --batch-size 50
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.services import gemini  # noqa: E402
from app.services.planner import load_schema_pack  # noqa: E402
from app.services.schema_index import document_text, load_index  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", default="test")
    parser.add_argument("--server", default="db01")
    parser.add_argument("--database", default="DB7222")
    parser.add_argument("--batch-size", type=int, default=50)
    args = parser.parse_args()

    if not gemini.is_configured():
        raise SystemExit(
            "GEMINI_API_KEY is not set. Add it to human-to-sql-service/.env first."
        )

    pack = load_schema_pack(args.environment, args.server, args.database)
    index = load_index(args.environment, args.server, args.database)
    names = sorted(index.documents)
    print(f"Embedding {len(names)} tables with {settings.gemini_embedding_model}")

    vectors: dict[str, list[float]] = {}
    for start in range(0, len(names), args.batch_size):
        batch = names[start : start + args.batch_size]
        texts = [document_text(index, name) for name in batch]
        for name, vector in zip(batch, gemini.embed_batch(texts)):
            vectors[name] = vector
        print(f"  {min(start + args.batch_size, len(names))}/{len(names)}")

    target = Path(pack["path"]) / "embeddings.json"
    target.write_text(
        json.dumps(
            {
                "model": settings.gemini_embedding_model,
                "dimensions": len(next(iter(vectors.values()))) if vectors else 0,
                "table_count": len(vectors),
                "vectors": vectors,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(vectors)} vectors to {target}")


if __name__ == "__main__":
    main()
