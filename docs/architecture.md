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

## Probability of success

1. **Benchmarks.** For every program we count each stage it left by advancing (a success) and
   the last stage of every discontinued program (a failure). Programs still in progress don't
   count yet. Rates are computed overall, by therapeutic area, and by area plus modality. The
   published BIO/Biomedtracker 2006–2015 figures are loaded as a reference until our own history
   is big enough.
2. **Likelihood of approval** from a stage is the product of the remaining transition rates.
3. **Per-asset estimate (model `v0-benchmark`).** For each remaining stage, use the most specific
   benchmark with at least 30 programs behind it, and chain them together. Future models add
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

1. **Analytics terminal:** bulk ClinicalTrials.gov import, matching trials to assets, more
   sources (FDA approvals, SEC filings), alerts on stage changes.
2. **Owner listings:** organization verification, listing editor, data-room uploads, interest
   analytics for sponsors.
3. **Funding:** transactions through a registered funding portal or broker-dealer partner
   (Reg CF / Reg A+ / Reg D), after legal review.
