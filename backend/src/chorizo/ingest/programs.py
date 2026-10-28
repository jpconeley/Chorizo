"""Turn imported trials into drug development programs (assets).

A program is one drug in one therapeutic area, following the BIO/Biomedtracker
convention. Steps:

1. Pull the drugs out of each trial: split combinations, drop placebos and
   comparators, normalize names (ignoring salts), and merge aliases. A trial that
   lists "MK-3475" with other name "pembrolizumab" links the two names.
2. Work out when each drug was first marketed: its first FDA approval (Drugs@FDA)
   or its first Phase 4 trial, whichever is earlier.
3. Group industry-sponsored trials by (drug, therapeutic area). Phase 1 trials with
   no disease (healthy volunteers) join the same drug's disease programs.
4. Infer the stage history (first trial start per phase) and approval: the program(s)
   that got furthest before the drug was marketed are the ones it was approved for.
   Status is discontinued once nothing has happened for INACTIVE_YEARS, unless a
   trial is still running.
5. Flag which programs count toward benchmarks: only those that started before the
   drug was marketed. That leaves out comparators, probe drugs in interaction
   studies, background therapy and new uses of old drugs, which would otherwise
   show up as thousands of "failed" programs.
6. Upsert the programs as assets with source "ctgov", plus stage events and trial links.

Known limits: approvals outside the US and CBER biologics (most vaccines, cell and
gene therapies) are only seen through Phase 4 trials, and the regulatory stage itself
is not observable on ClinicalTrials.gov.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, insert, select, update
from sqlalchemy.orm import Session

from chorizo.models import (
    STAGE_ORDER,
    Asset,
    AssetStatus,
    AssetTrial,
    DrugApproval,
    Listing,
    Modality,
    Organization,
    OrgType,
    Stage,
    StageEvent,
    Trial,
)

SOURCE = "ctgov"
INACTIVE_YEARS = 3
RUNNING_STATUSES = {"RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING", "ENROLLING_BY_INVITATION"}

# --- Drug names ---------------------------------------------------------------

_NOT_A_DRUG = re.compile(
    r"placebo|sham|saline|vehicle|standard of care|standard care|standard therapy|usual care|"
    r"best supportive care|supportive care|no treatment|no intervention|observation|control|"
    r"comparator|investigator'?s? choice|physician'?s? choice|water for injection|dextrose|"
    r"chemotherapy|radiotherapy|radiation|surgery|anesthesia|dummy|matching",
    re.IGNORECASE,
)
# Class descriptions, not drug names; never used to merge aliases.
_GENERIC = re.compile(
    r"\b(antibody|antibodies|inhibitor|agonist|antagonist|vaccine candidate|drug|therapy|treatment|"
    r"tablet|capsule|injection|infusion|study drug|investigational product|active|combination)\b",
    re.IGNORECASE,
)
_DOSE = re.compile(r"\b\d+(\.\d+)?\s*(mg|mcg|µg|ug|g|ml|mg/kg|mg/m2|iu|units?|%)\b", re.IGNORECASE)
_FORM = re.compile(
    r"\b(tablets?|capsules?|injections?|injectable|oral|iv|intravenous|subcutaneous|sc|infusion|"
    r"solution|suspension|cream|gel|ointment|patch|spray|high[- ]dose|low[- ]dose|dose|doses|"
    r"extended[- ]release|er|xr|sr)\b",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"\s*(?:\+|/|,|;|\bplus\b|\band\b|\bwith\b|\bin combination with\b)\s*", re.IGNORECASE)


def clean_name(raw: str) -> str | None:
    """A display-ready drug name, or None if this isn't an investigational drug."""
    if not raw or _NOT_A_DRUG.search(raw):
        return None
    name = re.sub(r"\(.*?\)|\[.*?\]", " ", raw)
    name = _FORM.sub(" ", _DOSE.sub(" ", name))
    name = re.sub(r"[^\w\- ]", " ", name)
    name = re.sub(r"\s+", " ", name).strip(" -")
    return name if len(name) >= 3 else None


_SALTS = re.compile(
    r"\b(hydrochloride|dihydrochloride|hcl|hydrobromide|sodium|disodium|potassium|calcium|"
    r"magnesium|mesylate|dimesylate|maleate|citrate|acetate|sulfate|sulphate|phosphate|tartrate|"
    r"bitartrate|besylate|fumarate|succinate|bromide|chloride|tosylate|anhydrous|"
    r"(mono|di|tri|hemi|sesqui)?hydrate)\b"
)


def name_key(name: str) -> str:
    """Matching key: lowercase, salts dropped, spaces and hyphens removed.

    'MK 3475' == 'MK-3475' and 'Metformin Hydrochloride' == 'metformin'.
    """
    lowered = name.lower()
    key = re.sub(r"[\s\-]", "", _SALTS.sub(" ", lowered))
    return key or re.sub(r"[\s\-]", "", lowered)


def drug_names(intervention: dict) -> list[tuple[str, list[str]]]:
    """(name, aliases) for each drug in one intervention entry."""
    if intervention.get("type") not in {"DRUG", "BIOLOGICAL"}:
        return []
    aliases = [
        a
        for a in (clean_name(o) for o in intervention.get("other_names") or [])
        if a and not _GENERIC.search(a) and len(a) <= 40
    ]
    parts = [clean_name(p) for p in _SPLIT.split(intervention.get("name") or "")]
    parts = [p for p in parts if p]
    # Aliases only describe the intervention as a whole when it names a single drug.
    return [(p, aliases if len(parts) == 1 else []) for p in parts]


class _Aliases:
    """Union-find over name keys."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, key: str) -> str:
        self.parent.setdefault(key, key)
        while self.parent[key] != key:
            self.parent[key] = self.parent[self.parent[key]]
            key = self.parent[key]
        return key

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


# --- Classification -----------------------------------------------------------

# First match wins, so more specific areas come first.
_AREAS: list[tuple[str, tuple[str, ...]]] = [
    (
        "oncology",
        (
            "neoplasm",
            "cancer",
            "tumor",
            "carcinoma",
            "lymphoma",
            "leukemia",
            "melanoma",
            "sarcoma",
            "myeloma",
            "glioma",
            "blastoma",
        ),
    ),
    (
        "infectious_disease",
        (
            "infection",
            "virus diseases",
            "bacterial",
            "mycoses",
            "parasitic",
            "hiv",
            "hepatitis",
            "covid",
            "influenza",
            "tuberculosis",
            "malaria",
            "sepsis",
        ),
    ),
    (
        "cardiovascular",
        (
            "cardiovascular",
            "heart",
            "vascular diseases",
            "hypertension",
            "coronary",
            "atrial fibrillation",
            "thrombosis",
            "dyslipidemia",
            "hypercholesterolemia",
        ),
    ),
    (
        "metabolic",
        (
            "nutritional and metabolic",
            "metabolic diseases",
            "endocrine",
            "diabetes",
            "obesity",
            "lipid metabolism",
        ),
    ),
    (
        "psychiatry",
        (
            "mental disorders",
            "behavior and behavior mechanisms",
            "depressi",
            "schizophrenia",
            "anxiety",
            "bipolar",
            "substance-related",
            "attention deficit",
        ),
    ),
    (
        "neurology",
        (
            "nervous system diseases",
            "neurodegenerative",
            "alzheimer",
            "parkinson",
            "epilepsy",
            "multiple sclerosis",
            "migraine",
            "neuropath",
            "dementia",
        ),
    ),
    (
        "immunology",
        (
            "autoimmune",
            "immune system diseases",
            "arthritis",
            "psoriasis",
            "lupus",
            "inflammatory bowel",
            "colitis",
            "crohn",
            "atopic dermatitis",
            "hypersensitivity",
        ),
    ),
    (
        "respiratory",
        ("respiratory tract diseases", "lung diseases", "asthma", "pulmonary", "copd", "cystic fibrosis"),
    ),
    (
        "hematology",
        ("hemic and lymphatic", "anemia", "hemophilia", "sickle", "thalassemia", "thrombocytopenia"),
    ),
    ("gastroenterology", ("digestive system diseases", "liver", "gastro", "hepatic", "pancrea")),
    ("ophthalmology", ("eye diseases", "macular", "retin", "glaucoma", "uveitis")),
    ("dermatology", ("skin", "dermat", "acne", "alopecia")),
    ("renal", ("kidney", "renal", "urologic")),
]
THERAPEUTIC_AREAS = [area for area, _ in _AREAS] + ["other"]


def classify_area(condition_terms: Iterable[str], conditions: Iterable[str]) -> str:
    for texts in (condition_terms, conditions):
        haystack = " | ".join(texts).lower()
        if not haystack:
            continue
        for area, keywords in _AREAS:
            if any(k in haystack for k in keywords):
                return area
    return "other"


def guess_modality(names: Iterable[str], biological: bool) -> Modality:
    text = " ".join(names).lower()
    words = re.findall(r"[a-z]+", text)
    if any(w.endswith("mab") for w in words):
        return Modality.ANTIBODY
    if "car-t" in text or "car t" in text or any(w.endswith(("leucel", "cel")) for w in words):
        return Modality.CELL_THERAPY
    if "vaccine" in text:
        return Modality.VACCINE
    if "mrna" in text or "oligonucleotide" in text or any(w.endswith(("siran", "rsen")) for w in words):
        return Modality.RNA
    if "gene therapy" in text or "aav" in words or any(w.endswith(("vec", "gene")) for w in words):
        return Modality.GENE_THERAPY
    if biological or any(w.endswith(("cept", "ase", "kin")) for w in words):
        return Modality.PROTEIN
    return Modality.SMALL_MOLECULE


# --- Programs -----------------------------------------------------------------


@dataclass
class TrialRow:
    id: int
    phase: Stage
    overall_status: str
    lead_sponsor: str | None
    sponsor_class: str | None
    conditions: list[str]
    condition_terms: list[str]
    interventions: list[dict]
    start_date: date | None
    completion_date: date | None
    last_update: date | None

    @property
    def started(self) -> date | None:
        return self.start_date or self.completion_date or self.last_update

    @property
    def last_activity(self) -> date | None:
        dates = [d for d in (self.start_date, self.completion_date, self.last_update) if d]
        return max(dates) if dates else None


@dataclass
class Program:
    key: str
    area: str
    trials: list[TrialRow] = field(default_factory=list)
    names: Counter = field(default_factory=Counter)
    biological: bool = False
    marketed_on: date | None = None  # when the drug was first marketed, for any use
    approved_on: date | None = None  # when it was approved for this program

    def add(self, trial: TrialRow, names: Iterable[str], biological: bool) -> None:
        if all(t.id != trial.id for t in self.trials):
            self.trials.append(trial)
        self.names.update(names)
        self.biological |= biological

    @property
    def clinical_trials(self) -> list[TrialRow]:
        return [t for t in self.trials if t.phase != Stage.APPROVED and t.started]

    @property
    def first_entry(self) -> date | None:
        return min((t.started for t in self.clinical_trials), default=None)

    @property
    def eligible(self) -> bool:
        """Counts toward benchmarks: development started before the drug was on the market."""
        first = self.first_entry
        return first is not None and (self.marketed_on is None or first < self.marketed_on)

    def furthest_before(self, when: date) -> Stage | None:
        stages = [t.phase for t in self.clinical_trials if t.started < when]
        return max(stages, key=STAGE_ORDER.index) if stages else None

    @property
    def name(self) -> str:
        # Prefer a generic name (letters only) over a code like "ABC-123".
        generic = [n for n, _ in self.names.most_common() if not re.search(r"\d", n)]
        name = (generic or [self.names.most_common(1)[0][0]])[0][:200]
        return name.capitalize() if name.islower() else name

    def stage_dates(self) -> dict[Stage, date]:
        entered: dict[Stage, date] = {}
        for t in self.clinical_trials:
            if t.phase not in entered or t.started < entered[t.phase]:
                entered[t.phase] = t.started
        if self.approved_on:
            entered[Stage.APPROVED] = self.approved_on
            # Filing isn't visible on ClinicalTrials.gov; approval implies it happened.
            entered.setdefault(Stage.REGULATORY, self.approved_on)
        return entered

    def status(self, today: date) -> AssetStatus:
        if self.approved_on:
            return AssetStatus.ACTIVE
        if any(t.overall_status in RUNNING_STATUSES for t in self.trials):
            return AssetStatus.ACTIVE
        last = max((t.last_activity for t in self.trials if t.last_activity), default=None)
        cutoff = date(today.year - INACTIVE_YEARS, today.month, min(today.day, 28))
        return AssetStatus.DISCONTINUED if last is None or last < cutoff else AssetStatus.ACTIVE

    def sponsor(self) -> str | None:
        industry = Counter(
            t.lead_sponsor for t in self.trials if t.sponsor_class == "INDUSTRY" and t.lead_sponsor
        )
        return industry.most_common(1)[0][0] if industry else None

    def indication(self) -> str:
        counts = Counter(c for t in self.trials for c in t.conditions)
        return (counts.most_common(1)[0][0] if counts else "Unspecified")[:300]


def build_programs(trials: Iterable[TrialRow], approvals: dict[str, date] | None = None) -> list[Program]:
    """Group trials into programs. `approvals` maps name_key -> first FDA approval date."""
    approvals = approvals or {}
    aliases = _Aliases()
    trial_drugs: list[tuple[TrialRow, list[tuple[list[str], str, bool]]]] = []
    for t in trials:
        drugs = []
        for intervention in t.interventions:
            for name, others in drug_names(intervention):
                key = name_key(name)
                aliases.find(key)
                for other in others:
                    aliases.union(key, name_key(other))
                drugs.append(([name, *others], key, intervention.get("type") == "BIOLOGICAL"))
        trial_drugs.append((t, drugs))

    # When each drug was first marketed: FDA approval of any alias, or its first Phase 4
    # trial by any sponsor.
    marketed: dict[str, date] = {}

    def mark(root: str, when: date) -> None:
        if root not in marketed or when < marketed[root]:
            marketed[root] = when

    for key in list(aliases.parent):
        if key in approvals:
            mark(aliases.find(key), approvals[key])
    for t, drugs in trial_drugs:
        if t.phase == Stage.APPROVED and t.started:
            for _, key, _ in drugs:
                mark(aliases.find(key), t.started)

    programs: dict[tuple[str, str], Program] = {}
    for t, drugs in trial_drugs:
        if t.sponsor_class != "INDUSTRY":
            continue
        area = classify_area(t.condition_terms, t.conditions)
        for names, key, biological in drugs:
            root = aliases.find(key)
            program = programs.setdefault((root, area), Program(key=f"{root}|{area}"[:200], area=area))
            program.add(t, names, biological)

    by_drug: dict[str, list[Program]] = defaultdict(list)
    for (root, _), program in programs.items():
        by_drug[root].append(program)

    result = []
    for root, drug_programs in by_drug.items():
        # Healthy-volunteer Phase 1 studies have no disease; they belong to the drug's
        # disease programs, not to a separate "other" program that looks like it stalled.
        other = [p for p in drug_programs if p.area == "other"]
        disease = [p for p in drug_programs if p.area != "other"]
        if other and disease:
            for p in disease:
                for t in other[0].trials:
                    p.add(t, [], other[0].biological)
                p.names.update(other[0].names)
            drug_programs = disease

        when = marketed.get(root)
        if when:
            reached = {id(p): p.furthest_before(when) for p in drug_programs}
            furthest = max((STAGE_ORDER.index(s) for s in reached.values() if s is not None), default=None)
            for p in drug_programs:
                p.marketed_on = when
                stage = reached[id(p)]
                if furthest is not None and stage is not None and STAGE_ORDER.index(stage) == furthest:
                    p.approved_on = when
                else:
                    # A Phase 4 trial in this area means it's on the market for this use too.
                    p4 = [t.started for t in p.trials if t.phase == Stage.APPROVED and t.started]
                    p.approved_on = min(p4) if p4 else None
        result += drug_programs
    return result


def load_trials(session: Session) -> Iterable[TrialRow]:
    columns = [
        Trial.id, Trial.phase, Trial.overall_status, Trial.lead_sponsor, Trial.sponsor_class,
        Trial.conditions, Trial.condition_terms, Trial.interventions,
        Trial.start_date, Trial.completion_date, Trial.last_update,
    ]  # fmt: skip
    for row in session.execute(select(*columns).where(Trial.phase.is_not(None))).yield_per(5000):
        yield TrialRow(*row)


def _organizations(session: Session, names: set[str]) -> dict[str, int]:
    existing = dict(session.execute(select(Organization.name, Organization.id)).all())
    missing = [{"name": n[:200], "type": OrgType.COMPANY} for n in names if n not in existing]
    if missing:
        for name, org_id in session.execute(
            insert(Organization).returning(Organization.name, Organization.id), missing
        ):
            existing[name] = org_id
    return existing


def save_programs(session: Session, programs: list[Program], today: date) -> int:
    orgs = _organizations(session, {p.sponsor() for p in programs})
    existing = dict(session.execute(select(Asset.external_key, Asset.id).where(Asset.source == SOURCE)).all())
    rows, history = [], {}
    for p in programs:
        entered = p.stage_dates()
        if not entered:
            continue
        stage = max(entered, key=STAGE_ORDER.index)
        sponsor = p.sponsor()
        rows.append(
            {
                "external_key": p.key,
                "source": SOURCE,
                "name": p.name,
                "synonyms": [n for n, _ in p.names.most_common(10) if n != p.name],
                "modality": guess_modality(p.names, p.biological),
                "therapeutic_area": p.area,
                "indication": p.indication(),
                "stage": stage,
                "status": p.status(today),
                "benchmark_eligible": p.eligible,
                "organization_id": orgs.get(sponsor[:200]) if sponsor else None,
                "summary": _summary(p, sponsor),
            }
        )
        history[p.key] = (entered, [t.id for t in p.trials])

    updates = [{**r, "id": existing[r["external_key"]]} for r in rows if r["external_key"] in existing]
    inserts = [r for r in rows if r["external_key"] not in existing]
    for chunk in _chunks(updates):
        session.execute(update(Asset), chunk)
    ids = {key: existing[key] for key in history if key in existing}
    for chunk in _chunks(inserts):
        for key, asset_id in session.execute(insert(Asset).returning(Asset.external_key, Asset.id), chunk):
            ids[key] = asset_id

    # Programs that no longer appear in the data, unless an owner has listed them.
    listed = select(Listing.asset_id)
    stale = [aid for key, aid in existing.items() if key not in history]
    for chunk in _chunks(stale):
        session.execute(delete(Asset).where(Asset.id.in_(chunk), Asset.id.not_in(listed)))

    ctgov_assets = select(Asset.id).where(Asset.source == SOURCE)
    session.execute(delete(StageEvent).where(StageEvent.asset_id.in_(ctgov_assets)))
    session.execute(delete(AssetTrial).where(AssetTrial.asset_id.in_(ctgov_assets)))
    events, links = [], []
    for key, (entered, trial_ids) in history.items():
        asset_id = ids[key]
        for stage, entered_on in entered.items():
            inferred = stage == Stage.REGULATORY
            events.append(
                {
                    "asset_id": asset_id,
                    "stage": stage,
                    "entered_on": entered_on,
                    "source": "ctgov-inferred" if inferred else SOURCE,
                }
            )
        links += [{"asset_id": asset_id, "trial_id": tid} for tid in set(trial_ids)]
    for chunk in _chunks(events):
        session.execute(insert(StageEvent), chunk)
    for chunk in _chunks(links):
        session.execute(insert(AssetTrial), chunk)
    session.commit()
    return len(rows)


def _summary(p: Program, sponsor: str | None) -> str:
    text = f"Built from {len(p.trials)} ClinicalTrials.gov trial(s). Sponsor: {sponsor}."
    if p.marketed_on and not p.eligible:
        text += f" Drug already on the market since {p.marketed_on.year}; not counted in benchmarks."
    return text


def _chunks(items: list, size: int = 5000):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def run(session: Session, today: date | None = None) -> int:
    today = today or date.today()
    approvals = dict(
        session.execute(select(DrugApproval.ingredient_key, DrugApproval.first_approved_on)).all()
    )
    return save_programs(session, build_programs(load_trials(session), approvals), today)
