from fastapi import APIRouter

from chorizo.analytics.pos import MIN_SAMPLE_SIZE
from chorizo.analytics.service import latest_benchmarks
from chorizo.api.deps import Features, SessionDep, upgrade_required
from chorizo.api.schemas import BenchmarkOut
from chorizo.models import STAGE_ORDER, Modality
from chorizo.plans import Feature

router = APIRouter(prefix="/benchmarks", tags=["analytics"])


@router.get("", response_model=list[BenchmarkOut])
def list_benchmarks(
    session: SessionDep,
    features: Features,
    therapeutic_area: str | None = None,
    modality: Modality | None = None,
    source: str | None = None,
    min_sample_size: int = MIN_SAMPLE_SIZE,
):
    """Stage success rates. Everyone sees the all-programs figures; filtering by
    therapeutic area or modality is a paid feature. Rates from fewer than
    `min_sample_size` programs are hidden as statistically meaningless."""
    if (therapeutic_area or modality) and Feature.BENCHMARK_DRILLDOWN not in features:
        raise upgrade_required(Feature.BENCHMARK_DRILLDOWN)
    rows = [
        r
        for r in latest_benchmarks(session, source)
        if r.therapeutic_area == therapeutic_area
        and r.modality == modality
        and r.sample_size >= min_sample_size
    ]
    return sorted(rows, key=lambda r: (r.source, STAGE_ORDER.index(r.stage)))
