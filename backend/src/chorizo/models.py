"""Database schema.

Four groups of tables:
- Accounts: users, organizations, memberships, subscriptions.
- Reference data: assets (therapies), their stage history, and clinical trials.
- Marketplace: funding listings, disclosures, investor interest, watchlists.
- Analytics: computed stage benchmarks and per-asset probability-of-success estimates.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from chorizo.db import Base


def _enum(cls: type[StrEnum]) -> Enum:
    # Stored as plain strings so new values don't need a Postgres enum migration.
    return Enum(cls, native_enum=False, length=32, values_callable=lambda e: [m.value for m in e])


class Stage(StrEnum):
    DISCOVERY = "discovery"
    PRECLINICAL = "preclinical"
    PHASE1 = "phase1"
    PHASE2 = "phase2"
    PHASE3 = "phase3"
    REGULATORY = "regulatory"  # NDA/BLA/MAA submitted
    APPROVED = "approved"


# Development order, used for transitions and probability chains.
STAGE_ORDER: list[Stage] = list(Stage)


class AssetStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISCONTINUED = "discontinued"


class Modality(StrEnum):
    SMALL_MOLECULE = "small_molecule"
    ANTIBODY = "antibody"
    PROTEIN = "protein"
    CELL_THERAPY = "cell_therapy"
    GENE_THERAPY = "gene_therapy"
    RNA = "rna"
    VACCINE = "vaccine"
    OTHER = "other"


class OrgType(StrEnum):
    COMPANY = "company"
    ACADEMIC = "academic"
    INVESTOR = "investor"


class MemberRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


class ListingStatus(StrEnum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    TRIALING = "trialing"
    PAST_DUE = "past_due"
    CANCELED = "canceled"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# --- Accounts ---------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(200))
    is_admin: Mapped[bool] = mapped_column(default=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="user")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user")


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    type: Mapped[OrgType] = mapped_column(_enum(OrgType))
    website: Mapped[str | None] = mapped_column(String(500))
    verified: Mapped[bool] = mapped_column(default=False)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="organization")
    assets: Mapped[list["Asset"]] = relationship(back_populates="organization")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "organization_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    role: Mapped[MemberRole] = mapped_column(_enum(MemberRole), default=MemberRole.MEMBER)

    user: Mapped[User] = relationship(back_populates="memberships")
    organization: Mapped[Organization] = relationship(back_populates="memberships")


class Subscription(TimestampMixin, Base):
    """A paid plan held by a user, or by an organization for all its members (seats)."""

    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    plan: Mapped[str] = mapped_column(String(32))
    status: Mapped[SubscriptionStatus] = mapped_column(_enum(SubscriptionStatus))
    seats: Mapped[int] = mapped_column(default=1)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), unique=True)

    user: Mapped[User | None] = relationship(back_populates="subscriptions")


# --- Reference data ---------------------------------------------------------


class Asset(TimestampMixin, Base):
    """A therapy (drug candidate) at any stage of development."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(200), index=True)
    synonyms: Mapped[list[str]] = mapped_column(JSON, default=list)
    modality: Mapped[Modality] = mapped_column(_enum(Modality))
    mechanism: Mapped[str | None] = mapped_column(String(300))
    target: Mapped[str | None] = mapped_column(String(100))
    therapeutic_area: Mapped[str] = mapped_column(String(64), index=True)
    indication: Mapped[str] = mapped_column(String(300))
    stage: Mapped[Stage] = mapped_column(_enum(Stage), index=True)
    status: Mapped[AssetStatus] = mapped_column(_enum(AssetStatus), default=AssetStatus.ACTIVE)
    uses_biomarker_selection: Mapped[bool] = mapped_column(default=False)
    orphan_designation: Mapped[bool] = mapped_column(default=False)
    summary: Mapped[str | None] = mapped_column(Text)

    organization: Mapped[Organization | None] = relationship(back_populates="assets")
    stage_history: Mapped[list["StageEvent"]] = relationship(
        back_populates="asset", order_by="StageEvent.entered_on"
    )
    trials: Mapped[list["AssetTrial"]] = relationship(back_populates="asset")
    listings: Mapped[list["Listing"]] = relationship(back_populates="asset")


class StageEvent(Base):
    """An asset entering a stage. The full history drives the stage benchmarks."""

    __tablename__ = "stage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    stage: Mapped[Stage] = mapped_column(_enum(Stage))
    entered_on: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(64))  # e.g. "ctgov", "owner", "filing"

    asset: Mapped[Asset] = relationship(back_populates="stage_history")


class Trial(TimestampMixin, Base):
    """A clinical trial record, mirrored from ClinicalTrials.gov."""

    __tablename__ = "trials"

    id: Mapped[int] = mapped_column(primary_key=True)
    nct_id: Mapped[str] = mapped_column(String(16), unique=True)
    title: Mapped[str] = mapped_column(Text)
    phase: Mapped[Stage | None] = mapped_column(_enum(Stage), index=True)
    overall_status: Mapped[str] = mapped_column(String(48), index=True)
    lead_sponsor: Mapped[str | None] = mapped_column(String(300))
    conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
    interventions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    enrollment: Mapped[int | None] = mapped_column(Integer)
    start_date: Mapped[date | None] = mapped_column(Date)
    completion_date: Mapped[date | None] = mapped_column(Date)
    last_update: Mapped[date | None] = mapped_column(Date)


class AssetTrial(Base):
    __tablename__ = "asset_trials"
    __table_args__ = (UniqueConstraint("asset_id", "trial_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    trial_id: Mapped[int] = mapped_column(ForeignKey("trials.id", ondelete="CASCADE"))

    asset: Mapped[Asset] = relationship(back_populates="trials")
    trial: Mapped[Trial] = relationship()


# --- Marketplace ------------------------------------------------------------


class Listing(TimestampMixin, Base):
    """An owner's request for funding (or a partner) for one asset."""

    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[ListingStatus] = mapped_column(_enum(ListingStatus), default=ListingStatus.DRAFT)
    headline: Mapped[str] = mapped_column(String(200))
    amount_sought_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    use_of_funds: Mapped[str | None] = mapped_column(Text)
    deal_types: Mapped[list[str]] = mapped_column(JSON, default=list)  # equity, licensing, royalty
    pitch: Mapped[str | None] = mapped_column(Text)

    asset: Mapped[Asset] = relationship(back_populates="listings")
    documents: Mapped[list["ListingDocument"]] = relationship(back_populates="listing")


class ListingDocument(TimestampMixin, Base):
    """Owner-provided disclosure: deck, data readout, patent summary, etc."""

    __tablename__ = "listing_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(48))
    url: Mapped[str] = mapped_column(String(1000))
    min_plan: Mapped[str] = mapped_column(String(32), default="free")  # gate sensitive material

    listing: Mapped[Listing] = relationship(back_populates="documents")


class InvestorInterest(TimestampMixin, Base):
    __tablename__ = "investor_interests"
    __table_args__ = (UniqueConstraint("listing_id", "user_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    message: Mapped[str | None] = mapped_column(Text)
    indicative_amount_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))


class WatchlistItem(TimestampMixin, Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (UniqueConstraint("user_id", "asset_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))


# --- Analytics --------------------------------------------------------------


class StageBenchmark(Base):
    """Historical probability that a program in `stage` advances to the next stage.

    A null therapeutic_area/modality means "all". Rows are versioned by `as_of`
    and `source`, so published reference figures and our own computed figures
    can sit side by side.
    """

    __tablename__ = "stage_benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[Stage] = mapped_column(_enum(Stage))
    therapeutic_area: Mapped[str | None] = mapped_column(String(64))
    modality: Mapped[Modality | None] = mapped_column(_enum(Modality))
    transition_probability: Mapped[float] = mapped_column(Float)
    likelihood_of_approval: Mapped[float] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(120))
    as_of: Mapped[date] = mapped_column(Date, index=True)


class PosEstimate(Base):
    """A model's probability-of-success estimate for one asset at a point in time."""

    __tablename__ = "pos_estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True)
    model_version: Mapped[str] = mapped_column(String(32))
    next_stage_probability: Mapped[float] = mapped_column(Float)
    likelihood_of_approval: Mapped[float] = mapped_column(Float)
    inputs: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
