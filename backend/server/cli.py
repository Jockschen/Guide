from __future__ import annotations

import argparse
import json

from .db import connect, init_db
from .ingestion import rebuild_knowledge


def status() -> dict[str, int]:
    init_db()
    conn = connect()
    try:
        return {
            "sources": conn.execute("SELECT COUNT(*) FROM source_files").fetchone()[0],
            "attractions": conn.execute("SELECT COUNT(*) FROM attractions").fetchone()[0],
            "chunks": conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0],
            "faqs": conn.execute("SELECT COUNT(*) FROM faqs").fetchone()[0],
            "logs": conn.execute("SELECT COUNT(*) FROM qa_logs").fetchone()[0],
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Lingjing backend helper")
    parser.add_argument("command", choices=["rebuild", "status"])
    args = parser.parse_args()
    if args.command == "rebuild":
        result = rebuild_knowledge()
    else:
        result = status()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
