import csv
import io
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from chorizo.analytics.service import latest_estimate
from chorizo.api.deps import Features, SessionDep, require
from chorizo.api.schemas import AssetDetail, AssetPage, AssetSummary, PosOut, TrialOut
from chorizo.models import Asset, AssetTrial, ListingStatus, Modality, Stage
from chorizo.plans import Feature

router = APIRouter(prefix="/assets", tags=["assets"])


def _filtered(stage, therapeutic_area, modality, q):
    query = select(Asset)
    if stage:
        query = query.where(Asset.stage == stage)
    if therapeutic_area:
        query = query.where(Asset.therapeutic_area == therapeutic_area)
    if modality:
        query = query.where(Asset.modality == modality)
    if q:
        pattern = f"%{q}%"
        query = query.where(
            or_(Asset.name.ilike(pattern), Asset.indication.ilike(pattern), Asset.target.ilike(pattern))
        )
    return query


@router.get("", response_model=AssetPage)
def list_assets(
    session: SessionDep,
    stage: Stage | None = None,
    therapeutic_area: str | None = None,
    modality: Modality | None = None,
    q: str | None = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
):
    query = _filtered(stage, therapeutic_area, modality, q)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.options(selectinload(Asset.organization)).order_by(Asset.name).limit(limit).offset(offset)
    ).all()
    return AssetPage(
        items=[AssetSummary.model_validate(a) for a in rows], total=total, limit=limit, offset=offset
    )


@router.get("/export.csv", dependencies=[require(Feature.DATA_EXPORT)])
def export_assets(
    session: SessionDep,
    stage: Stage | None = None,
    therapeutic_area: str | None = None,
    modality: Modality | None = None,
    q: str | None = None,
):
    rows = session.scalars(_filtered(stage, therapeutic_area, modality, q).order_by(Asset.name)).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["id", "name", "modality", "target", "therapeutic_area", "indication", "stage", "status"])
    for a in rows:
        writer.writerow(
            [a.id, a.name, a.modality, a.target, a.therapeutic_area, a.indication, a.stage, a.status]
        )
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=assets.csv"},
    )


MAX_TRIALS = 100


def _recent(links: list[AssetTrial]):
    trials = [link.trial for link in links]
    return sorted(trials, key=lambda t: t.start_date or date.min, reverse=True)[:MAX_TRIALS]


@router.get("/{asset_id}", response_model=AssetDetail)
def get_asset(asset_id: int, session: SessionDep):
    asset = session.get(
        Asset,
        asset_id,
        options=[
            selectinload(Asset.organization),
            selectinload(Asset.stage_history),
            selectinload(Asset.trials).selectinload(AssetTrial.trial),
            selectinload(Asset.listings),
        ],
    )
    if asset is None:
        raise HTTPException(404, "Asset not found")
    return AssetDetail(
        **AssetSummary.model_validate(asset).model_dump(),
        mechanism=asset.mechanism,
        synonyms=asset.synonyms,
        uses_biomarker_selection=asset.uses_biomarker_selection,
        orphan_designation=asset.orphan_designation,
        summary=asset.summary,
        stage_history=asset.stage_history,
        trials=[TrialOut.model_validate(t) for t in _recent(asset.trials)],
        trial_count=len(asset.trials),
        open_listing_ids=[lst.id for lst in asset.listings if lst.status == ListingStatus.OPEN],
    )


@router.get("/{asset_id}/pos", response_model=PosOut, dependencies=[require(Feature.ASSET_POS)])
def get_asset_pos(asset_id: int, session: SessionDep, features: Features):
    if session.get(Asset, asset_id) is None:
        raise HTTPException(404, "Asset not found")
    est = latest_estimate(session, asset_id)
    if est is None:
        raise HTTPException(404, "No estimate yet for this asset")
    return PosOut(
        asset_id=asset_id,
        model_version=est.model_version,
        next_stage_probability=est.next_stage_probability,
        likelihood_of_approval=est.likelihood_of_approval,
        computed_at=est.computed_at,
        inputs=est.inputs if Feature.MODEL_INPUTS in features else None,
    )
