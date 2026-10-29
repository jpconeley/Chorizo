"""The signed-in user's dashboard: what they follow, offers they've made, their listings,
and one activity feed across all of it."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from chorizo.analytics.service import latest_estimate
from chorizo.api.deps import CurrentUser, Features, SessionDep
from chorizo.api.schemas import AssetSummary
from chorizo.models import (
    Asset,
    InvestorInterest,
    Listing,
    ListingStatus,
    Membership,
    Stage,
    StageEvent,
    User,
    WatchlistItem,
)
from chorizo.plans import Feature

router = APIRouter(prefix="/me", tags=["account"])

ACTIVITY_LIMIT = 40
# Inferred filing dates duplicate approvals.
_EVENT_STAGES = [Stage.PHASE1, Stage.PHASE2, Stage.PHASE3, Stage.APPROVED]


class Move(BaseModel):
    stage: Stage
    on: date


class Followed(BaseModel):
    asset: AssetSummary
    followed_on: date
    latest: Move | None
    next_stage_probability: float | None  # None without the asset_pos feature
    likelihood_of_approval: float | None


class OfferSent(BaseModel):
    listing_id: int
    asset_id: int
    asset: str
    headline: str
    amount_sought_usd: Decimal | None
    indicative_amount_usd: Decimal | None
    message: str | None
    listing_status: ListingStatus
    sent_on: date


class OwnListing(BaseModel):
    listing_id: int
    asset_id: int
    asset: str
    headline: str
    status: ListingStatus
    interest_count: int
    created_on: date


class InterestReceived(BaseModel):
    listing_id: int
    asset: str
    investor: str
    indicative_amount_usd: Decimal | None
    message: str | None
    on: date


class Activity(BaseModel):
    kind: Literal["stage", "followed", "offer_sent", "listing_created", "interest_received"]
    on: date
    asset_id: int
    asset: str
    stage: Stage | None = None
    listing_id: int | None = None
    detail: str | None = None


class Dashboard(BaseModel):
    following: list[Followed]
    offers: list[OfferSent]
    listings: list[OwnListing]
    interest_received: list[InterestReceived]
    activity: list[Activity]


def _day(value: datetime | date) -> date:
    return value.date() if isinstance(value, datetime) else value


@router.get("/dashboard", response_model=Dashboard)
def dashboard(session: SessionDep, user: CurrentUser, features: Features):
    today = date.today()
    activity: list[Activity] = []

    # Following (watchlist), with each drug's latest move.
    watched = session.execute(
        select(WatchlistItem, Asset)
        .join(Asset, Asset.id == WatchlistItem.asset_id)
        .where(WatchlistItem.user_id == user.id)
        .options(selectinload(Asset.organization))
        .order_by(WatchlistItem.created_at.desc())
    ).all()
    asset_ids = [asset.id for _, asset in watched]
    events = session.execute(
        select(StageEvent.asset_id, StageEvent.stage, StageEvent.entered_on)
        .where(
            StageEvent.asset_id.in_(asset_ids),
            StageEvent.stage.in_(_EVENT_STAGES),
            StageEvent.entered_on <= today,
        )
        .order_by(StageEvent.entered_on.desc())
    ).all()
    latest: dict[int, Move] = {}
    names = {asset.id: asset.name for _, asset in watched}
    for asset_id, stage, on in events:
        if asset_id in latest:
            continue
        # Only each drug's latest move goes in the feed; its full history is on its page.
        latest[asset_id] = Move(stage=stage, on=on)
        activity.append(Activity(kind="stage", on=on, asset_id=asset_id, asset=names[asset_id], stage=stage))

    show_pos = Feature.ASSET_POS in features
    following = []
    for item, asset in watched:
        est = latest_estimate(session, asset.id) if show_pos else None
        following.append(
            Followed(
                asset=AssetSummary.model_validate(asset),
                followed_on=_day(item.created_at),
                latest=latest.get(asset.id),
                next_stage_probability=est.next_stage_probability if est else None,
                likelihood_of_approval=est.likelihood_of_approval if est else None,
            )
        )
        activity.append(
            Activity(kind="followed", on=_day(item.created_at), asset_id=asset.id, asset=asset.name)
        )

    # Offers this user sent (expressions of interest on listings).
    offers = []
    for interest, listing, asset in session.execute(
        select(InvestorInterest, Listing, Asset)
        .join(Listing, Listing.id == InvestorInterest.listing_id)
        .join(Asset, Asset.id == Listing.asset_id)
        .where(InvestorInterest.user_id == user.id)
        .order_by(InvestorInterest.created_at.desc())
    ):
        offers.append(
            OfferSent(
                listing_id=listing.id,
                asset_id=asset.id,
                asset=asset.name,
                headline=listing.headline,
                amount_sought_usd=listing.amount_sought_usd,
                indicative_amount_usd=interest.indicative_amount_usd,
                message=interest.message,
                listing_status=listing.status,
                sent_on=_day(interest.created_at),
            )
        )
        activity.append(
            Activity(
                kind="offer_sent",
                on=_day(interest.created_at),
                asset_id=asset.id,
                asset=asset.name,
                listing_id=listing.id,
                detail=listing.headline,
            )
        )

    # Listings this user created or that belong to their organizations.
    org_ids = select(Membership.organization_id).where(Membership.user_id == user.id)
    own = session.execute(
        select(Listing, Asset)
        .join(Asset, Asset.id == Listing.asset_id)
        .where(or_(Listing.created_by_id == user.id, Asset.organization_id.in_(org_ids)))
        .order_by(Listing.created_at.desc())
    ).all()
    listing_ids = [listing.id for listing, _ in own]
    counts = dict(
        session.execute(
            select(InvestorInterest.listing_id, func.count())
            .where(InvestorInterest.listing_id.in_(listing_ids))
            .group_by(InvestorInterest.listing_id)
        ).all()
    )
    listings = []
    asset_of_listing = {}
    for listing, asset in own:
        asset_of_listing[listing.id] = asset
        listings.append(
            OwnListing(
                listing_id=listing.id,
                asset_id=asset.id,
                asset=asset.name,
                headline=listing.headline,
                status=listing.status,
                interest_count=counts.get(listing.id, 0),
                created_on=_day(listing.created_at),
            )
        )
        activity.append(
            Activity(
                kind="listing_created",
                on=_day(listing.created_at),
                asset_id=asset.id,
                asset=asset.name,
                listing_id=listing.id,
                detail=listing.headline,
            )
        )

    received = []
    for interest, investor in session.execute(
        select(InvestorInterest, User)
        .join(User, User.id == InvestorInterest.user_id)
        .where(InvestorInterest.listing_id.in_(listing_ids), InvestorInterest.user_id != user.id)
        .order_by(InvestorInterest.created_at.desc())
    ):
        asset = asset_of_listing[interest.listing_id]
        received.append(
            InterestReceived(
                listing_id=interest.listing_id,
                asset=asset.name,
                investor=investor.full_name or investor.email,
                indicative_amount_usd=interest.indicative_amount_usd,
                message=interest.message,
                on=_day(interest.created_at),
            )
        )
        activity.append(
            Activity(
                kind="interest_received",
                on=_day(interest.created_at),
                asset_id=asset.id,
                asset=asset.name,
                listing_id=interest.listing_id,
                detail=investor.full_name or investor.email,
            )
        )

    activity.sort(key=lambda a: a.on, reverse=True)
    return Dashboard(
        following=following,
        offers=offers,
        listings=listings,
        interest_received=received,
        activity=activity[:ACTIVITY_LIMIT],
    )
