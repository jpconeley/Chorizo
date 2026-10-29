# Architecture

Chorizo is built like a market-data terminal. A data layer collects and normalizes facts about
drug programs. An analytics layer turns them into probabilities. An entitlement layer decides
who sees what, and a fast, dense UI sits on top.

```
 ClinicalTrials.gov ─┐                                    ┌─ Web app (Next.js)
 Owner submissions ──┼─> Ingestion jobs ─> Postgres <─> API (FastAPI) ─┤
 Published studies ──┘        │                 ^          │           └─ Institutional API clients
                              v                 │          └─ Stripe (checkout, portal, webhooks)
                         Analytics jobs ────────┘
                   (benchmarks, PoS estimates)
```

## Components

| Part | Where | What it does |
|---|---|---|
| Database | Postgres, schema in `backend/src/chorizo/models.py`, migrations in `backend/migrations` | Single source of truth for accounts, assets, trials, listings and analytics |
| API | `backend/src/chorizo/api` | Versioned REST API (`/v1`). The web app and institutional clients both use it |
| Entitlements | `backend/src/chorizo/plans.py` | Maps plans to features. Routes check features, never plan names |
| Ingestion | `backend/src/chorizo/ingest` | Batch jobs that mirror external sources. Currently ClinicalTrials.gov v2 |
| Analytics | `backend/src/chorizo/analytics` | Stage-transition benchmarks and per-asset probability-of-success models |
| Billing | `backend/src/chorizo/api/routes/billing.py` | Stripe Checkout and Customer Portal. Webhooks keep `subscriptions` in sync |
| Web | `web/` | Server-rendered Next.js. Talks to the API on the server and keeps the session token in an httpOnly cookie |

## Data model

- **Accounts:** `users`, `organizations` (companies, labs, funds), `memberships` and
  `subscriptions`. A subscription belongs to a user or an organization. Members of an
  organization inherit its plan, which is how institutional seats work.
- **Reference:** `assets` (one row per therapy), `stage_events` (each stage it entered and when),
  `trials` (mirrored from ClinicalTrials.gov) and `asset_trials`.
- **Marketplace:** `listings` (a funding request for an asset), `listing_documents` (the data
  room, each document gated by a minimum plan), `investor_interests` and `watchlist_items`.
- **Analytics:** `stage_benchmarks` (versioned by source and `as_of`) and `pos_estimates`
  (versioned by `model_version`, with the inputs stored for auditability).

## From trials to programs

`backend/src/chorizo/ingest/programs.py` turns ClinicalTrials.gov trials into drug programs
(one drug in one therapeutic area, the BIO/Biomedtracker convention):

1. **Drugs per trial:** split combinations ("A + B"), drop placebos and comparators, strip doses,
   formulations and salts, and normalize names so "MK 3475" matches "MK-3475". A trial's "other
   names" link aliases, so a code name and its generic name end up as one drug.
2. **Marketed date:** the drug's first FDA approval (Drugs@FDA, `ingest/fda.py`) or its first
   Phase 4 trial by any sponsor, whichever is earlier.
3. **Programs:** industry-sponsored trials grouped by drug and therapeutic area (from MeSH
   condition terms). Supporting Phase 1 studies (healthy volunteers, liver or kidney impairment,
   drug interactions, bioequivalence, food effect, QT, mass balance) join the same drug's disease
   programs; a drug that only ever had supporting studies gets no program. FDA matching also tries
   brand names and the distinctive words in a name ("Rivaroxaban Xarelto" matches rivaroxaban).
4. **Stage history and approval:** the first trial start in each phase. The program(s) that got
   furthest before the drug was marketed are marked approved on the marketed date; other programs
   only count as approved if they have their own Phase 4 trial.
5. **Status:** discontinued when no trial is running and nothing has happened for three years;
   otherwise active.
6. **Benchmark eligibility:** only programs that started before the drug was marketed count
   toward success rates. Comparators, probe drugs in interaction studies, background therapy and
   new uses of old drugs are still shown, but would otherwise appear as thousands of "failed"
   programs. Vaccines, cell and gene therapies and blood products are excluded too: FDA's CBER
   approves them and they aren't in Drugs@FDA, so every one would look like a failure. So are
   programs whose name doesn't identify a specific drug (a code like "AZD1656" or a distinctive
   name like "faldaprevir"): fragments such as "Suppositories" or "EMS association" usually come
   from new forms of old products by generic or consumer-health companies.

`chorizo diagnose` prints how programs are classified and what the counted failures at each
stage have in common, with examples. Use it whenever the rates look off.

Known limits, roughly in order of impact:

- Approvals outside the US are only detected through Phase 4 trials, so drugs approved only in
  Europe, Japan or China look like failures.
- Benchmarks cover drugs and therapeutic biologics, not vaccines, cell and gene therapies or
  blood products.
- Filings aren't on ClinicalTrials.gov, so our Phase 3 rate runs all the way to approval. Compare
  it with BIO's Phase 3 × filing rate (49.6% for 2006–2015), not their Phase 3 → filing 58.1%.
- A Phase 3 outcome only counts if the program had a Phase 2 trial first. Programs that start at
  Phase 3 are nearly always biosimilars, new forms of old drugs or repackaged products.
- Name matching is heuristic; some aliases won't merge and a few unrelated names may.
- Programs started recently are still undecided and don't count yet (right-censoring).
- New indications of already-approved drugs aren't benchmarked, so rates describe new drugs.

## Probability of success

1. **Benchmarks.** For every program we count each stage it left by advancing (a success) and
   the last stage of every discontinued program (a failure). Programs still in progress don't
   count yet. A stage only counts as passed if a later stage started on or after it, so a new
   Phase 2 study of an already-approved drug isn't scored as a Phase 2 success. Rates are computed
   overall, by therapeutic area, and by area plus modality, from ClinicalTrials.gov programs only.
   The published BIO/Biomedtracker 2006–2015 figures stay alongside as a reference and fill in
   any rate we have too little data for.
2. **Likelihood of approval** from a stage is the product of the remaining transition rates.
3. **Per-asset estimate (model `v0-benchmark`).** For each remaining stage, use the most specific
   benchmark with at least 30 programs behind it, and chain them together. Discontinued programs
   get no estimate. Future models add
   asset-level adjustments, such as biomarker selection, orphan status, sponsor track record and
   trial design, and bump the version. Old estimates are kept for back-testing.

## Subscription plans

| Plan | For | Unlocks |
|---|---|---|
| Free | Anyone | Browse assets and listings, headline stage success rates |
| Pro | Individual investors | Per-asset PoS, benchmarks by area and modality, watchlists, contacting owners, gated documents |
| Institutional (per seat) | Funds, family offices, pharma BD | Everything in Pro, plus CSV export, API access and full model inputs |
| Sponsor | Companies and labs | List assets for funding, investor-interest analytics, benchmark drill-down |

Prices are set in Stripe and referenced by `CHORIZO_STRIPE_PRICE_*`. When a user hits a paywall,
the API returns `403 {"code": "upgrade_required", "feature": ..., "plan": ...}` and the UI shows
an upgrade prompt.

## Roadmap

1. **Analytics terminal:** FDA approval data to confirm approvals, better drug-name matching,
   more sources (SEC filings), alerts on stage changes.
2. **Owner listings:** organization verification, listing editor, data-room uploads, interest
   analytics for sponsors.
3. **Funding:** transactions through a registered funding portal or broker-dealer partner
   (Reg CF / Reg A+ / Reg D), after legal review.
