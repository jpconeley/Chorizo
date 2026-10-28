from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from chorizo.models import AssetStatus, ListingStatus, Modality, Stage


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)
    full_name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: int
    email: str
    full_name: str | None
    plans: list[str]
    features: list[str]


class PlanOut(BaseModel):
    plan: str
    name: str
    audience: str
    per_seat: bool
    features: list[str]


class OrganizationOut(ORM):
    id: int
    name: str
    type: str
    verified: bool


class AssetSummary(ORM):
    id: int
    name: str
    modality: Modality
    target: str | None
    therapeutic_area: str
    indication: str
    stage: Stage
    status: AssetStatus
    organization: OrganizationOut | None


class StageEventOut(ORM):
    stage: Stage
    entered_on: date
    source: str


class TrialOut(ORM):
    nct_id: str
    title: str
    phase: Stage | None
    overall_status: str
    enrollment: int | None
    start_date: date | None
    completion_date: date | None


class AssetDetail(AssetSummary):
    mechanism: str | None
    synonyms: list[str]
    uses_biomarker_selection: bool
    orphan_designation: bool
    summary: str | None
    stage_history: list[StageEventOut]
    trials: list[TrialOut]
    open_listing_ids: list[int]


class AssetPage(BaseModel):
    items: list[AssetSummary]
    total: int
    limit: int
    offset: int


class PosOut(BaseModel):
    asset_id: int
    model_version: str
    next_stage_probability: float
    likelihood_of_approval: float
    computed_at: datetime
    inputs: dict[str, Any] | None = None  # institutional plans only


class BenchmarkOut(ORM):
    stage: Stage
    therapeutic_area: str | None
    modality: Modality | None
    transition_probability: float
    likelihood_of_approval: float
    sample_size: int
    source: str
    as_of: date


class DocumentOut(ORM):
    id: int
    title: str
    kind: str
    url: str | None
    locked: bool = False


class ListingIn(BaseModel):
    asset_id: int
    headline: str = Field(max_length=200)
    amount_sought_usd: Decimal | None = None
    use_of_funds: str | None = None
    deal_types: list[str] = []
    pitch: str | None = None
    status: ListingStatus = ListingStatus.DRAFT


class ListingOut(ORM):
    id: int
    asset: AssetSummary
    status: ListingStatus
    headline: str
    amount_sought_usd: Decimal | None
    use_of_funds: str | None
    deal_types: list[str]
    pitch: str | None
    created_at: datetime


class ListingDetail(ListingOut):
    documents: list[DocumentOut]


class InterestIn(BaseModel):
    message: str | None = None
    indicative_amount_usd: Decimal | None = None


class CheckoutIn(BaseModel):
    plan: str
    seats: int = Field(default=1, ge=1)


class UrlOut(BaseModel):
    url: str
