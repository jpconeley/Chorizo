from datetime import date

import pytest
from sqlalchemy import select

from chorizo import seed
from chorizo.analytics import service
from chorizo.analytics.benchmarks import ProgramHistory, outcomes
from chorizo.ingest import programs
from chorizo.ingest.ctgov import upsert_trials
from chorizo.models import Asset, AssetStatus, Modality, PosEstimate, Stage, StageBenchmark

TODAY = date(2026, 6, 1)


def test_clean_name_drops_doses_forms_and_comparators():
    assert programs.clean_name("Pembrolizumab 200 mg IV infusion") == "Pembrolizumab"
    assert programs.clean_name("MK-3475 (pembrolizumab)") == "MK-3475"
    assert programs.clean_name("Matching placebo") is None
    assert programs.clean_name("Standard of care") is None
    assert programs.name_key("MK 3475") == programs.name_key("mk-3475")


def test_drug_names_splits_combinations_and_keeps_aliases():
    combo = {"type": "DRUG", "name": "Drug A + Drug B", "other_names": ["XYZ-1"]}
    assert programs.drug_names(combo) == [("Drug A", []), ("Drug B", [])]
    single = {"type": "BIOLOGICAL", "name": "ABC-123", "other_names": ["abcizumab", "anti-PD-1 antibody"]}
    assert programs.drug_names(single) == [("ABC-123", ["abcizumab"])]
    assert programs.drug_names({"type": "DEVICE", "name": "Stent"}) == []


def test_classify_area_and_modality():
    assert programs.classify_area(["Lymphoma", "Immune System Diseases"], []) == "oncology"
    assert (
        programs.classify_area(["Inflammatory Bowel Diseases", "Digestive System Diseases"], [])
        == "immunology"
    )
    assert programs.classify_area([], ["Type 2 Diabetes"]) == "metabolic"
    assert programs.classify_area([], ["Something rare"]) == "other"
    assert programs.guess_modality(["abcizumab"], biological=True) == Modality.ANTIBODY
    assert programs.guess_modality(["inclisiran"], biological=False) == Modality.RNA
    assert programs.guess_modality(["XYZ-1"], biological=False) == Modality.SMALL_MOLECULE


def test_dated_outcomes_ignore_stages_entered_after_approval():
    history = ProgramHistory(
        stages=[],
        status=AssetStatus.ACTIVE,
        entered={
            Stage.PHASE1: date(2010, 1, 1),
            Stage.PHASE3: date(2012, 1, 1),
            Stage.REGULATORY: date(2015, 1, 1),
            Stage.APPROVED: date(2015, 1, 1),
            Stage.PHASE2: date(2020, 1, 1),  # new indication study after approval
        },
    )
    assert outcomes(history) == [
        (Stage.PHASE1, True),
        (Stage.PHASE3, True),
        (Stage.REGULATORY, True),
    ]


def _trial(nct, phase, drug, *, status="COMPLETED", start="2015-01-01", sponsor_class="INDUSTRY", others=()):
    y, m, d = map(int, start.split("-"))
    return {
        "nct_id": nct,
        "title": f"{drug} trial",
        "phase": phase,
        "overall_status": status,
        "why_stopped": None,
        "lead_sponsor": "Example Bio" if sponsor_class == "INDUSTRY" else "Some University",
        "sponsor_class": sponsor_class,
        "conditions": ["Ulcerative Colitis"],
        "condition_terms": ["Inflammatory Bowel Diseases"],
        "interventions": [
            {"type": "DRUG", "name": drug, "other_names": list(others)},
            {"type": "DRUG", "name": "Placebo", "other_names": []},
        ],
        "enrollment": 100,
        "start_date": date(y, m, d),
        "completion_date": date(y + 2, m, d),
        "last_update": date(y + 2, m, d),
    }


@pytest.fixture
def imported(session):
    records = [
        # EX-1 (aka exampleumab): Phase 1 -> 2 -> 3 -> approved (Phase 4 trial exists).
        _trial("NCT1", Stage.PHASE1, "EX-1", start="2010-01-01", others=["exampleumab"]),
        _trial("NCT2", Stage.PHASE2, "exampleumab 10 mg", start="2012-01-01"),
        _trial("NCT3", Stage.PHASE3, "EX-1", start="2014-01-01"),
        _trial("NCT4", Stage.APPROVED, "Exampleumab", start="2019-01-01"),
        # EX-2: stopped after Phase 2 long ago -> discontinued.
        _trial("NCT5", Stage.PHASE1, "EX-2", start="2011-01-01"),
        _trial("NCT6", Stage.PHASE2, "EX-2", start="2013-01-01", status="TERMINATED"),
        # EX-3: Phase 2 still recruiting -> active, outcome unknown.
        _trial("NCT7", Stage.PHASE2, "EX-3", start="2025-01-01", status="RECRUITING"),
        # Academic-only drug: excluded from programs.
        _trial("NCT8", Stage.PHASE2, "Old Generic", sponsor_class="OTHER"),
    ]
    upsert_trials(session, records)
    assert programs.run(session, today=TODAY) == 3
    return session


def test_programs_built_from_trials(imported):
    assets = {a.name: a for a in imported.scalars(select(Asset).where(Asset.source == "ctgov"))}
    assert set(assets) == {"Exampleumab", "EX-2", "EX-3"}

    ex1 = assets["Exampleumab"]
    assert ex1.stage == Stage.APPROVED
    assert ex1.therapeutic_area == "immunology"
    assert ex1.modality == Modality.ANTIBODY
    assert ex1.organization.name == "Example Bio"
    assert len(ex1.trials) == 4
    assert [e.stage for e in ex1.stage_history][:3] == [Stage.PHASE1, Stage.PHASE2, Stage.PHASE3]

    assert assets["EX-2"].status == AssetStatus.DISCONTINUED
    assert assets["EX-3"].status == AssetStatus.ACTIVE

    # Re-running is idempotent.
    assert programs.run(imported, today=TODAY) == 3
    assert imported.scalar(select(Asset).where(Asset.name == "Exampleumab")).id == ex1.id


def test_benchmarks_and_estimates_from_programs(imported):
    seed.seed_reference(imported)
    assert service.recompute_benchmarks(imported, as_of=TODAY) > 0
    rows = {
        r.stage: r
        for r in imported.scalars(
            select(StageBenchmark).where(
                StageBenchmark.source == service.COMPUTED_SOURCE,
                StageBenchmark.therapeutic_area.is_(None),
                StageBenchmark.modality.is_(None),
            )
        )
    }
    # Phase 1: EX-1 and EX-2 advanced. Phase 2: EX-1 advanced, EX-2 failed; EX-3 undecided.
    assert (rows[Stage.PHASE1].transition_probability, rows[Stage.PHASE1].sample_size) == (1.0, 2)
    assert (rows[Stage.PHASE2].transition_probability, rows[Stage.PHASE2].sample_size) == (0.5, 2)
    assert Stage.REGULATORY not in rows  # never computed from ClinicalTrials.gov

    # Tiny samples never override the published reference figures.
    assert service.refresh_estimates(imported) > 0
    ex3 = imported.scalar(select(Asset).where(Asset.name == "EX-3"))
    est = imported.scalar(select(PosEstimate).where(PosEstimate.asset_id == ex3.id))
    assert est.next_stage_probability == pytest.approx(0.307)
    ex2 = imported.scalar(select(Asset).where(Asset.name == "EX-2"))
    assert imported.scalar(select(PosEstimate).where(PosEstimate.asset_id == ex2.id)) is None
