"""Historical stage-transition success rates.

For every program we know the stages it entered and whether it is still
active. Each stage a program left by entering a later stage counts as a
success. The last stage of a discontinued program counts as a failure. The
last stage of an active program is still undecided, so it is left out.

When stage entry dates are known, only a later stage entered on or after a stage
counts as advancing from it. That keeps a new Phase 2 trial of an already-approved
drug from being scored as a Phase 2 success. A Phase 3 outcome also needs a Phase 2
entry before it: US law has required Phase 2 and 3 trials to be registered since
2007, so a "program" that starts at Phase 3 is nearly always a biosimilar, a new form
of an old drug or a repackaged product, not a new drug's development.

The likelihood of approval (LOA) from a stage is the product of the transition
probabilities from that stage through regulatory review, the standard method
used in the BIO/Biomedtracker studies.
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from chorizo.models import STAGE_ORDER, AssetStatus, Modality, Stage

# Stages that have a "next stage" to transition into.
TRANSITION_STAGES = STAGE_ORDER[:-1]


@dataclass(frozen=True)
class ProgramHistory:
    stages: list[Stage]
    status: AssetStatus
    therapeutic_area: str | None = None
    modality: Modality | None = None
    entered: dict[Stage, date] | None = None  # first entry date per stage, if known


@dataclass(frozen=True)
class GroupKey:
    therapeutic_area: str | None = None  # None means all areas
    modality: Modality | None = None  # None means all modalities


@dataclass(frozen=True)
class Transition:
    successes: int
    failures: int

    @property
    def sample_size(self) -> int:
        return self.successes + self.failures

    @property
    def probability(self) -> float | None:
        return self.successes / self.sample_size if self.sample_size else None


def outcomes(program: ProgramHistory) -> list[tuple[Stage, bool]]:
    """(stage, advanced?) for each stage of this program whose outcome is known."""
    if program.entered:
        return _dated_outcomes(program.entered, program.status)
    reached = sorted(set(program.stages), key=STAGE_ORDER.index)
    result = [(stage, True) for stage in reached[:-1]]
    last = reached[-1] if reached else None
    if last is not None and last != Stage.APPROVED and program.status == AssetStatus.DISCONTINUED:
        result.append((last, False))
    return result


# A stage's outcome only counts if this earlier stage was entered first (see above).
REQUIRES_EARLIER = {Stage.PHASE3: Stage.PHASE2}


def _dated_outcomes(entered: dict[Stage, date], status: AssetStatus) -> list[tuple[Stage, bool]]:
    top = max(entered, key=STAGE_ORDER.index)
    result = []
    for stage in sorted(entered, key=STAGE_ORDER.index):
        if stage == Stage.APPROVED:
            continue
        earlier = REQUIRES_EARLIER.get(stage)
        if earlier and not (earlier in entered and entered[earlier] <= entered[stage]):
            continue
        advanced = any(
            STAGE_ORDER.index(later) > STAGE_ORDER.index(stage) and on >= entered[stage]
            for later, on in entered.items()
        )
        if advanced:
            result.append((stage, True))
        elif stage == top and status == AssetStatus.DISCONTINUED:
            result.append((stage, False))
    return result


def compute_transitions(
    programs: Iterable[ProgramHistory], group_by: tuple[str, ...] = ()
) -> dict[GroupKey, dict[Stage, Transition]]:
    """Count stage outcomes, optionally grouped by therapeutic_area and/or modality."""
    counts: dict[GroupKey, dict[Stage, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for program in programs:
        key = GroupKey(
            therapeutic_area=program.therapeutic_area if "therapeutic_area" in group_by else None,
            modality=program.modality if "modality" in group_by else None,
        )
        for stage, advanced in outcomes(program):
            counts[key][stage][0 if advanced else 1] += 1
    return {
        key: {stage: Transition(s, f) for stage, (s, f) in by_stage.items()}
        for key, by_stage in counts.items()
    }


def likelihood_of_approval(probabilities: dict[Stage, float | None], start: Stage) -> float | None:
    """Chain transition probabilities from `start` to approval. None if any link is unknown."""
    if start == Stage.APPROVED:
        return 1.0
    loa = 1.0
    for stage in TRANSITION_STAGES[STAGE_ORDER.index(start) :]:
        p = probabilities.get(stage)
        if p is None:
            return None
        loa *= p
    return loa
