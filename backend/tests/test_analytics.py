from datetime import date

import pytest

from chorizo.analytics import pos
from chorizo.analytics.benchmarks import (
    GroupKey,
    ProgramHistory,
    compute_transitions,
    likelihood_of_approval,
    outcomes,
)
from chorizo.models import AssetStatus, Modality, Stage


def test_outcomes_counts_advances_and_discontinuations():
    advanced = ProgramHistory([Stage.PHASE1, Stage.PHASE2], AssetStatus.DISCONTINUED)
    assert outcomes(advanced) == [(Stage.PHASE1, True), (Stage.PHASE2, False)]


def test_outcomes_ignores_undecided_last_stage():
    active = ProgramHistory([Stage.PHASE1, Stage.PHASE2], AssetStatus.ACTIVE)
    assert outcomes(active) == [(Stage.PHASE1, True)]


def test_approved_program_has_no_failure():
    approved = ProgramHistory([Stage.PHASE3, Stage.REGULATORY, Stage.APPROVED], AssetStatus.DISCONTINUED)
    assert outcomes(approved) == [(Stage.PHASE3, True), (Stage.REGULATORY, True)]


def test_compute_transitions_grouped():
    programs = [
        ProgramHistory([Stage.PHASE1, Stage.PHASE2], AssetStatus.ACTIVE, "oncology", Modality.ANTIBODY),
        ProgramHistory([Stage.PHASE1], AssetStatus.DISCONTINUED, "oncology", Modality.ANTIBODY),
        ProgramHistory([Stage.PHASE1, Stage.PHASE2], AssetStatus.ACTIVE, "neurology", Modality.RNA),
    ]
    overall = compute_transitions(programs)[GroupKey()]
    assert overall[Stage.PHASE1].successes == 2 and overall[Stage.PHASE1].failures == 1

    by_area = compute_transitions(programs, ("therapeutic_area",))
    assert by_area[GroupKey("oncology")][Stage.PHASE1].probability == 0.5
    assert by_area[GroupKey("neurology")][Stage.PHASE1].probability == 1.0


def test_likelihood_of_approval_chains_probabilities():
    probs = {Stage.PHASE1: 0.5, Stage.PHASE2: 0.5, Stage.PHASE3: 0.5, Stage.REGULATORY: 0.5}
    assert likelihood_of_approval(probs, Stage.PHASE1) == pytest.approx(0.0625)
    assert likelihood_of_approval(probs, Stage.PHASE3) == pytest.approx(0.25)
    assert likelihood_of_approval({Stage.PHASE3: 0.5}, Stage.PHASE3) is None


def test_pos_prefers_specific_benchmark_with_enough_data():
    table = {
        (Stage.PHASE3, GroupKey()): pos.BenchmarkPoint(0.6, 1000, "ref"),
        (Stage.PHASE3, GroupKey("oncology")): pos.BenchmarkPoint(0.4, 200, "ref"),
        (Stage.PHASE3, GroupKey("oncology", Modality.ANTIBODY)): pos.BenchmarkPoint(0.9, 5, "ref"),
        (Stage.REGULATORY, GroupKey()): pos.BenchmarkPoint(0.8, 1000, "ref"),
    }
    est = pos.estimate(table, Stage.PHASE3, "oncology", Modality.ANTIBODY)
    # Area+modality has too few programs, so the oncology-wide figure is used.
    assert est.next_stage_probability == 0.4
    assert est.likelihood_of_approval == pytest.approx(0.32)
    assert est.inputs["phase3"]["therapeutic_area"] == "oncology"
    assert est.inputs["regulatory"]["therapeutic_area"] is None


def test_pos_unknown_when_benchmarks_missing():
    est = pos.estimate({}, Stage.PRECLINICAL, None, None)
    assert est.next_stage_probability is None and est.likelihood_of_approval is None


def test_phase3_outcome_needs_phase2_first():
    jumped = ProgramHistory(
        [], AssetStatus.DISCONTINUED, entered={Stage.PHASE1: date(2010, 1, 1), Stage.PHASE3: date(2012, 1, 1)}
    )
    assert outcomes(jumped) == [(Stage.PHASE1, True)]
    full = ProgramHistory(
        [], AssetStatus.DISCONTINUED, entered={Stage.PHASE2: date(2010, 1, 1), Stage.PHASE3: date(2012, 1, 1)}
    )
    assert outcomes(full) == [(Stage.PHASE2, True), (Stage.PHASE3, False)]


def test_through_approval_rate_ends_the_chain():
    table = {
        (Stage.PHASE3, GroupKey()): pos.BenchmarkPoint(0.5, 500, "ours", through_approval=True),
        (Stage.REGULATORY, GroupKey()): pos.BenchmarkPoint(0.8, 500, "ref"),
    }
    est = pos.estimate(table, Stage.PHASE3, None, None)
    assert est.likelihood_of_approval == pytest.approx(0.5)
    assert "regulatory" not in est.inputs
