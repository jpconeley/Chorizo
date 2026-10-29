"""Import clinical trials from the ClinicalTrials.gov v2 API.

Docs: https://clinicaltrials.gov/data-api/api
"""

import logging
from collections.abc import Callable, Iterator
from datetime import date
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from chorizo.config import get_settings
from chorizo.models import Stage, Trial

log = logging.getLogger(__name__)

# A trial tagged with two phases (e.g. PHASE1|PHASE2) is counted at the later one.
_PHASES = {
    "EARLY_PHASE1": Stage.PHASE1,
    "PHASE1": Stage.PHASE1,
    "PHASE2": Stage.PHASE2,
    "PHASE3": Stage.PHASE3,
    "PHASE4": Stage.APPROVED,
}

DRUG_INTERVENTION_TYPES = {"DRUG", "BIOLOGICAL"}

# Only the parts of each record we use, which cuts the download by roughly 10x.
_FIELDS = ",".join(
    [
        "protocolSection.identificationModule",
        "protocolSection.statusModule",
        "protocolSection.sponsorCollaboratorsModule",
        "protocolSection.conditionsModule",
        "protocolSection.designModule",
        "protocolSection.armsInterventionsModule",
        "derivedSection.conditionBrowseModule",
    ]
)
_FILTER = "AREA[StudyType]INTERVENTIONAL AND (AREA[InterventionType]DRUG OR AREA[InterventionType]BIOLOGICAL)"


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


def _terms(module: dict[str, Any]) -> list[str]:
    terms = [m.get("term") for m in module.get("meshes", []) + module.get("ancestors", [])]
    terms += [b.get("name") for b in module.get("browseBranches", [])]
    return sorted({t for t in terms if t})


def parse_study(study: dict[str, Any]) -> dict[str, Any]:
    p = study.get("protocolSection", {})
    ident = p.get("identificationModule", {})
    status = p.get("statusModule", {})
    design = p.get("designModule", {})
    sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
    return {
        "nct_id": ident["nctId"],
        "title": ident.get("officialTitle") or ident.get("briefTitle") or "",
        "phase": parse_phase(design.get("phases")),
        "overall_status": status.get("overallStatus", "UNKNOWN"),
        "why_stopped": status.get("whyStopped"),
        "lead_sponsor": sponsor.get("name"),
        "sponsor_class": sponsor.get("class"),
        "conditions": p.get("conditionsModule", {}).get("conditions", []),
        "condition_terms": _terms(study.get("derivedSection", {}).get("conditionBrowseModule", {})),
        "interventions": [
            {"type": i.get("type"), "name": i.get("name"), "other_names": i.get("otherNames", [])}
            for i in p.get("armsInterventionsModule", {}).get("interventions", [])
        ],
        "enrollment": design.get("enrollmentInfo", {}).get("count"),
        "start_date": parse_date(status.get("startDateStruct", {}).get("date")),
        "completion_date": parse_date(
            (status.get("completionDateStruct") or status.get("primaryCompletionDateStruct") or {}).get(
                "date"
            )
        ),
        "last_update": parse_date(status.get("lastUpdatePostDateStruct", {}).get("date")),
    }


def is_drug_trial(record: dict[str, Any]) -> bool:
    return record["phase"] is not None and any(
        i["type"] in DRUG_INTERVENTION_TYPES for i in record["interventions"]
    )


def fetch_studies(
    client: httpx.Client, query: str | None = None, page_size: int = 1000, max_pages: int | None = None
) -> Iterator[dict[str, Any]]:
    """Yield raw study records, following nextPageToken.

    Asks the API for interventional drug trials and only the fields we use. If the API
    rejects that (its query syntax changes now and then), falls back to plain paging;
    callers filter with `is_drug_trial` either way.
    """
    params: dict[str, Any] = {"pageSize": page_size, "fields": _FIELDS, "filter.advanced": _FILTER}
    if query:
        params["query.term"] = query
    pages = 0
    while True:
        response = client.get("/studies", params=params)
        if response.status_code == 400 and ("fields" in params or "filter.advanced" in params):
            log.warning("API rejected fields/filter (%s); retrying without them", response.text[:200])
            params.pop("fields", None)
            params.pop("filter.advanced", None)
            continue
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


def run(
    session: Session,
    query: str | None = None,
    max_pages: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Import drug trials. Calls progress(seen, imported) after each batch."""
    seen = imported = 0
    batch: list[dict[str, Any]] = []
    headers = {
        "User-Agent": "LASO/0.1 (+https://github.com/jpconeley/chorizo)",
        "Accept": "application/json",
    }
    with httpx.Client(base_url=get_settings().ctgov_base_url, timeout=120, headers=headers) as client:
        for study in fetch_studies(client, query=query, max_pages=max_pages):
            seen += 1
            record = parse_study(study)
            if is_drug_trial(record):
                batch.append(record)
            if len(batch) >= 1000:
                imported += upsert_trials(session, batch)
                batch = []
                if progress:
                    progress(seen, imported)
    if batch:
        imported += upsert_trials(session, batch)
    if progress:
        progress(seen, imported)
    return imported
