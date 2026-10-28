import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from chorizo.ingest.ctgov import parse_date, parse_phase, parse_study, upsert_trials
from chorizo.models import Stage, Trial

FIXTURE = Path(__file__).parent / "fixtures" / "ctgov_studies.json"


def test_parse_phase_uses_latest_phase():
    assert parse_phase(["PHASE1", "PHASE2"]) == Stage.PHASE2
    assert parse_phase(["EARLY_PHASE1"]) == Stage.PHASE1
    assert parse_phase(["NA"]) is None
    assert parse_phase(None) is None


def test_parse_date_handles_month_precision():
    assert parse_date("2024-03") == date(2024, 3, 1)
    assert parse_date("2024-03-15") == date(2024, 3, 15)
    assert parse_date(None) is None


def test_parse_and_upsert_studies(session):
    studies = json.loads(FIXTURE.read_text())["studies"]
    records = [parse_study(s) for s in studies]
    first = records[0]
    assert first["nct_id"] == "NCT00000001"
    assert first["phase"] == Stage.PHASE2
    assert first["lead_sponsor"] == "Example Bio"
    assert first["interventions"] == [{"type": "DRUG", "name": "EX-101"}]
    assert first["start_date"] == date(2023, 5, 1)

    assert upsert_trials(session, records) == 2
    records[0]["overall_status"] = "COMPLETED"
    upsert_trials(session, records)
    trials = session.scalars(select(Trial).order_by(Trial.nct_id)).all()
    assert len(trials) == 2
    assert trials[0].overall_status == "COMPLETED"
