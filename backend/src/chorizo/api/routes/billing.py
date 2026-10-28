"""Stripe subscriptions.

Checkout and the customer portal are hosted by Stripe. Our database learns
about subscription changes only through the webhook, so the webhook is the
source of truth for entitlements.
"""

import json
from datetime import UTC, datetime
from typing import Any

import stripe
from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from chorizo.api.deps import CurrentUser, SessionDep
from chorizo.api.schemas import CheckoutIn, UrlOut
from chorizo.config import get_settings
from chorizo.models import Subscription, SubscriptionStatus
from chorizo.plans import PAID_PLANS, PLANS, Plan

router = APIRouter(prefix="/billing", tags=["billing"])

_STATUS = {
    "active": SubscriptionStatus.ACTIVE,
    "trialing": SubscriptionStatus.TRIALING,
    "past_due": SubscriptionStatus.PAST_DUE,
}


def _client() -> stripe.StripeClient:
    key = get_settings().stripe_secret_key
    if not key:
        raise HTTPException(503, "Billing is not configured")
    return stripe.StripeClient(key)


def _price_for(plan: Plan) -> str:
    settings = get_settings()
    price = {
        Plan.PRO: settings.stripe_price_pro,
        Plan.INSTITUTIONAL: settings.stripe_price_institutional,
        Plan.SPONSOR: settings.stripe_price_sponsor,
    }.get(plan, "")
    if not price:
        raise HTTPException(503, f"No Stripe price configured for plan '{plan.value}'")
    return price


@router.post("/checkout", response_model=UrlOut)
def create_checkout(body: CheckoutIn, session: SessionDep, user: CurrentUser):
    try:
        plan = Plan(body.plan)
    except ValueError:
        raise HTTPException(422, "Unknown plan") from None
    if plan not in PAID_PLANS:
        raise HTTPException(422, "Plan is not purchasable")
    seats = body.seats if PLANS[plan].per_seat else 1
    price = _price_for(plan)
    client = _client()
    if not user.stripe_customer_id:
        customer = client.v1.customers.create({"email": user.email, "metadata": {"user_id": str(user.id)}})
        user.stripe_customer_id = customer.id
        session.commit()
    web_url = get_settings().web_url
    metadata = {"user_id": str(user.id), "plan": plan.value}
    checkout = client.v1.checkout.sessions.create(
        {
            "mode": "subscription",
            "customer": user.stripe_customer_id,
            "line_items": [{"price": price, "quantity": seats}],
            "success_url": f"{web_url}/account?checkout=success",
            "cancel_url": f"{web_url}/pricing",
            "subscription_data": {"metadata": metadata},
            "metadata": metadata,
        }
    )
    return UrlOut(url=checkout.url)


@router.post("/portal", response_model=UrlOut)
def create_portal(user: CurrentUser):
    if not user.stripe_customer_id:
        raise HTTPException(400, "No billing account yet")
    portal = _client().v1.billing_portal.sessions.create(
        {"customer": user.stripe_customer_id, "return_url": f"{get_settings().web_url}/account"}
    )
    return UrlOut(url=portal.url)


def apply_subscription_event(session: Session, event: dict[str, Any]) -> bool:
    """Mirror a customer.subscription.* event into our table. Returns True if handled."""
    if not event.get("type", "").startswith("customer.subscription."):
        return False
    obj = event["data"]["object"]
    metadata = obj.get("metadata") or {}
    plan = metadata.get("plan")
    user_id = metadata.get("user_id")
    if plan not in Plan._value2member_map_ or not user_id:
        return False

    items = (obj.get("items") or {}).get("data") or [{}]
    period_end = items[0].get("current_period_end") or obj.get("current_period_end")
    status = _STATUS.get(obj.get("status"), SubscriptionStatus.CANCELED)
    if event["type"] == "customer.subscription.deleted":
        status = SubscriptionStatus.CANCELED

    sub = session.scalar(select(Subscription).where(Subscription.stripe_subscription_id == obj["id"]))
    if sub is None:
        sub = Subscription(stripe_subscription_id=obj["id"], user_id=int(user_id))
        session.add(sub)
    sub.plan = plan
    sub.status = status
    sub.seats = items[0].get("quantity") or 1
    sub.current_period_end = datetime.fromtimestamp(period_end, UTC) if period_end else None
    session.commit()
    return True


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request, session: SessionDep, stripe_signature: str = Header(alias="Stripe-Signature")
):
    payload = await request.body()
    secret = get_settings().stripe_webhook_secret
    if not secret:
        raise HTTPException(503, "Billing is not configured")
    try:
        stripe.Webhook.construct_event(payload, stripe_signature, secret)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(400, "Invalid signature") from None
    handled = apply_subscription_event(session, json.loads(payload))
    return {"received": True, "handled": handled}
