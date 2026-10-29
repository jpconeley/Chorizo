"""Per-asset probability-of-success estimates.

Model v0 is a benchmark lookup: for each remaining stage it uses the most
specific benchmark with enough history (therapeutic area + modality, then
therapeutic area, then all programs) and chains them into a likelihood of
approval. Later models can add asset-level adjustments (biomarker selection,
sponsor track record, trial design) and should bump MODEL_VERSION.
"""

from dataclasses import dataclass, field

from chorizo.analytics.benchmarks import TRANSITION_STAGES, GroupKey
from chorizo.models import STAGE_ORDER, Modality, Stage

MODEL_VERSION = "v0-benchmark"
MIN_SAMPLE_SIZE = 30


@dataclass(frozen=True)
class BenchmarkPoint:
    probability: float
    sample_size: int
    source: str
    # True when this rate already runs through approval (our Phase 3 rate, since
    # filings aren't visible): the chain stops here instead of adding the filing step.
    through_approval: bool = False


BenchmarkTable = dict[tuple[Stage, GroupKey], BenchmarkPoint]


@dataclass
class Estimate:
    next_stage_probability: float | None
    likelihood_of_approval: float | None
    model_version: str = MODEL_VERSION
    inputs: dict[str, dict] = field(default_factory=dict)


def _lookup(
    table: BenchmarkTable, stage: Stage, area: str | None, modality: Modality | None
) -> tuple[GroupKey, BenchmarkPoint] | None:
    for key in (GroupKey(area, modality), GroupKey(area, None), GroupKey(None, None)):
        point = table.get((stage, key))
        if point is not None and point.sample_size >= MIN_SAMPLE_SIZE:
            return key, point
    return None


def estimate(
    table: BenchmarkTable, stage: Stage, therapeutic_area: str | None, modality: Modality | None
) -> Estimate:
    if stage == Stage.APPROVED:
        return Estimate(next_stage_probability=None, likelihood_of_approval=1.0)

    result = Estimate(next_stage_probability=None, likelihood_of_approval=1.0)
    for s in TRANSITION_STAGES[STAGE_ORDER.index(stage) :]:
        found = _lookup(table, s, therapeutic_area, modality)
        if found is None:
            result.likelihood_of_approval = None
            result.inputs[s.value] = {"benchmark": None}
            continue
        key, point = found
        if s == stage:
            result.next_stage_probability = point.probability
        if result.likelihood_of_approval is not None:
            result.likelihood_of_approval *= point.probability
        result.inputs[s.value] = {
            "probability": point.probability,
            "sample_size": point.sample_size,
            "source": point.source,
            "therapeutic_area": key.therapeutic_area,
            "modality": key.modality.value if key.modality else None,
            "through_approval": point.through_approval,
        }
        if point.through_approval:
            break
    return result
