"""Database glue for benchmarks and estimates."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from chorizo.analytics import pos
from chorizo.analytics.benchmarks import (
    GroupKey,
    ProgramHistory,
    compute_transitions,
    likelihood_of_approval,
)
from chorizo.models import Asset, PosEstimate, StageBenchmark

COMPUTED_SOURCE = "chorizo"
GROUPINGS: list[tuple[str, ...]] = [(), ("therapeutic_area",), ("therapeutic_area", "modality")]


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
    """Prefer our own computed figures; fall back to published reference figures."""
    table: pos.BenchmarkTable = {}
    for row in sorted(latest_benchmarks(session), key=lambda r: r.source == COMPUTED_SOURCE):
        key = (row.stage, GroupKey(row.therapeutic_area, row.modality))
        table[key] = pos.BenchmarkPoint(row.transition_probability, row.sample_size, row.source)
    return table


def recompute_benchmarks(session: Session, as_of: date | None = None) -> int:
    as_of = as_of or date.today()
    assets = session.scalars(select(Asset).options(selectinload(Asset.stage_history))).all()
    programs = [
        ProgramHistory(
            stages=[e.stage for e in a.stage_history] or [a.stage],
            status=a.status,
            therapeutic_area=a.therapeutic_area,
            modality=a.modality,
        )
        for a in assets
    ]
    written = 0
    for group_by in GROUPINGS:
        for key, by_stage in compute_transitions(programs, group_by).items():
            probabilities = {stage: t.probability for stage, t in by_stage.items()}
            for stage, transition in by_stage.items():
                if transition.probability is None:
                    continue
                session.add(
                    StageBenchmark(
                        stage=stage,
                        therapeutic_area=key.therapeutic_area,
                        modality=key.modality,
                        transition_probability=transition.probability,
                        likelihood_of_approval=likelihood_of_approval(probabilities, stage) or 0.0,
                        sample_size=transition.sample_size,
                        source=COMPUTED_SOURCE,
                        as_of=as_of,
                    )
                )
                written += 1
    session.commit()
    return written


def refresh_estimates(session: Session) -> int:
    table = benchmark_table(session)
    assets = session.scalars(select(Asset)).all()
    for asset in assets:
        est = pos.estimate(table, asset.stage, asset.therapeutic_area, asset.modality)
        if est.next_stage_probability is None and est.likelihood_of_approval is None:
            continue
        session.add(
            PosEstimate(
                asset_id=asset.id,
                model_version=est.model_version,
                next_stage_probability=est.next_stage_probability or 0.0,
                likelihood_of_approval=est.likelihood_of_approval or 0.0,
                inputs=est.inputs,
            )
        )
    session.commit()
    return len(assets)


def latest_estimate(session: Session, asset_id: int) -> PosEstimate | None:
    return session.scalars(
        select(PosEstimate)
        .where(PosEstimate.asset_id == asset_id)
        .order_by(PosEstimate.computed_at.desc(), PosEstimate.id.desc())
        .limit(1)
    ).first()


def benchmark_count(session: Session) -> int:
    return session.scalar(select(func.count(StageBenchmark.id))) or 0
