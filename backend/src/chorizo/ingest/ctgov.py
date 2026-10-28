"""Import clinical trials from the ClinicalTrials.gov v2 API.

Docs: https://clinicaltrials.gov/data-api/api
"""

from collections.abc import Iterator
from datetime import date
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from chorizo.config import get_settings
from chorizo.models import Stage, Trial

# A trial tagged with two phases (e.g. PHASE1|PHASE2) is counted at the later one.
_PHASES = {
    "EARLY_PHASE1": Stage.PHASE1,
    "PHASE1": Stage.PHASE1,
    "PHASE2": Stage.PHASE2,
    "PHASE3": Stage.PHASE3,
    "PHASE4": Stage.APPROVED,
}


def parse_date(value: str | None) -> date | None:
    """CT.gov dates are YYYY-MM-DD or YYYY-MM; month-only dates map to the 1st."""
    if not value:
        return None
    parts = value.split("-")
    if len(parts) == 2:
        parts.append("01")
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, IndexError):
        return None


def parse_phase(phases: list[str] | None) -> Stage | None:
    stages = [_PHASES[p] for p in phases or [] if p in _PHASES]
    return max(stages, key=list(Stage).index) if stages else None


def parse_study(study: dict[str, Any]) -> dict[str, Any]:
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    design = p.get("designModule", {})
    return {
        "nct_id": ident["nctId"],
        "title": ident.get("officialTitle") or ident.get("briefTitle") or "",
        "phase": parse_phase(design.get("phases")),
        "overall_status": status.get("overallStatus", "UNKNOWN"),
        "lead_sponsor": p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("name"),
        "conditions": p.get("conditionsModule", {}).get("conditions", []),
        "interventions": [
            {"type": i.get("type"), "name": i.get("name")}
            for i in p.get("armsInterventionsModule", {}).get("interventions", [])
        ],
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "start_date": parse_date(status.get("startDateStruct", {}).get("date")),
        "completion_date": parse_date(status.get("completionDateStruct", {}).get("date")),
        "last_update": parse_date(status.get("lastUpdatePostDateStruct", {}).get("date")),
    }


def fetch_studies(
    client: httpx.Client, query: str | None = None, page_size: int = 100, max_pages: int | None = None
) -> Iterator[dict[str, Any]]:
    """Yield raw study records, following nextPageToken. Interventional drug/biologic trials only."""
    params: dict[str, Any] = {
        "pageSize": page_size,
        "filter.advanced": "AREA[StudyType]INTERVENTIONAL AND "
        "(AREA[InterventionType]DRUG OR AREA[InterventionType]BIOLOGICAL)",
    }
    if query:
        params["query.term"] = query
    pages = 0
    while True:
        response = client.get("/studies", params=params)
        response.raise_for_status()
        body = response.json()
        yield from body.get("studies", [])
        pages += 1
        token = body.get("nextPageToken")
        if not token or (max_pages is not None and pages >= max_pages):
            return
        params["pageToken"] = token


def upsert_trials(session: Session, records: list[dict[str, Any]]) -> int:
    existing = {
        t.nct_id: t
        for t in session.scalars(select(Trial).where(Trial.nct_id.in_([r["nct_id"] for r in records])))
    }
    for record in records:
        trial = existing.get(record["nct_id"])
        if trial is None:
            session.add(Trial(**record))
        else:
            for field, value in record.items():
                setattr(trial, field, value)
    session.commit()
    return len(records)


def run(session: Session, query: str | None = None, max_pages: int | None = None) -> int:
    total = 0
    batch: list[dict[str, Any]] = []
    with httpx.Client(base_url=get_settings().ctgov_base_url, timeout=60) as client:
        for study in fetch_studies(client, query=query, max_pages=max_pages):
            batch.append(parse_study(study))
            if len(batch) >= 500:
                total += upsert_trials(session, batch)
                batch = []
    if batch:
        total += upsert_trials(session, batch)
    return total
