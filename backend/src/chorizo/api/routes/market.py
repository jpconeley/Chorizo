"""Market overview for the terminal's dashboard and ticker tape."""

from datetime import date, timedelta

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import extract, func, select

from chorizo.api.deps import SessionDep
from chorizo.models import STAGE_ORDER, Asset, AssetStatus, Organization, Stage, StageEvent, Trial

router = APIRouter(prefix="/market", tags=["market"])

# Inferred filing dates duplicate approvals, so the feed leaves them out.
_FEED_STAGES = [Stage.PHASE1, Stage.PHASE2, Stage.PHASE3, Stage.APPROVED]


class StageCount(BaseModel):
    stage: Stage
    count: int


class YearCount(BaseModel):
    year: int
    count: int


class MarketStats(BaseModel):
    programs: int
    active: int
    approved: int
    trials: int
    phase3_starts_12m: int
    pipeline: list[StageCount]  # active programs by current stage
    approvals_by_year: list[YearCount]


class FeedEvent(BaseModel):
    asset_id: int
    asset: str
    stage: Stage
    on: date
    sponsor: str | None


@router.get("/stats", response_model=MarketStats)
def market_stats(session: SessionDep, years: int = Query(15, ge=1, le=40)):
    today = date.today()
    counts = dict(session.execute(select(Asset.status, func.count()).group_by(Asset.status)).all())
    pipeline = dict(
        session.execute(
            select(Asset.stage, func.count()).where(Asset.status == AssetStatus.ACTIVE).group_by(Asset.stage)
        ).all()
    )
    approved_year = extract("year", StageEvent.entered_on)
    by_year = dict(
        session.execute(
            select(approved_year, func.count())
            .where(
                StageEvent.stage == Stage.APPROVED,
                StageEvent.entered_on <= today,
                StageEvent.entered_on >= date(today.year - years + 1, 1, 1),
            )
            .group_by(approved_year)
        ).all()
    )
    phase3_starts = session.scalar(
        select(func.count())
        .select_from(StageEvent)
        .where(
            StageEvent.stage == Stage.PHASE3,
            StageEvent.entered_on > today - timedelta(days=365),
            StageEvent.entered_on <= today,
        )
    )
    return MarketStats(
        programs=sum(counts.values()),
        active=counts.get(AssetStatus.ACTIVE, 0),
        approved=pipeline.get(Stage.APPROVED, 0),
        trials=session.scalar(select(func.count()).select_from(Trial)) or 0,
        phase3_starts_12m=phase3_starts or 0,
        pipeline=[StageCount(stage=s, count=pipeline.get(s, 0)) for s in STAGE_ORDER],
        approvals_by_year=[
            YearCount(year=y, count=int(by_year.get(y, 0)))
            for y in range(today.year - years + 1, today.year + 1)
        ],
    )


@router.get("/feed", response_model=list[FeedEvent])
def market_feed(session: SessionDep, limit: int = Query(30, ge=1, le=100)):
    """The most recent stage entries: approvals, phase starts."""
    rows = session.execute(
        select(StageEvent.asset_id, Asset.name, StageEvent.stage, StageEvent.entered_on, Organization.name)
        .join(Asset, Asset.id == StageEvent.asset_id)
        .outerjoin(Organization, Organization.id == Asset.organization_id)
        .where(StageEvent.stage.in_(_FEED_STAGES), StageEvent.entered_on <= date.today())
        .order_by(StageEvent.entered_on.desc(), StageEvent.id.desc())
        .limit(limit)
    ).all()
    return [FeedEvent(asset_id=a, asset=n, stage=s, on=d, sponsor=o) for a, n, s, d, o in rows]
