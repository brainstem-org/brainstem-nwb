"""BrainSTEM epochs as rows of the NWB epochs table."""

from __future__ import annotations

from ..manifest.models import EpochColumnPlan, EpochRowPlan
from ..normalize.timeutil import parse_duration
from ..store.graph import Record
from .context import MapContext
from .registry import MappingRule, rules

COLUMNS = [
    EpochColumnPlan(name="brainstem_id", description="BrainSTEM epoch id"),
    EpochColumnPlan(name="behavior", description="behavioral assay of the epoch's BrainSTEM behavior, with its id"),
    EpochColumnPlan(name="data_acquisitions",
                    description="BrainSTEM data acquisitions recorded in the epoch (type and id)"),
    EpochColumnPlan(name="manipulations", description="BrainSTEM manipulations applied in the epoch (type and id)"),
]


@rules(
    MappingRule(
        id="epochs.rows",
        destination="NWBFile.epochs",
        section="Intervals",
        sources=("stem.epoch.start", "stem.epoch.end", "stem.epoch.name", "stem.epoch.behavior",
                 "stem.epoch.dataacquisitions", "stem.epoch.manipulations"),
        transform="one row per epoch, sorted by start, order and id: start_time and stop_time in seconds "
                  "relative to the session start (BrainSTEM stores them as durations from the session start); "
                  "tags = [name]; columns brainstem_id, behavior, data_acquisitions, manipulations "
                  "(links to records of other subjects are left out)",
        units="s",
        condition="both start and end are recorded",
        missing="row not written (EPOCH_TIMES_MISSING); end before start: EPOCH_STOP_BEFORE_START. "
                "BrainSTEM has no trial records, so no trials table is written",
    ),
)
def map_epochs(ctx: MapContext) -> None:
    store = ctx.store
    included = {record.pk for role in ("behavior", "dataacquisition", "manipulation") for record in ctx.unit.role(role)}
    rows: list[tuple[float, int, str, EpochRowPlan, Record]] = []
    for epoch in ctx.unit.role("epoch"):
        name = str(epoch.get("name") or "")
        start_raw, end_raw = epoch.get("start"), epoch.get("end")
        nwb_path = f"/intervals/epochs[{epoch.pk}]"
        if start_raw in (None, "") or end_raw in (None, ""):
            ctx.warn("EPOCH_TIMES_MISSING", f"epoch '{name}' has no {'start' if start_raw in (None, '') else 'end'}",
                     record=epoch, nwb_path=nwb_path, rule_id="epochs.rows")
            ctx.map("epochs.rows", nwb_path, "missing", sources=[epoch])
            continue
        try:
            start = parse_duration(start_raw).total_seconds()
            stop = parse_duration(end_raw).total_seconds()
        except ValueError as exc:
            ctx.warn("EPOCH_TIMES_MISSING", f"epoch '{name}' has unreadable times: {exc}", record=epoch,
                     rule_id="epochs.rows")
            ctx.map("epochs.rows", nwb_path, "missing", sources=[epoch], note="unreadable times")
            continue
        if stop < start:
            ctx.warn("EPOCH_STOP_BEFORE_START", f"epoch '{name}' ends ({end_raw}) before it starts ({start_raw})",
                     record=epoch, rule_id="epochs.rows")
            ctx.map("epochs.rows", nwb_path, "missing", sources=[epoch], note="stop before start")
            continue
        if start < 0:
            ctx.warn("EPOCH_NEGATIVE_TIME", f"epoch '{name}' starts {start_raw} relative to the session start",
                     record=epoch, rule_id="epochs.rows")
        behavior = store.fk_record(epoch, "behavior")
        behavior_text = ""
        if behavior is not None and behavior.pk in included:
            assay = store.fk_record(behavior, "behavioralassay")
            behavior_text = f"{assay.get('name') if assay else 'behavior'} [{behavior.pk}]"
        acquisitions = [f"{r.get('type')} [{r.pk}]" for r in store.m2m_records(epoch, "dataacquisitions")
                        if r.pk in included]
        manipulations = [f"{r.get('type')} [{r.pk}]" for r in store.m2m_records(epoch, "manipulations")
                         if r.pk in included]
        row = EpochRowPlan(
            start_time=start,
            stop_time=stop,
            tags=[name] if name else [],
            values={
                "brainstem_id": epoch.pk,
                "behavior": behavior_text,
                "data_acquisitions": "; ".join(acquisitions),
                "manipulations": "; ".join(manipulations),
            },
        )
        rows.append((start, int(epoch.get("order") or 0), epoch.pk, row, epoch))
    rows.sort(key=lambda item: item[:3])
    if rows:
        ctx.epochs.columns = list(COLUMNS)
        ctx.epochs.rows = [item[3] for item in rows]
        for item in rows:
            ctx.map("epochs.rows", f"/intervals/epochs[{item[2]}]", "present",
                    [item[3].start_time, item[3].stop_time], [item[4]])
    ctx.warn("NO_TRIALS", rule_id="epochs.rows")
