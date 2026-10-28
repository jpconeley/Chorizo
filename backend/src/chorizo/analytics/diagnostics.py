"""A compact report on how imported programs are classified, to sanity-check benchmarks.

Run with `chorizo diagnose`. Each section asks a specific question about the
programs counted as failures, so a skewed rate can be traced to its cause.
"""

from collections import Counter, defaultdict
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from chorizo.ingest.programs import SOURCE, name_key
from chorizo.models import (
    STAGE_ORDER,
    Asset,
    AssetStatus,
    AssetTrial,
    DrugApproval,
    Organization,
    Stage,
    StageEvent,
)

CLINICAL = [Stage.PHASE1, Stage.PHASE2, Stage.PHASE3]


def _pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:.0f}%" if whole else "-"


def report(session: Session) -> str:
    approvals = set(session.scalars(select(DrugApproval.ingredient_key)))
    rows = session.execute(
        select(
            Asset.id,
            Asset.external_key,
            Asset.name,
            Asset.synonyms,
            Asset.therapeutic_area,
            Asset.stage,
            Asset.status,
            Asset.benchmark_eligible,
            Asset.summary,
            Organization.name,
        )
        .outerjoin(Organization, Asset.organization_id == Organization.id)
        .where(Asset.source == SOURCE)
    ).all()
    trial_counts = dict(
        session.execute(select(AssetTrial.asset_id, func.count()).group_by(AssetTrial.asset_id)).all()
    )
    first_entry: dict[tuple[int, Stage], date] = {}
    for asset_id, stage, on in session.execute(
        select(StageEvent.asset_id, StageEvent.stage, StageEvent.entered_on)
    ):
        key = (asset_id, stage)
        if key not in first_entry or on < first_entry[key]:
            first_entry[key] = on

    # Furthest stage each drug reached in any area, and whether it's approved anywhere.
    drug_of = {r.id: r.external_key.split("|")[0] for r in rows}
    furthest: dict[str, int] = defaultdict(int)
    for r in rows:
        furthest[drug_of[r.id]] = max(furthest[drug_of[r.id]], STAGE_ORDER.index(r.stage))

    eligible = [r for r in rows if r.benchmark_eligible]
    excluded = [r for r in rows if not r.benchmark_eligible]
    cber = sum("vaccines" in (r.summary or "") for r in excluded)
    out = [
        f"FDA-approved ingredients and brands loaded: {len(approvals):,}",
        f"Programs: {len(rows):,} total, {len(eligible):,} counted in benchmarks; excluded: "
        f"{len(excluded) - cber:,} already-marketed drugs, {cber:,} vaccines/cell/gene therapies",
        "",
        "Counted programs by furthest stage (active / discontinued):",
    ]
    for stage in STAGE_ORDER[2:]:
        at = [r for r in eligible if r.stage == stage]
        stopped = sum(r.status == AssetStatus.DISCONTINUED for r in at)
        out.append(f"  {stage.value:<11} {len(at) - stopped:>7,} / {stopped:>7,}")

    for stage in CLINICAL:
        failed = [r for r in eligible if r.stage == stage and r.status == AssetStatus.DISCONTINUED]
        n = len(failed)
        elsewhere = sum(furthest[drug_of[r.id]] > STAGE_ORDER.index(stage) for r in failed)
        names = lambda r: [r.name, *(r.synonyms or [])]  # noqa: E731
        fda_named = sum(any(name_key(x) in approvals for x in names(r)) for r in failed)
        started = [first_entry.get((r.id, stage)) for r in failed]
        recent = sum(1 for d in started if d and d.year >= 2016)
        old = sum(1 for d in started if d and d.year < 2008)
        single = sum(trial_counts.get(r.id, 0) == 1 for r in failed)
        out += [
            "",
            f"{stage.value} failures counted: {n:,}",
            f"  same drug got further in another area: {_pct(elsewhere, n)}",
            f"  a name matches an FDA-approved ingredient: {_pct(fda_named, n)}",
            f"  only one trial in the program: {_pct(single, n)}",
            f"  entered this stage before 2008: {_pct(old, n)}, in 2016 or later: {_pct(recent, n)}",
        ]
        sponsors = Counter(r.name_1 for r in failed if r.name_1).most_common(8)
        out.append("  top sponsors: " + ", ".join(f"{s} ({c})" for s, c in sponsors))
        sample = sorted(failed, key=lambda r: -trial_counts.get(r.id, 0))[:12]
        out.append("  most-tested examples (name | area | sponsor | trials | entered):")
        for r in sample:
            when = first_entry.get((r.id, stage))
            out.append(
                f"    {r.name[:28]:<28} | {r.therapeutic_area[:12]:<12} | {(r.name_1 or '-')[:24]:<24} | "
                f"{trial_counts.get(r.id, 0):>4} | {when.year if when else '-'}"
            )
        singles = [r for r in failed if trial_counts.get(r.id, 0) == 1]
        out.append("  random single-trial examples (name | area | sponsor | entered):")
        for r in sorted(singles, key=lambda r: (r.id * 2654435761) % 2**32)[:12]:
            when = first_entry.get((r.id, stage))
            out.append(
                f"    {r.name[:28]:<28} | {r.therapeutic_area[:12]:<12} | {(r.name_1 or '-')[:24]:<24} | "
                f"{when.year if when else '-'}"
            )
    return "\n".join(out)
