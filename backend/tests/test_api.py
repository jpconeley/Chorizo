from sqlalchemy import select

from chorizo.api.routes.billing import apply_subscription_event
from chorizo.models import Asset, Listing, User
from chorizo.plans import Feature, Plan, cheapest_plan_with, features_for


def _asset_id(session, name: str) -> int:
    return session.scalar(select(Asset.id).where(Asset.name == name))


def test_plan_features_are_unioned():
    features = features_for({Plan.PRO, Plan.SPONSOR})
    assert Feature.ASSET_POS in features and Feature.CREATE_LISTINGS in features
    assert Feature.API_ACCESS not in features
    assert cheapest_plan_with(Feature.ASSET_POS) == Plan.PRO
    assert cheapest_plan_with(Feature.API_ACCESS) == Plan.INSTITUTIONAL


def test_register_login_and_me(client):
    r = client.post("/v1/auth/register", json={"email": "New@Example.com", "password": "long-enough-pw"})
    assert r.status_code == 201
    token = r.json()["access_token"]
    me = client.get("/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert me["email"] == "new@example.com"
    assert me["plans"] == []
    assert "asset_pos" not in me["features"]

    dup = client.post("/v1/auth/register", json={"email": "new@example.com", "password": "long-enough-pw"})
    assert dup.status_code == 409


def test_browse_assets_is_free(client):
    page = client.get("/v1/assets", params={"stage": "phase2"}).json()
    assert page["total"] == 2
    assert {a["name"] for a in page["items"]} == {"DEMO-204", "DEMO-530"}


def test_asset_pos_requires_paid_plan(client, seeded, login):
    asset_id = _asset_id(seeded, "DEMO-204")

    anon = client.get(f"/v1/assets/{asset_id}/pos")
    assert anon.status_code == 403
    assert anon.json()["detail"] == {"code": "upgrade_required", "feature": "asset_pos", "plan": "pro"}

    pro = client.get(f"/v1/assets/{asset_id}/pos", headers=login("pro")).json()
    assert round(pro["next_stage_probability"], 3) == 0.307
    assert pro["inputs"] is None  # model inputs are institutional-only

    inst = client.get(f"/v1/assets/{asset_id}/pos", headers=login("institutional")).json()
    assert inst["inputs"]["phase2"]["source"].startswith("BIO")


def test_benchmark_drilldown_is_gated(client, login):
    overall = client.get("/v1/benchmarks").json()
    assert [b["stage"] for b in overall] == ["phase1", "phase2", "phase3", "regulatory"]

    assert client.get("/v1/benchmarks", params={"therapeutic_area": "oncology"}).status_code == 403
    r = client.get("/v1/benchmarks", params={"therapeutic_area": "oncology"}, headers=login("pro"))
    assert r.status_code == 200


def test_export_requires_institutional(client, login):
    assert client.get("/v1/assets/export.csv", headers=login("pro")).status_code == 403
    r = client.get("/v1/assets/export.csv", headers=login("institutional"))
    assert r.status_code == 200
    assert r.text.splitlines()[0].startswith("id,name,modality")


def test_gated_listing_documents(client, seeded, login):
    listing_id = seeded.scalar(select(Listing.id))
    free_docs = client.get(f"/v1/listings/{listing_id}").json()["documents"]
    locked = {d["title"]: d["locked"] for d in free_docs}
    assert locked == {"Overview deck": False, "Phase 1 data readout": True}
    assert all(d["url"] is None for d in free_docs if d["locked"])

    pro_docs = client.get(f"/v1/listings/{listing_id}", headers=login("pro")).json()["documents"]
    assert not any(d["locked"] for d in pro_docs)


def test_only_org_members_with_sponsor_plan_can_list(client, seeded, login):
    body = {"asset_id": _asset_id(seeded, "DEMO-101"), "headline": "Seeking seed round"}
    assert client.post("/v1/listings", json=body, headers=login("pro")).status_code == 403
    r = client.post("/v1/listings", json=body, headers=login("sponsor"))
    assert r.status_code == 201
    assert r.json()["asset"]["name"] == "DEMO-101"


def test_express_interest_once(client, seeded, login):
    listing_id = seeded.scalar(select(Listing.id))
    headers = login("pro")
    assert client.post(f"/v1/listings/{listing_id}/interest", json={}, headers=headers).status_code == 201
    assert client.post(f"/v1/listings/{listing_id}/interest", json={}, headers=headers).status_code == 409


def test_watchlist(client, seeded, login):
    asset_id = _asset_id(seeded, "DEMO-422")
    assert client.put(f"/v1/watchlist/{asset_id}").status_code == 403
    headers = login("pro")
    assert client.put(f"/v1/watchlist/{asset_id}", headers=headers).status_code == 204
    assert [a["name"] for a in client.get("/v1/watchlist", headers=headers).json()] == ["DEMO-422"]
    client.delete(f"/v1/watchlist/{asset_id}", headers=headers)
    assert client.get("/v1/watchlist", headers=headers).json() == []


def test_subscription_webhook_grants_and_revokes_access(client, seeded, login):
    user = seeded.scalar(select(User).where(User.email == "free@chorizo-demo.example.com"))
    headers = login("free")
    event = {
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_123",
                "status": "active",
                "metadata": {"user_id": str(user.id), "plan": "pro"},
                "items": {"data": [{"quantity": 1, "current_period_end": 1893456000}]},
            }
        },
    }
    assert apply_subscription_event(seeded, event)
    assert "asset_pos" in client.get("/v1/me", headers=headers).json()["features"]

    event["type"] = "customer.subscription.deleted"
    event["data"]["object"]["status"] = "canceled"
    assert apply_subscription_event(seeded, event)
    assert "asset_pos" not in client.get("/v1/me", headers=headers).json()["features"]


def test_market_stats_and_feed(client):
    stats = client.get("/v1/market/stats", params={"years": 10}).json()
    assert stats["programs"] == 6 and stats["active"] == 6
    pipeline = {row["stage"]: row["count"] for row in stats["pipeline"]}
    assert pipeline["phase2"] == 2 and pipeline["regulatory"] == 1
    assert len(stats["approvals_by_year"]) == 10

    feed = client.get("/v1/market/feed", params={"limit": 5}).json()
    assert len(feed) == 5
    assert feed == sorted(feed, key=lambda e: e["on"], reverse=True)
    assert all(e["stage"] != "regulatory" for e in feed)
    assert feed[0]["sponsor"] == "Demo Therapeutics"


def test_search_matches_sponsor_and_ranks_prefix_first(client):
    by_sponsor = client.get("/v1/assets", params={"q": "demo thera"}).json()
    assert by_sponsor["total"] == 6
    ranked = client.get("/v1/assets", params={"q": "DEMO-2"}).json()["items"]
    assert ranked[0]["name"] == "DEMO-204"


def test_dashboard_for_investor_and_sponsor(client, seeded, login):
    assert client.get("/v1/me/dashboard").status_code == 401

    investor = client.get("/v1/me/dashboard", headers=login("institutional")).json()
    following = {f["asset"]["name"]: f for f in investor["following"]}
    assert set(following) == {"DEMO-204", "DEMO-422", "DEMO-611"}  # no ctgov programs in the test data
    assert following["DEMO-422"]["latest"]["stage"] == "phase3"
    assert following["DEMO-204"]["next_stage_probability"] is not None  # institutional sees PoS
    assert [o["asset"] for o in investor["offers"]] == ["DEMO-204"]
    kinds = {a["kind"] for a in investor["activity"]}
    assert {"stage", "followed", "offer_sent"} <= kinds
    moves = [a["asset"] for a in investor["activity"] if a["kind"] == "stage"]
    assert sorted(moves) == sorted(set(moves))  # one latest move per followed drug
    assert investor["activity"] == sorted(investor["activity"], key=lambda a: a["on"], reverse=True)

    sponsor = client.get("/v1/me/dashboard", headers=login("sponsor")).json()
    assert [(row["asset"], row["interest_count"]) for row in sponsor["listings"]] == [("DEMO-204", 1)]
    assert sponsor["interest_received"][0]["investor"] == "institutional@chorizo-demo.example.com"
    assert {"listing_created", "interest_received"} <= {a["kind"] for a in sponsor["activity"]}


def test_demo_activity_is_idempotent(seeded):
    from sqlalchemy import func

    from chorizo import seed
    from chorizo.models import InvestorInterest, WatchlistItem

    before = (
        seeded.scalar(select(func.count(WatchlistItem.id))),
        seeded.scalar(select(func.count(InvestorInterest.id))),
    )
    seed.seed_demo_activity(seeded)
    after = (
        seeded.scalar(select(func.count(WatchlistItem.id))),
        seeded.scalar(select(func.count(InvestorInterest.id))),
    )
    assert before == after
