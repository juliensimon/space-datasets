#!/usr/bin/env python3
"""Update status.json with the current date for a given dataset key."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATUS_FILE = Path(__file__).parent.parent / "status.json"

def main():
    if len(sys.argv) < 2:
        print("Usage: python update-status.py <key>", file=sys.stderr)
        sys.exit(1)
    key = sys.argv[1]
    rows = None
    if "--rows" in sys.argv:
        idx = sys.argv.index("--rows")
        raw = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
        rows = int(raw) if raw else None

    status = json.loads(STATUS_FILE.read_text()) if STATUS_FILE.exists() else {}
    status[key] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if rows is not None:
        status.setdefault("_rows", {})[key] = rows

    STATUS_FILE.write_text(json.dumps(status, indent=2) + "\n")
    print(f"Updated status[{key}] = {status[key]}"
          + (f" ({rows:,} rows)" if rows else ""))

if __name__ == "__main__":
    main()
