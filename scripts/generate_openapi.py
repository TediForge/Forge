"""Generate or verify the committed OpenAPI schema."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "docs" / "openapi.json"
sys.path.insert(0, str(ROOT / "src"))

from orchestrator.api import app


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if the committed schema is stale")
    mode.add_argument("--write", action="store_true", help="write the generated schema")
    args = parser.parse_args()

    generated = json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not SCHEMA_PATH.is_file() or SCHEMA_PATH.read_text(encoding="utf-8") != generated:
            print("docs/openapi.json is stale; run python scripts/generate_openapi.py --write")
            return 1
        print("docs/openapi.json matches the generated API schema")
        return 0

    SCHEMA_PATH.write_text(generated, encoding="utf-8", newline="\n")
    print(f"Wrote {SCHEMA_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
