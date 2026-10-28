from datetime import date

import pytest
from sqlalchemy import select

from chorizo import seed
from chorizo.analytics import diagnostics, service
from chorizo.analytics.benchmarks import ProgramHistory, outcomes
from chorizo.ingest import fda, programs
from chorizo.ingest.ctgov import upsert_trials
from chorizo.models import Asset, AssetStatus, Modality, PosEstimate, Stage, StageBenchmark

TODAY = date(2026, 6, 1)


def test_clean_name_drops_doses_forms_and_comparators():
    assert programs.clean_name("Pembrolizumab 200 mg IV infusion") == "Pembrolizumab"
    assert programs.clean_name("MK-3475 (pembrolizumab)") == "MK-3475"
    assert programs.clean_name("Matching placebo") is None
    assert programs.clean_name("Standard of care") is None
    assert programs.name_key("MK 3475") == programs.name_key("mk-3475")
    assert programs.name_key("Metformin Hydrochloride") == programs.name_key("metformin")
    assert programs.name_key("Sodium Chloride") == "sodiumchloride"  # all-salt names stay intact


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


def _trial(nct, phase, drug, *, status="COMPLETED", start="2015-01-01", sponsor_class="INDUSTRY", others=(),
           also=None, healthy=False, title=None, conditions=None):  # fmt: skip
    y, m, d = map(int, start.split("-"))
    drugs = [{"type": "DRUG", "name": drug, "other_names": list(others)}]
    if also:
        drugs.append({"type": "DRUG", "name": also, "other_names": []})
    return {
        "nct_id": nct,
        "title": title or f"{drug} trial",
        "phase": phase,
        "overall_status": status,
        "why_stopped": None,
        "lead_sponsor": "Example Bio" if sponsor_class == "INDUSTRY" else "Some University",
        "sponsor_class": sponsor_class,
        "conditions": conditions or (["Healthy Volunteers"] if healthy else ["Ulcerative Colitis"]),
        "condition_terms": [] if healthy else ["Inflammatory Bowel Diseases"],
        "interventions": drugs + [{"type": "DRUG", "name": "Placebo", "other_names": []}],
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
        # A liver-impairment study is supporting work, not a liver-disease program.
        _trial(
            "NCT16",
            Stage.PHASE1,
            "EX-1",
            start="2013-06-01",
            conditions=["Hepatic Impairment"],
            title="Pharmacokinetics of EX-1 in Subjects With Hepatic Impairment",
        ),  # fmt: skip
        # EX-2: stopped after Phase 2 long ago -> discontinued. Later a drug-interaction
        # study in healthy volunteers uses midazolam as a probe.
        _trial("NCT5", Stage.PHASE1, "EX-2", start="2011-01-01"),
        _trial("NCT6", Stage.PHASE2, "EX-2", start="2013-01-01", status="TERMINATED"),
        _trial("NCT11", Stage.PHASE1, "EX-2", start="2016-01-01", also="Midazolam", healthy=True),
        _trial("NCT12", Stage.APPROVED, "Midazolam", start="2005-01-01", sponsor_class="OTHER"),
        # EX-3: healthy-volunteer Phase 1, then Phase 2 still recruiting -> active, undecided.
        _trial("NCT13", Stage.PHASE1, "EX-3", start="2024-01-01", healthy=True),
        _trial("NCT7", Stage.PHASE2, "EX-3", start="2025-01-01", status="RECRUITING"),
        # Mesalamine is background therapy in an EX-3 trial; it's been marketed for decades.
        _trial("NCT14", Stage.PHASE2, "EX-3", start="2025-02-01", also="Mesalamine", status="RECRUITING"),
        _trial("NCT15", Stage.APPROVED, "Mesalamine", start="2004-01-01", sponsor_class="OTHER"),
        # A vaccine: approvals aren't visible, so it's shown but not benchmarked.
        _trial(
            "NCT17",
            Stage.PHASE3,
            "FluShield",
            start="2012-01-01",
            conditions=["Influenza"],
            title="Immunogenicity and Safety of FluShield in Adults",
        ),  # fmt: skip
        # Only ever tested for bioequivalence: never becomes a program.
        _trial("NCT18", Stage.PHASE1, "CKD-999", title="Bioequivalence of CKD-999 and Co-administration"),
        # A blood product (CBER), a bare dosage form and a vague product name.
        _trial("NCT19", Stage.PHASE3, "Fibrin Sealant Vapor Heated", start="2002-01-01"),
        _trial("NCT20", Stage.PHASE3, "Lozenges", start="2017-01-01"),
        _trial("NCT21", Stage.PHASE3, "TULY Spray", start="2010-01-01"),
        # EX-5: Phase 1 and 3, no Phase 4 trial, but FDA approved it as exfivib.
        _trial("NCT9", Stage.PHASE1, "EX-5", start="2010-01-01", others=["exfivib"]),
        _trial("NCT10", Stage.PHASE3, "EX-5", start="2013-01-01"),
        # Academic-only drug: excluded from programs.
        _trial("NCT8", Stage.PHASE2, "Old Generic", sponsor_class="OTHER"),
    ]
    upsert_trials(session, records)
    fda.save_approvals(session, {"exfivib": ("Exfivib", date(2016, 5, 1), "NDA000001")})
    assert programs.run(session, today=TODAY) == 8
    return session


def _assets(session):
    return {a.name: a for a in session.scalars(select(Asset).where(Asset.source == "ctgov"))}


def test_programs_built_from_trials(imported):
    assets = _assets(imported)
    assert set(assets) == {
        "Exampleumab", "EX-2", "EX-3", "Exfivib", "Mesalamine", "FluShield",
        "Fibrin Sealant Vapor Heated", "TULY",
    }  # fmt: skip

    ex1 = assets["Exampleumab"]
    assert ex1.stage == Stage.APPROVED
    assert ex1.therapeutic_area == "immunology"
    assert ex1.modality == Modality.ANTIBODY
    assert ex1.organization.name == "Example Bio"
    assert len(ex1.trials) == 5  # including the supporting liver-impairment study
    assert [e.stage for e in ex1.stage_history][:3] == [Stage.PHASE1, Stage.PHASE2, Stage.PHASE3]

    assert assets["EX-2"].status == AssetStatus.DISCONTINUED
    assert assets["EX-3"].status == AssetStatus.ACTIVE

    # Re-running is idempotent.
    assert programs.run(imported, today=TODAY) == 8
    assert imported.scalar(select(Asset).where(Asset.name == "Exampleumab")).id == ex1.id


def test_healthy_volunteer_phase1_joins_disease_program(imported):
    ex3 = _assets(imported)["EX-3"]
    assert ex3.therapeutic_area == "immunology"
    assert {e.stage for e in ex3.stage_history} == {Stage.PHASE1, Stage.PHASE2}
    assert len(ex3.trials) == 3


def test_fda_approval_marks_program_approved(imported):
    ex5 = _assets(imported)["Exfivib"]
    assert ex5.stage == Stage.APPROVED
    assert ex5.benchmark_eligible
    approved = next(e for e in ex5.stage_history if e.stage == Stage.APPROVED)
    assert approved.entered_on == date(2016, 5, 1)


def test_already_marketed_drugs_are_not_benchmarked(imported):
    assets = _assets(imported)
    assert not assets["Mesalamine"].benchmark_eligible  # background therapy, marketed since 2004
    assert "not counted in benchmarks" in assets["Mesalamine"].summary
    assert assets["EX-2"].benchmark_eligible


def test_supporting_studies_never_form_programs(imported):
    assets = _assets(imported)
    assert "Midazolam" not in assets  # probe drug in a drug-interaction study
    assert "CKD-999" not in assets  # only ever in a bioequivalence study
    assert {a.therapeutic_area for a in assets.values()} <= {"immunology", "infectious_disease"}


def test_blood_products_and_vague_names_are_not_benchmarked(imported):
    assets = _assets(imported)
    assert not assets["Fibrin Sealant Vapor Heated"].benchmark_eligible
    assert "blood products" in assets["Fibrin Sealant Vapor Heated"].summary
    assert not assets["TULY"].benchmark_eligible
    assert "doesn't identify a specific drug" in assets["TULY"].summary


def test_junk_names_and_drug_like_names():
    for junk in ["Suppositories", "Lozenges", "After", "Baseline", "2x 200", "20 6", "Dex nasal", "Part 2"]:
        assert programs.clean_name(junk) is None, junk
    for name in ["AZD1656", "PF-04958242", "BI 1356", "Faldaprevir", "Epoetin beta pegol"]:
        assert programs.drug_like(name), name
    for name in ["TULY", "EMS association", "SHAPE"]:
        assert not programs.drug_like(name), name


def test_fda_matching_handles_salts_inn_names_and_long_fda_names():
    assert programs.name_key("Triptorelin Pamoate") == "triptorelin"
    assert "triptorelin" in programs.fda_keys("TRIPTORELIN PAMOATE")
    assert "acetaminophen" in programs.name_candidates("Paracetamol hot drink")
    fda_side = programs.fda_keys("METHOXY POLYETHYLENE GLYCOL-EPOETIN BETA")
    assert programs.name_candidates("Epoetin beta pegol") & fda_side == {"epoetinbeta"}


def test_vaccines_are_shown_but_not_benchmarked(imported):
    flu = _assets(imported)["FluShield"]
    assert flu.modality == Modality.VACCINE
    assert not flu.benchmark_eligible
    assert "vaccines" in flu.summary


def test_fda_matching_uses_name_words_and_brands():
    assert "rivaroxaban" in programs.name_candidates("Rivaroxaban Xarelto")
    assert "insulinaspart" in programs.name_candidates("Faster-acting insulin aspart")
    assert "insulin" not in programs.name_candidates("Insulin Peglispro")
    approvals = fda.first_approvals(
        [
            {
                "application_number": "NDA202439",
                "products": [{"brand_name": "XARELTO", "active_ingredients": [{"name": "RIVAROXABAN"}]}],
                "submissions": [
                    {
                        "submission_type": "ORIG",
                        "submission_status": "AP",
                        "submission_status_date": "20110701",
                    }
                ],
            }
        ]
    )
    assert approvals["xarelto"][1] == approvals["rivaroxaban"][1] == date(2011, 7, 1)


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
    # Phase 1: EX-1, EX-2, EX-3 and EX-5 advanced; midazolam isn't counted.
    # Phase 2: EX-1 advanced, EX-2 failed; EX-3 undecided. Phase 3: EX-1 and EX-5 approved.
    assert (rows[Stage.PHASE1].transition_probability, rows[Stage.PHASE1].sample_size) == (1.0, 4)
    assert (rows[Stage.PHASE2].transition_probability, rows[Stage.PHASE2].sample_size) == (0.5, 2)
    assert (rows[Stage.PHASE3].transition_probability, rows[Stage.PHASE3].sample_size) == (1.0, 2)
    assert Stage.REGULATORY not in rows  # never computed from ClinicalTrials.gov
    # The approval chain is completed with the published regulatory rate.
    assert rows[Stage.PHASE3].likelihood_of_approval == pytest.approx(0.853)

    # Tiny samples never override the published reference figures.
    assert service.refresh_estimates(imported) > 0
    ex3 = imported.scalar(select(Asset).where(Asset.name == "EX-3"))
    est = imported.scalar(select(PosEstimate).where(PosEstimate.asset_id == ex3.id))
    assert est.next_stage_probability == pytest.approx(0.307)
    ex2 = imported.scalar(select(Asset).where(Asset.name == "EX-2"))
    assert imported.scalar(select(PosEstimate).where(PosEstimate.asset_id == ex2.id)) is None


def test_fda_first_approvals():
    applications = [
        {
            "application_number": "NDA021000",
            "products": [{"active_ingredients": [{"name": "EXFIVIB HYDROCHLORIDE", "strength": "10MG"}]}],
            "submissions": [
                {"submission_type": "SUPPL", "submission_status": "AP", "submission_status_date": "20010101"},
                {"submission_type": "ORIG", "submission_status": "AP", "submission_status_date": "20160501"},
            ],
        },
        {  # a later combination product doesn't move the first approval
            "application_number": "NDA022000",
            "products": [{"active_ingredients": [{"name": "EXFIVIB"}, {"name": "OTHERDRUG"}]}],
            "submissions": [
                {"submission_type": "ORIG", "submission_status": "AP", "submission_status_date": "20200101"}
            ],
        },
        {  # generics don't count
            "application_number": "ANDA090000",
            "products": [{"active_ingredients": [{"name": "GENERICOL"}]}],
            "submissions": [
                {"submission_type": "ORIG", "submission_status": "AP", "submission_status_date": "19990101"}
            ],
        },
    ]
    approvals = fda.first_approvals(applications)
    assert approvals["exfivib"][1:] == (date(2016, 5, 1), "NDA021000")
    assert approvals["otherdrug"][1] == date(2020, 1, 1)
    assert "genericol" not in approvals


def test_diagnostics_report_runs(imported):
    text = diagnostics.report(imported)
    assert "FDA-approved ingredients and brands loaded: 1" in text
    assert "2 vaccines/cell/gene/blood products, 1 vague names" in text
    assert "phase2 failures counted: 1" in text  # EX-2
    assert "EX-2" in text
