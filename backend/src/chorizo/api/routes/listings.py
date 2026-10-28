from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from chorizo.api.deps import CurrentUser, Features, SessionDep, require
from chorizo.api.schemas import DocumentOut, InterestIn, ListingDetail, ListingIn, ListingOut
from chorizo.models import Asset, InvestorInterest, Listing, ListingStatus, Membership
from chorizo.plans import Feature, Plan

router = APIRouter(prefix="/listings", tags=["marketplace"])

_LOAD = [selectinload(Listing.asset).selectinload(Asset.organization), selectinload(Listing.documents)]


@router.get("", response_model=list[ListingOut])
def list_listings(session: SessionDep):
    return session.scalars(
        select(Listing)
        .where(Listing.status == ListingStatus.OPEN)
        .options(*_LOAD)
        .order_by(Listing.created_at.desc())
    ).all()


@router.get("/{listing_id}", response_model=ListingDetail)
def get_listing(listing_id: int, session: SessionDep, features: Features):
    listing = session.get(Listing, listing_id, options=_LOAD)
    if listing is None or listing.status == ListingStatus.DRAFT:
        raise HTTPException(404, "Listing not found")
    can_see_gated = Feature.GATED_DOCUMENTS in features
    documents = [
        DocumentOut(
            id=d.id,
            title=d.title,
            kind=d.kind,
            url=d.url if (d.min_plan == Plan.FREE or can_see_gated) else None,
            locked=not (d.min_plan == Plan.FREE or can_see_gated),
        )
        for d in listing.documents
    ]
    return ListingDetail(**ListingOut.model_validate(listing).model_dump(), documents=documents)


@router.post(
    "",
    response_model=ListingOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require(Feature.CREATE_LISTINGS)],
)
def create_listing(body: ListingIn, session: SessionDep, user: CurrentUser):
    asset = session.get(Asset, body.asset_id)
    if asset is None:
        raise HTTPException(404, "Asset not found")
    is_member = asset.organization_id is not None and session.scalar(
        select(Membership).where(
            Membership.user_id == user.id, Membership.organization_id == asset.organization_id
        )
    )
    if not is_member:
        raise HTTPException(403, "Only members of the asset's organization can list it")
    listing = Listing(**body.model_dump(), created_by_id=user.id)
    session.add(listing)
    session.commit()
    return session.get(Listing, listing.id, options=_LOAD)


@router.post(
    "/{listing_id}/interest",
    status_code=status.HTTP_201_CREATED,
    dependencies=[require(Feature.EXPRESS_INTEREST)],
)
def express_interest(listing_id: int, body: InterestIn, session: SessionDep, user: CurrentUser):
    listing = session.get(Listing, listing_id)
    if listing is None or listing.status != ListingStatus.OPEN:
        raise HTTPException(404, "Listing not found")
    session.add(InvestorInterest(listing_id=listing_id, user_id=user.id, **body.model_dump()))
    try:
        session.commit()
    except IntegrityError:
        raise HTTPException(409, "Interest already registered") from None
    return {"status": "ok"}
