"""
Registry of warning codes. Every warning the exporter emits uses a code from here, so the
documentation (``docs/warnings.md``) lists all of them and tests can check none is undocumented.

Severity convention:

- ``error``: the unit cannot be produced, or the output would be wrong;
- ``warning``: information was lost, or a placeholder was used where BrainSTEM had nothing;
- ``info``: an expected gap (not in the export, kept in the manifest only).
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import ConversionWarning, Severity, SourcePointer


@dataclass(frozen=True)
class WarningCode:
    code: str
    severity: Severity
    description: str


_CODES = [
    # Export file and units
    WarningCode("EXPORT_MINOR_NEWER", "info",
                "The export is a newer minor format version than this release knows; unknown labels and "
                "fields are kept in the manifest and otherwise ignored."),
    WarningCode("UNKNOWN_LABEL", "info", "The export contains a record type this release does not know."),
    WarningCode("DATA_MODEL_CACHED", "warning",
                "The BrainSTEM server could not be reached, so the data model was read from the copy cached the "
                "last time it was; records changed on the server since then may be described incompletely."),
    WarningCode("DATA_MODEL_UNSUPPORTED", "warning",
                "The server's data model generation is not one this release was written for; fields it does not "
                "know are kept in the manifest, but links may be missed. Update brainstem-nwb."),
    WarningCode("SESSION_NOT_PERFORMED", "info",
                "The session is planned or cancelled, not performed; no NWB file is written for it."),
    WarningCode("PROCEDURE_NOT_PERFORMED", "info",
                "A procedure or specimen procedure is planned or cancelled, not performed; it is left out of the NWB "
                "file and kept in the manifest."),
    WarningCode("UNKNOWN_FIELD", "info",
                "A record has a field this release does not know; it is kept in the manifest."),
    WarningCode("SESSION_START_TIME_MISSING", "error",
                "The session has no date and time; NWB requires a session start time, so no file is written."),
    WarningCode("NO_SUBJECT", "error",
                "The session has no subject (or specimen set with a subject); run with --allow-no-subject to "
                "export it without one."),
    WarningCode("NO_SUBJECT_ALLOWED", "warning", "The session has no subject and was exported without an NWB Subject."),
    WarningCode("SUBJECT_NOT_IN_EXPORT", "error",
                "The session lists a subject that is not in this project's export (it belongs to another project)."),
    WarningCode("SUBJECTS_INFERRED", "warning",
                "The session lists no subjects; they were taken from its behaviors, procedures and interfaces."),
    WarningCode("MULTIPLE_SUBJECTS", "info", "The session has several subjects; one NWB file is written per subject."),
    WarningCode("RECORD_SHARED_ACROSS_SUBJECTS", "warning",
                "A record of a multi-subject session is not linked to any subject, so it is included in the "
                "file of every subject."),
    WarningCode("FILENAME_COLLISION", "warning",
                "Two units would get the same file name; a short BrainSTEM id was appended."),
    WarningCode("OUTPUT_EXISTS", "error",
                "A different NWB file already exists at the output path; use --overwrite to replace it."),
    WarningCode("UNIT_FAILED", "error", "Building or writing the unit failed; see the message."),
    # NWBFile
    WarningCode("SESSION_DESCRIPTION_MISSING", "warning",
                "The session has no description; a placeholder naming the session was written."),
    WarningCode("EXPERIMENTER_NOT_AVAILABLE", "info",
                "No experimenter: BrainSTEM sessions do not record who ran them and user names are not exported. "
                "Set nwbfile.experimenter in the configuration file."),
    WarningCode("LAB_NOT_AVAILABLE", "info",
                "No lab or institution: they are not in the export. Set nwbfile.lab and nwbfile.institution in "
                "the configuration file."),
    WarningCode("PUBLICATIONS_NOT_RESOLVED", "info",
                "The project has publications, but publication records are not in the export; their ids are in "
                "the manifest."),
    WarningCode("UNMAPPED_FIELDS", "info",
                "Some BrainSTEM fields have no NWB destination; they are kept in the manifest."),
    # Subject
    WarningCode("IDENTIFIER_SLASH_REPLACED", "warning",
                "A subject or session name contains '/', which breaks NWB and DANDI paths; it was replaced by '-' "
                "in subject_id or session_id (the original name is in the manifest)."),
    WarningCode("SUBJECT_SPECIES_MISSING", "warning", "The subject's species record is not in the export."),
    WarningCode("SUBJECT_SEX_UNKNOWN", "info", "The subject's sex is recorded as unknown; NWB sex is 'U'."),
    WarningCode("SUBJECT_AGE_UNKNOWN", "warning",
                "The subject has no birth date, so neither date_of_birth nor age is written."),
    WarningCode("SUBJECT_AGE_NEGATIVE", "error",
                "The subject's birth date is after the session start; age is not written."),
    WarningCode("SUBJECT_WEIGHT_NOT_IN_EXPORT", "info",
                "Subject weight comes from subject log entries, and this export has none for the subject (format 2.0 "
                "exports hold no log entries)."),
    WarningCode("SUBJECT_WEIGHT_UNKNOWN", "info",
                "The subject has no Weighing or Monitoring log entry with a weight at or before the session start."),
    WarningCode("SPECIES_IRI_UNAVAILABLE", "warning",
                "species_format is 'ncbitaxon' but the species record names no NCBI Taxonomy id; the "
                "binomial name was written."),
    # Procedures and materials
    WarningCode("PROCEDURE_DATE_UNKNOWN", "info",
                "A procedure of the subject has no date; it is treated as having happened before the session."),
    WarningCode("PROCEDURE_AFTER_SESSION", "info",
                "A procedure of the subject happened after the session; it is left out of the NWB file and kept "
                "in the manifest."),
    WarningCode("PROCEDURE_TYPE_UNCLASSIFIED", "warning",
                "A procedure type is not in this release's vocabulary; it is described in the notes."),
    WarningCode("REGION_NOT_RESOLVED", "info",
                "A target brain region is not recorded, or its region record is not in the export (format 2.0 exports "
                "hold no region records); the "
                "NWB location is 'unknown' and region ids are kept in the manifest."),
    WarningCode("RESTRICTED_LAB_RESOURCES", "info",
                "The records reference lab resources (equipment, setups, protocols, ...) the exporting user cannot "
                "read; only their names are exported, and they are named in the text fields and the manifest."),
    WarningCode("LEGACY_BARE_NUMBER", "warning",
                "A value saved under an older schema has no unit in the export; it is written as 'unit not recorded'."),
    # Devices
    WarningCode("DEVICE_MANUFACTURER_UNKNOWN", "info",
                "Supplier records are not in the export, so no NWB DeviceModel (which requires a manufacturer) "
                "is written; the hardware device name is in the Device description."),
    WarningCode("ELECTRODE_GROUP_LABELS_UNATTRIBUTABLE", "info",
                "The acquisition defines electrode groups but uses several electrophysiology interfaces, so the "
                "groups cannot be assigned to one device; one ElectrodeGroup per interface is written."),
    WarningCode("ELECTRODES_NOT_WRITTEN", "info",
                "Electrode (channel) rows are written only with raw data (Phase 4); metadata-only files have "
                "electrode groups but no electrodes table."),
    # Optogenetics, imaging, intracellular
    WarningCode("OPTO_SITE_NO_WAVELENGTH", "warning",
                "An optic fiber is used for optogenetic stimulation but no wavelength is recorded; NWB requires "
                "one, so no OptogeneticStimulusSite is written."),
    WarningCode("OPTO_SITE_WAVELENGTH_AMBIGUOUS", "warning",
                "An optic fiber is used with several wavelengths; NWB allows one per site, so no "
                "OptogeneticStimulusSite is written."),
    WarningCode("IMAGING_PLANE_NOT_CREATED", "info",
                "Imaging acquisitions are described in data_collection; an NWB ImagingPlane needs the indicator "
                "and imaging rate, which are not recorded, so none is written."),
    WarningCode("ICEPHYS_NOT_MAPPED", "info",
                "Intracellular recordings are described in data_collection; NWB intracellular electrodes are "
                "written only with raw data."),
    # Extensions
    WarningCode("LOCALIZATION_NOT_SUPPORTED", "info",
                "Coordinates in this system are not a 3D point in a space (e.g. a brain-surface entry point with an "
                "insertion depth) or the space is not supported yet; they are kept in the ndx-brainstem tables only."),
    WarningCode("LOCALIZATION_INCOMPLETE", "warning",
                "Coordinates lack a value or a unit for one of the three axes; the record is not localized."),
    WarningCode("SCHEMA_NOT_AVAILABLE", "warning",
                "A BrainSTEM JSON schema version the records use could not be fetched; its URL is in the file, the "
                "schema itself is not embedded. Another version is never used instead."),
    # Epochs and behavior
    WarningCode("EPOCH_TIMES_MISSING", "warning",
                "An epoch has no start or end; it is not written to the epochs table."),
    WarningCode("EPOCH_STOP_BEFORE_START", "error", "An epoch ends before it starts; it is not written."),
    WarningCode("EPOCH_NEGATIVE_TIME", "warning",
                "An epoch starts before the session start time; it is written with a negative start time."),
    WarningCode("BEHAVIOR_NO_TIMING", "info",
                "A behavior is linked to no epoch, so it has no times; it is described in the notes."),
    WarningCode("NO_TRIALS", "info", "BrainSTEM has no trial records; no trials table is written."),
]

CODES: dict[str, WarningCode] = {entry.code: entry for entry in _CODES}


def make_warning(
    code: str,
    message: str | None = None,
    *,
    label: str | None = None,
    pk: str | None = None,
    path: str | None = None,
    nwb_path: str | None = None,
    rule_id: str | None = None,
    severity: Severity | None = None,
) -> ConversionWarning:
    """Build a warning; the severity defaults to the code's registered severity."""
    entry = CODES[code]  # KeyError for an unregistered code is a programming error
    source = SourcePointer(label=label, pk=pk, path=path) if (label or pk or path) else None
    return ConversionWarning(
        code=code,
        severity=severity or entry.severity,
        message=message or entry.description,
        source=source,
        nwb_path=nwb_path,
        rule_id=rule_id,
    )
