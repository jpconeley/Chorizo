from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from chorizo.api.deps import CurrentUser, SessionDep, require
from chorizo.api.schemas import AssetSummary
from chorizo.models import Asset, WatchlistItem
from chorizo.plans import Feature

router = APIRouter(prefix="/watchlist", tags=["watchlist"], dependencies=[require(Feature.WATCHLISTS)])


@router.get("", response_model=list[AssetSummary])
def get_watchlist(session: SessionDep, user: CurrentUser):
    return session.scalars(
        select(Asset)
        .join(WatchlistItem, WatchlistItem.asset_id == Asset.id)
        .where(WatchlistItem.user_id == user.id)
        .options(selectinload(Asset.organization))
        .order_by(Asset.name)
    ).all()


@router.put("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def add_to_watchlist(asset_id: int, session: SessionDep, user: CurrentUser):
    if session.get(Asset, asset_id) is None:
        raise HTTPException(404, "Asset not found")
    exists = session.scalar(
        select(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.asset_id == asset_id)
    )
    if not exists:
        session.add(WatchlistItem(user_id=user.id, asset_id=asset_id))
        session.commit()


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(asset_id: int, session: SessionDep, user: CurrentUser):
    session.execute(
        delete(WatchlistItem).where(WatchlistItem.user_id == user.id, WatchlistItem.asset_id == asset_id)
    )
    session.commit()
