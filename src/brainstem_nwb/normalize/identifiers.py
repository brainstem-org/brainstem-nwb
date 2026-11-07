"""Ontology identifiers (species, RRIDs) and DANDI-safe labels for file names."""

from __future__ import annotations

import re
from typing import Any

NCBI_TAXON_IRI = "http://purl.obolibrary.org/obo/NCBITaxon_{}"

# BrainSTEM species records have used both "RRID:NCBITaxon_10090" and "RRID:NCBI_txid10090".
_RRID_TAXON = re.compile(r"^RRID:\s*(?:NCBITaxon_|NCBI_txid)(\d+)$", re.IGNORECASE)
_TAXON_URL = re.compile(r"NCBITaxon_(\d+)|[?&]id=(\d+)")


def ncbi_taxon_id(species_fields: dict[str, Any]) -> str | None:
    """
    The NCBI Taxonomy number of a species record, from ``external_identifiers`` or ``rrid``.

    Returns None when neither names one; the number is never looked up by species name.
    """
    for entry in species_fields.get("external_identifiers") or []:
        if not isinstance(entry, dict):
            continue
        source = str(entry.get("source") or "").upper()
        if source in {"NCBI", "NCBITAXON", "NCBI TAXONOMY"} and str(entry.get("id") or "").isdigit():
            return str(entry["id"])
        match = _TAXON_URL.search(str(entry.get("url") or ""))
        if source.startswith("NCBI") and match:
            return match.group(1) or match.group(2)
    match = _RRID_TAXON.match(str(species_fields.get("rrid") or "").strip())
    if match:
        return match.group(1)
    return None


def ncbi_taxon_iri(species_fields: dict[str, Any]) -> str | None:
    taxon = ncbi_taxon_id(species_fields)
    return NCBI_TAXON_IRI.format(taxon) if taxon else None


def normalize_rrid(value: Any) -> str | None:
    """``"RRID: IMSR_JAX:000664"`` -> ``"RRID:IMSR_JAX:000664"``; None for empty values."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if not text.upper().startswith("RRID:"):
        text = f"RRID:{text}"
    return "RRID:" + text[5:].strip()


def dandi_label(value: str) -> str:
    """
    A label usable in DANDI file names (``sub-<label>_ses-<label>``): letters, digits and ``-`` only.

    Runs of other characters become a single ``-``; leading and trailing ``-`` are dropped.
    """
    label = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return label or "unnamed"
