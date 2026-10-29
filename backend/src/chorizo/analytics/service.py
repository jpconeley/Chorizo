"""Database glue for benchmarks and estimates."""

from datetime import date

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from chorizo.analytics import pos
from chorizo.analytics.benchmarks import (
    GroupKey,
    ProgramHistory,
    compute_transitions,
    likelihood_of_approval,
)
from chorizo.ingest.programs import SOURCE as CTGOV_SOURCE
from chorizo.models import Asset, AssetStatus, PosEstimate, Stage, StageBenchmark, StageEvent

COMPUTED_SOURCE = "ClinicalTrials.gov (LASO)"
GROUPINGS: list[tuple[str, ...]] = [(), ("therapeutic_area",), ("therapeutic_area", "modality")]
# Filings aren't visible on ClinicalTrials.gov, so our Phase 3 "success" is reaching
# approval: the computed Phase 3 rate already includes the regulatory step, and no
# separate regulatory rate is computed.
UNOBSERVED_STAGES = {Stage.REGULATORY}


def latest_benchmarks(session: Session, source: str | None = None) -> list[StageBenchmark]:
    """The most recent row per source and stage/area/modality, optionally from one source."""
    query = select(StageBenchmark)
    if source:
        query = query.where(StageBenchmark.source == source)
    rows = session.scalars(query.order_by(StageBenchmark.as_of.desc())).all()
    seen: set[tuple] = set()
    latest = []
    for row in rows:
        key = (row.source, row.stage, row.therapeutic_area, row.modality)
        if key not in seen:
            seen.add(key)
            latest.append(row)
    return latest


def benchmark_table(session: Session) -> pos.BenchmarkTable:
    """Our computed figures where they have enough data, else published reference figures."""
    table: pos.BenchmarkTable = {}
    for row in sorted(latest_benchmarks(session), key=lambda r: r.source == COMPUTED_SOURCE):
        key = (row.stage, GroupKey(row.therapeutic_area, row.modality))
        computed = row.source == COMPUTED_SOURCE
        if computed and key in table and row.sample_size < pos.MIN_SAMPLE_SIZE:
            continue
        table[key] = pos.BenchmarkPoint(
            row.transition_probability,
            row.sample_size,
            row.source,
            through_approval=computed and row.stage == Stage.PHASE3,
        )
    return table


def _program_histories(session: Session) -> list[ProgramHistory]:
    assets = {
        row.id: row
        for row in session.execute(
            select(Asset.id, Asset.status, Asset.therapeutic_area, Asset.modality).where(
                Asset.source == CTGOV_SOURCE, Asset.benchmark_eligible
            )
        )
    }
    entered: dict[int, dict[Stage, date]] = {}
    events = session.execute(
        select(StageEvent.asset_id, StageEvent.stage, StageEvent.entered_on).where(
            StageEvent.asset_id.in_(select(Asset.id).where(Asset.source == CTGOV_SOURCE))
        )
    )
    for asset_id, stage, on in events:
        dates = entered.setdefault(asset_id, {})
        if stage not in dates or on < dates[stage]:
            dates[stage] = on
    return [
        ProgramHistory(
            stages=list(entered[aid]),
            status=row.status,
            therapeutic_area=row.therapeutic_area,
            modality=row.modality,
            entered=entered[aid],
        )
        for aid, row in assets.items()
        if aid in entered
    ]


def recompute_benchmarks(session: Session, as_of: date | None = None) -> int:
    """Replace our computed benchmarks with fresh ones from the imported programs."""
    as_of = as_of or date.today()
    programs = _program_histories(session)
    session.execute(delete(StageBenchmark).where(StageBenchmark.source == COMPUTED_SOURCE))
    rows = []
    for group_by in GROUPINGS:
        for key, by_stage in compute_transitions(programs, group_by).items():
            probabilities = {stage: t.probability for stage, t in by_stage.items()}
            # Our Phase 3 rate runs through approval, so the filing step adds nothing.
            probabilities.update({s: 1.0 for s in UNOBSERVED_STAGES})
            for stage, transition in by_stage.items():
                if transition.probability is None or stage in UNOBSERVED_STAGES:
                    continue
                rows.append(
                    {
                        "stage": stage,
                        "therapeutic_area": key.therapeutic_area,
                        "modality": key.modality,
                        "transition_probability": transition.probability,
                        "likelihood_of_approval": likelihood_of_approval(probabilities, stage) or 0.0,
                        "sample_size": transition.sample_size,
                        "source": COMPUTED_SOURCE,
                        "as_of": as_of,
                    }
                )
    if rows:
        session.execute(insert(StageBenchmark), rows)
    session.commit()
    return len(rows)


def refresh_estimates(session: Session) -> int:
    table = benchmark_table(session)
    rows = []
    # Discontinued programs get no estimate: their chance of advancing is effectively zero.
    for asset_id, stage, area, modality in session.execute(
        select(Asset.id, Asset.stage, Asset.therapeutic_area, Asset.modality).where(
            Asset.status != AssetStatus.DISCONTINUED
        )
    ):
        est = pos.estimate(table, stage, area, modality)
        if est.next_stage_probability is None and est.likelihood_of_approval is None:
            continue
        rows.append(
            {
                "asset_id": asset_id,
                "model_version": est.model_version,
                "next_stage_probability": est.next_stage_probability or 0.0,
                "likelihood_of_approval": est.likelihood_of_approval or 0.0,
                "inputs": est.inputs,
            }
        )
    for i in range(0, len(rows), 5000):
        session.execute(insert(PosEstimate), rows[i : i + 5000])
    session.commit()
    return len(rows)


def latest_estimate(session: Session, asset_id: int) -> PosEstimate | None:
    return session.scalars(
        select(PosEstimate)
        .where(PosEstimate.asset_id == asset_id)
        .order_by(PosEstimate.computed_at.desc(), PosEstimate.id.desc())
        .limit(1)
    ).first()


def benchmark_count(session: Session) -> int:
    return session.scalar(select(func.count(StageBenchmark.id))) or 0
