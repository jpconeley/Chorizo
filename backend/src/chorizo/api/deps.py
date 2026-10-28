from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from chorizo.db import get_session
from chorizo.models import Membership, Subscription, SubscriptionStatus, User
from chorizo.plans import Feature, Plan, cheapest_plan_with, features_for
from chorizo.security import decode_access_token

SessionDep = Annotated[Session, Depends(get_session)]

# Past-due subscriptions keep access while Stripe retries payment.
ENTITLED_STATUSES = (SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING, SubscriptionStatus.PAST_DUE)

_bearer = HTTPBearer(auto_error=False)


def get_optional_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User | None:
    if credentials is None:
        return None
    user_id = decode_access_token(credentials.credentials)
    return session.get(User, user_id) if user_id is not None else None


def get_current_user(user: Annotated[User | None, Depends(get_optional_user)]) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


OptionalUser = Annotated[User | None, Depends(get_optional_user)]
CurrentUser = Annotated[User, Depends(get_current_user)]


def active_plans(session: Session, user: User | None) -> set[Plan]:
    """Plans held by the user directly or through any organization they belong to."""
    if user is None:
        return set()
    org_ids = select(Membership.organization_id).where(Membership.user_id == user.id)
    rows = session.scalars(
        select(Subscription.plan).where(
            or_(Subscription.user_id == user.id, Subscription.organization_id.in_(org_ids)),
            Subscription.status.in_(ENTITLED_STATUSES),
        )
    )
    return {Plan(p) for p in rows if p in Plan._value2member_map_}


def get_features(session: SessionDep, user: OptionalUser) -> set[Feature]:
    return features_for(active_plans(session, user))


Features = Annotated[set[Feature], Depends(get_features)]


def upgrade_required(feature: Feature) -> HTTPException:
    plan = cheapest_plan_with(feature)
    return HTTPException(
        status.HTTP_403_FORBIDDEN,
        {"code": "upgrade_required", "feature": feature.value, "plan": plan.value if plan else None},
    )


def require(feature: Feature):
    """Route dependency: 403 with an upgrade hint unless the caller's plans include `feature`."""

    def check(features: Features) -> None:
        if feature not in features:
            raise upgrade_required(feature)

    return Depends(check)
