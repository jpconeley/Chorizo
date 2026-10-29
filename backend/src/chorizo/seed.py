"""Reference data and local demo data."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from chorizo.models import (
    Asset,
    AssetStatus,
    InvestorInterest,
    Listing,
    ListingDocument,
    ListingStatus,
    MemberRole,
    Membership,
    Modality,
    Organization,
    OrgType,
    Stage,
    StageBenchmark,
    StageEvent,
    Subscription,
    SubscriptionStatus,
    User,
    WatchlistItem,
)
from chorizo.plans import Plan
from chorizo.security import hash_password

# Thomas et al., "Clinical Development Success Rates 2006-2015", BIO/Biomedtracker/Amplion (2016).
# All therapeutic areas and modalities; n = phase transitions observed.
BIO_2016_SOURCE = "BIO/Biomedtracker 2006-2015"
BIO_2016 = [
    (Stage.PHASE1, 0.632, 3582),
    (Stage.PHASE2, 0.307, 3862),
    (Stage.PHASE3, 0.581, 1491),
    (Stage.REGULATORY, 0.853, 1050),
]


def seed_reference(session: Session) -> int:
    if session.scalar(select(StageBenchmark).where(StageBenchmark.source == BIO_2016_SOURCE)):
        return 0
    loa = 1.0
    rows = []
    for stage, p, n in reversed(BIO_2016):
        loa *= p
        rows.append(
            StageBenchmark(
                stage=stage,
                therapeutic_area=None,
                modality=None,
                transition_probability=p,
                likelihood_of_approval=round(loa, 4),
                sample_size=n,
                source=BIO_2016_SOURCE,
                as_of=date(2016, 2, 1),
            )
        )
    session.add_all(rows)
    session.commit()
    return len(rows)


DEMO_PASSWORD = "chorizo-demo-pass"

# Fictional assets so the UI has something to show locally. Never load in production.
_DEMO_ASSETS = [
    ("DEMO-101", Modality.SMALL_MOLECULE, "KRAS G12D", "oncology", "Pancreatic cancer", Stage.PHASE1),
    ("DEMO-204", Modality.ANTIBODY, "IL-23", "immunology", "Ulcerative colitis", Stage.PHASE2),
    ("DEMO-317", Modality.GENE_THERAPY, "SMN1", "neurology", "Spinal muscular atrophy", Stage.PRECLINICAL),
    ("DEMO-422", Modality.RNA, "PCSK9", "cardiovascular", "Hypercholesterolemia", Stage.PHASE3),
    ("DEMO-530", Modality.CELL_THERAPY, "CD19", "oncology", "B-cell lymphoma", Stage.PHASE2),
    ("DEMO-611", Modality.PROTEIN, "GLP-1R", "metabolic", "Obesity", Stage.REGULATORY),
]


def seed_demo(session: Session) -> None:
    if session.scalar(select(Organization).where(Organization.name == "Demo Therapeutics")):
        return
    org = Organization(name="Demo Therapeutics", type=OrgType.COMPANY, verified=True)
    session.add(org)
    session.flush()

    order = list(Stage)
    for i, (name, modality, target, area, indication, stage) in enumerate(_DEMO_ASSETS):
        asset = Asset(
            organization_id=org.id,
            name=name,
            modality=modality,
            target=target,
            therapeutic_area=area,
            indication=indication,
            stage=stage,
            status=AssetStatus.ACTIVE,
            source="demo",
            summary=f"Demo {modality.value.replace('_', ' ')} targeting {target} for {indication.lower()}.",
        )
        session.add(asset)
        session.flush()
        for j, s in enumerate(order[: order.index(stage) + 1]):
            session.add(
                StageEvent(asset_id=asset.id, stage=s, entered_on=date(2018 + j, 1 + i, 1), source="demo")
            )

    users = {}
    for plan in [Plan.FREE, Plan.PRO, Plan.INSTITUTIONAL, Plan.SPONSOR]:
        user = User(
            email=f"{plan.value}@chorizo-demo.example.com", password_hash=hash_password(DEMO_PASSWORD)
        )
        session.add(user)
        session.flush()
        users[plan] = user
        if plan != Plan.FREE:
            session.add(Subscription(user_id=user.id, plan=plan.value, status=SubscriptionStatus.ACTIVE))
    session.add(Membership(user_id=users[Plan.SPONSOR].id, organization_id=org.id, role=MemberRole.OWNER))

    first = session.scalar(select(Asset).where(Asset.name == "DEMO-204"))
    listing = Listing(
        asset_id=first.id,
        created_by_id=users[Plan.SPONSOR].id,
        status=ListingStatus.OPEN,
        headline="Phase 2 IL-23 antibody seeking $25M to complete dose-ranging study",
        amount_sought_usd=25_000_000,
        use_of_funds="Complete Phase 2b enrolment and readout.",
        deal_types=["equity", "licensing"],
        pitch="Demo listing for local development.",
    )
    session.add(listing)
    session.flush()
    session.add_all(
        [
            ListingDocument(
                listing_id=listing.id, title="Overview deck", kind="deck", url="https://example.com/deck.pdf"
            ),
            ListingDocument(
                listing_id=listing.id,
                title="Phase 1 data readout",
                kind="data",
                url="https://example.com/p1.pdf",
                min_plan=Plan.PRO.value,
            ),
        ]
    )
    session.commit()


def seed_demo_activity(session: Session) -> None:
    """Give the institutional demo user something on their dashboard: a few followed drugs
    (demo ones plus the real programs with the latest Phase 3 or approval moves) and an
    offer on the demo listing. Safe to run repeatedly; adds only what's missing."""
    user = session.scalar(select(User).where(User.email == "institutional@chorizo-demo.example.com"))
    if user is None:
        return
    demo = list(session.scalars(select(Asset.id).where(Asset.name.in_(["DEMO-204", "DEMO-422", "DEMO-611"]))))
    recent = list(
        session.scalars(
            select(StageEvent.asset_id)
            .join(Asset, Asset.id == StageEvent.asset_id)
            .where(
                Asset.source == "ctgov",
                StageEvent.stage.in_([Stage.PHASE3, Stage.APPROVED]),
                StageEvent.entered_on <= date.today(),
            )
            .order_by(StageEvent.entered_on.desc())
            .limit(20)
        )
    )
    wanted = demo + list(dict.fromkeys(recent))[:3]
    have = set(session.scalars(select(WatchlistItem.asset_id).where(WatchlistItem.user_id == user.id)))
    session.add_all(WatchlistItem(user_id=user.id, asset_id=a) for a in wanted if a not in have)

    listing = session.scalar(
        select(Listing).join(Asset, Asset.id == Listing.asset_id).where(Asset.name == "DEMO-204")
    )
    already = listing and session.scalar(
        select(InvestorInterest).where(
            InvestorInterest.listing_id == listing.id, InvestorInterest.user_id == user.id
        )
    )
    if listing and not already:
        session.add(
            InvestorInterest(
                listing_id=listing.id,
                user_id=user.id,
                message="Interested in leading the Phase 2b round; can we see the dose-ranging data?",
                indicative_amount_usd=5_000_000,
            )
        )
    session.commit()
