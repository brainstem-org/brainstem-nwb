"""The mapping specification, warning codes and schemas stay complete and in sync with the code."""

import ast
import json
from pathlib import Path

from brainstem_nwb.manifest.schema import SCHEMA_FILES
from brainstem_nwb.manifest.warnings import CODES
from brainstem_nwb.mapping.docs import render_mapping_spec, render_warnings
from brainstem_nwb.mapping.registry import MANIFEST_ONLY, RULES, STRUCTURAL, _load_mappers, field_policy
from brainstem_nwb.store.inventory import get_inventory

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "brainstem_nwb"


def test_the_server_describes_every_exported_record_type():
    inventory = get_inventory()
    assert [label for label in inventory.export_labels if label not in inventory.labels] == []


def test_every_exported_field_is_accounted_for():
    """Fails when the server's data model gains a field: map it, or say why it is not."""
    inventory = get_inventory()
    unaccounted = [
        f"{label}.{field}"
        for label in inventory.export_labels
        for field in inventory.fields(label)
        if field_policy(label, field) == "unaccounted"
    ]
    assert unaccounted == [], "map these fields, mark them STRUCTURAL, or add them to MANIFEST_ONLY with a reason"


def test_rule_sources_name_real_fields():
    _load_mappers()
    inventory = get_inventory()
    for rule in RULES.values():
        for source in rule.sources:
            label, _, field = source.rpartition(".")
            if label in inventory.export_labels:
                assert field in inventory.fields(label), f"rule {rule.id}: {source} is not a field"


def test_policy_tables_name_real_fields():
    inventory = get_inventory()
    for table in (STRUCTURAL, MANIFEST_ONLY):
        for label, fields in table.items():
            assert label in inventory.export_labels, label
            for field in fields:
                assert field == "*" or field in inventory.fields(label), f"{label}.{field}"


def test_every_warning_code_used_is_registered():
    used = set()
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", None)) in (
                    "warn", "make_warning") and node.args and isinstance(node.args[0], ast.Constant):
                used.add(node.args[0].value)
    assert used, "no warning calls found"
    assert used - set(CODES) == set()


def test_generated_docs_are_current():
    assert (ROOT / "docs" / "mapping-spec.md").read_text(encoding="utf-8") == render_mapping_spec(), \
        "regenerate: brainstem-nwb mapping > docs/mapping-spec.md"
    assert (ROOT / "docs" / "warnings.md").read_text(encoding="utf-8") == render_warnings(), \
        "regenerate: brainstem-nwb mapping --warnings > docs/warnings.md"


def test_committed_schemas_are_current():
    for name, build in SCHEMA_FILES.items():
        committed = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert committed == build(), f"regenerate schemas/{name} (python scripts/generate_docs.py)"
