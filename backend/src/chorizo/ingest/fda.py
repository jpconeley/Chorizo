"""First FDA approval date per active ingredient and brand name, from Drugs@FDA via openFDA.

Docs: https://open.fda.gov/apis/drug/drugsfda/

Only NDAs and BLAs count (ANDAs are generics). An ingredient's first approval is the
earliest original ("ORIG") submission with status approved ("AP") on any application
containing it. Biologics regulated by CBER (most vaccines, cell and gene therapies) are
not in Drugs@FDA, so for those we still rely on Phase 4 trials.
"""

import io
import json
import logging
import zipfile
from collections.abc import Iterable, Iterator
from datetime import date
from typing import Any

import httpx
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from chorizo.config import get_settings
from chorizo.ingest.programs import fda_keys
from chorizo.models import DrugApproval

log = logging.getLogger(__name__)
_HEADERS = {"User-Agent": "LASO/0.1 (+https://github.com/jpconeley/chorizo)"}


def _date(value: str | None) -> date | None:
    if not value or len(value) != 8 or not value.isdigit():
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:]))
    except ValueError:
        return None


def first_approvals(applications: Iterable[dict[str, Any]]) -> dict[str, tuple[str, date, str]]:
    """{ingredient key: (ingredient name, first approval date, application number)}."""
    best: dict[str, tuple[str, date, str]] = {}
    for app in applications:
        number = app.get("application_number") or ""
        if not number.startswith(("NDA", "BLA")):
            continue
        approved = [
            d
            for s in app.get("submissions") or []
            if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP"
            for d in [_date(s.get("submission_status_date"))]
            if d
        ]
        if not approved:
            continue
        when = min(approved)
        for product in app.get("products") or []:
            # Brand names too: trials often name a drug "Rivaroxaban (Xarelto)" or just "Xarelto".
            names = [i.get("name") for i in product.get("active_ingredients") or []]
            names.append(product.get("brand_name"))
            for name in names:
                name = (name or "").strip()
                for key in fda_keys(name) if name else ():
                    if key and (key not in best or when < best[key][1]):
                        best[key] = (name.title(), when, number)
    return best


def _from_bulk_download(client: httpx.Client) -> Iterator[dict[str, Any]]:
    index = client.get(get_settings().openfda_download_index).raise_for_status().json()
    for partition in index["results"]["drug"]["drugsfda"]["partitions"]:
        archive = zipfile.ZipFile(io.BytesIO(client.get(partition["file"]).raise_for_status().content))
        for member in archive.namelist():
            yield from json.loads(archive.read(member)).get("results", [])


def _from_search_api(client: httpx.Client) -> Iterator[dict[str, Any]]:
    # The search API stops at skip=25,000, a little short of the full set; fallback only.
    url = f"{get_settings().openfda_base_url}/drug/drugsfda.json"
    for skip in range(0, 26000, 1000):
        response = client.get(url, params={"limit": 1000, "skip": skip})
        if response.status_code == 404:  # past the end
            return
        results = response.raise_for_status().json().get("results", [])
        if not results:
            return
        yield from results


def fetch_applications() -> list[dict[str, Any]]:
    with httpx.Client(timeout=300, headers=_HEADERS, follow_redirects=True) as client:
        try:
            return list(_from_bulk_download(client))
        except (httpx.HTTPError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
            log.warning("openFDA bulk download failed (%s); using the search API", exc)
            return list(_from_search_api(client))


def save_approvals(session: Session, approvals: dict[str, tuple[str, date, str]]) -> int:
    session.execute(delete(DrugApproval))
    rows = [
        {
            "ingredient_key": key[:200],
            "ingredient": name[:300],
            "first_approved_on": when,
            "application_number": num,
        }
        for key, (name, when, num) in approvals.items()
    ]
    for i in range(0, len(rows), 5000):
        session.execute(insert(DrugApproval), rows[i : i + 5000])
    session.commit()
    return len(rows)


def run(session: Session) -> int:
    return save_approvals(session, first_approvals(fetch_applications()))
