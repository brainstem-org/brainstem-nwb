"""
Regenerate the files derived from the code: docs/mapping-spec.md, docs/warnings.md and the JSON
Schemas in schemas/. Tests fail when they are out of date.

    python scripts/generate_docs.py
"""

import json
from pathlib import Path

from brainstem_nwb.manifest.schema import SCHEMA_FILES
from brainstem_nwb.mapping.docs import render_mapping_spec, render_warnings

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    (ROOT / "docs" / "mapping-spec.md").write_text(render_mapping_spec(), encoding="utf-8")
    (ROOT / "docs" / "warnings.md").write_text(render_warnings(), encoding="utf-8")
    for name, build in SCHEMA_FILES.items():
        (ROOT / "schemas" / name).write_text(json.dumps(build(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("regenerated docs/mapping-spec.md, docs/warnings.md and schemas/")


if __name__ == "__main__":
    main()
