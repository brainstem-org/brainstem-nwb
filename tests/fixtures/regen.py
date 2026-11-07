"""
Regenerate the committed synthetic exports from tests/fixtures/scenarios.py:

    python tests/fixtures/regen.py

writes tests/fixtures/exports/<scenario>.json and examples/synthetic-ephys/brainstem-export.json.
A test checks the committed files equal the scenarios.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.fixtures.scenarios import SCENARIOS  # noqa: E402

EXPORTS = ROOT / "tests" / "fixtures" / "exports"
EXAMPLE = ROOT / "examples" / "synthetic-ephys" / "brainstem-export.json"


def dump(payload: dict) -> str:
    return json.dumps(payload, indent=1, ensure_ascii=False) + "\n"


def main() -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    for name, build in SCENARIOS.items():
        (EXPORTS / f"{name}.json").write_text(dump(build()), encoding="utf-8")
    EXAMPLE.parent.mkdir(parents=True, exist_ok=True)
    EXAMPLE.write_text(dump(SCENARIOS["ephys"]()), encoding="utf-8")
    print(f"wrote {len(SCENARIOS)} scenarios to {EXPORTS} and {EXAMPLE}")


if __name__ == "__main__":
    main()
