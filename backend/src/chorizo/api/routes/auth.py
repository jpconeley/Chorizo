from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from chorizo.api.deps import CurrentUser, Features, SessionDep, active_plans
from chorizo.api.schemas import LoginIn, MeOut, PlanOut, RegisterIn, TokenOut
from chorizo.models import User
from chorizo.plans import PLANS, Feature
from chorizo.security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["account"])


@router.post("/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, session: SessionDep):
    email = body.email.lower()
    if session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name)
    session.add(user)
    session.commit()
    return TokenOut(access_token=create_access_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
def login(body: LoginIn, session: SessionDep):
    user = session.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser, session: SessionDep, features: Features):
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        plans=sorted(p.value for p in active_plans(session, user)),
        features=sorted(f.value for f in features),
    )


@router.get("/plans", response_model=list[PlanOut])
def list_plans():
    return [
        PlanOut(
            plan=info.plan.value,
            name=info.name,
            audience=info.audience,
            per_seat=info.per_seat,
            features=[f.value for f in Feature if f in info.features],
        )
        for info in PLANS.values()
    ]
