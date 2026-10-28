"""Subscription plans and the features each one unlocks.

This is the single source of truth for the paywall. The API checks features,
never plan names, so plans can be repackaged without touching route code.
Prices live in Stripe; see Settings.stripe_price_*.
"""

from dataclasses import dataclass
from enum import StrEnum


class Feature(StrEnum):
    BROWSE_ASSETS = "browse_assets"
    STAGE_BENCHMARKS = "stage_benchmarks"  # headline success rates by stage
    BENCHMARK_DRILLDOWN = "benchmark_drilldown"  # by therapeutic area / modality
    ASSET_POS = "asset_pos"  # per-asset probability-of-success estimates
    WATCHLISTS = "watchlists"
    EXPRESS_INTEREST = "express_interest"  # contact owners about a listing
    GATED_DOCUMENTS = "gated_documents"  # owner disclosures marked for paid plans
    DATA_EXPORT = "data_export"
    API_ACCESS = "api_access"
    MODEL_INPUTS = "model_inputs"  # see the inputs behind each estimate
    CREATE_LISTINGS = "create_listings"
    LISTING_ANALYTICS = "listing_analytics"


class Plan(StrEnum):
    FREE = "free"
    PRO = "pro"  # individual / retail investors
    INSTITUTIONAL = "institutional"  # funds, family offices, pharma BD; per-seat
    SPONSOR = "sponsor"  # asset owners listing therapies


@dataclass(frozen=True)
class PlanInfo:
    plan: Plan
    name: str
    audience: str
    features: frozenset[Feature]
    per_seat: bool = False


_FREE = frozenset({Feature.BROWSE_ASSETS, Feature.STAGE_BENCHMARKS})
_PRO = _FREE | {
    Feature.BENCHMARK_DRILLDOWN,
    Feature.ASSET_POS,
    Feature.WATCHLISTS,
    Feature.EXPRESS_INTEREST,
    Feature.GATED_DOCUMENTS,
}
_INSTITUTIONAL = _PRO | {Feature.DATA_EXPORT, Feature.API_ACCESS, Feature.MODEL_INPUTS}
_SPONSOR = _FREE | {Feature.BENCHMARK_DRILLDOWN, Feature.CREATE_LISTINGS, Feature.LISTING_ANALYTICS}

PLANS: dict[Plan, PlanInfo] = {
    Plan.FREE: PlanInfo(Plan.FREE, "Free", "Anyone", _FREE),
    Plan.PRO: PlanInfo(Plan.PRO, "Pro", "Individual investors", _PRO),
    Plan.INSTITUTIONAL: PlanInfo(
        Plan.INSTITUTIONAL, "Institutional", "Funds and pharma BD teams", _INSTITUTIONAL, per_seat=True
    ),
    Plan.SPONSOR: PlanInfo(Plan.SPONSOR, "Sponsor", "Companies and labs listing assets", _SPONSOR),
}

PAID_PLANS = [Plan.PRO, Plan.INSTITUTIONAL, Plan.SPONSOR]


def features_for(plans: set[Plan]) -> set[Feature]:
    """Features are the union of every active plan; everyone gets Free."""
    features = set(PLANS[Plan.FREE].features)
    for plan in plans:
        features |= PLANS[plan].features
    return features


def cheapest_plan_with(feature: Feature) -> Plan | None:
    """The plan to suggest when a user hits a paywall."""
    for plan in [Plan.FREE, Plan.PRO, Plan.SPONSOR, Plan.INSTITUTIONAL]:
        if feature in PLANS[plan].features:
            return plan
    return None
