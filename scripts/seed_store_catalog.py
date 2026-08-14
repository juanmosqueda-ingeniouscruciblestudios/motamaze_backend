#!/usr/bin/env python3
"""
scripts/seed_store_catalog.py

Seeds/updates the config/catalog document that GET /store/catalog reads from
(T-240, architecture doc §9A.4). Idempotent — uses Firestore .set() on a
fixed document ID, safe to re-run any time the catalog needs updating.

Only products with a REAL, confirmed price are included. skin_gold,
skin_silver, and the large life pack are still "TBD" in the architecture
doc's own pricing table (2026-06-04, lines 737-740) — REST-001's example
payload shows placeholder numbers for those to illustrate the response
shape, not approved pricing. Do not add them here until Juan confirms
real prices; inventing one would show a wrong charge to real players.

season_pass_gold added 2026-08-14: $4.99 confirmed in approved UI art
(motamaze-project/docs/media/ui_screen_roadmap.md:52-53 — Store screen
"Best Value" callout + Season Pass screen "UNLOCK GOLD PASS $4.99"), not
just noted somewhere — the purchase path was already fully built
(payments.py, reconcile_service.py, REST-001 §2099) but had no price seeded
anywhere. The $9.99 in seed_bq_test_data.py is unrelated fixture noise, not
a competing real price.

Do NOT seed any lives_pack_10/50/100 or a cosmetic product here yet — the
approved Store UI advertises those but they don't exist in code, and
lives_pack_5 (which exists) doesn't appear in that UI. Product IDs are
permanent once created in either store; seeding a guess would burn an ID
nobody ends up using. Juan flagged this reconciliation as still open
(2026-08-13).

config/promotions/{promo_id} is intentionally left empty by this script —
no promotion is active yet. GET /store/catalog treats "no matching active
promotion" as a normal, valid state.

Usage:
    gcloud auth application-default login --project motamaze-dev   # or motamaze for prod
    python scripts/seed_store_catalog.py --project motamaze-dev
"""

import argparse
from datetime import date

from google.cloud import firestore

# Only products with a confirmed price in BOTH the architecture doc's pricing
# table and REST-001's contract. See module docstring for what's excluded and why.
PRODUCTS = [
    {
        "product_id": "lives_pack_5",
        "type": "consumable",
        "display_name": "5 Extra Lives",
        "description": "Keep playing with 5 extra lives",
        "price_usd": 0.99,
        "currency": "USD",
        "lives_granted": 5,
        "display_order": 1,
        "visible": True,
        "badge": None,
    },
    {
        "product_id": "no_ads",
        "type": "non_consumable",
        "display_name": "Remove Ads",
        "description": "Remove all ads permanently",
        "price_usd": 2.99,
        "currency": "USD",
        "lives_granted": None,
        "display_order": 2,
        "visible": True,
        "badge": None,
    },
    {
        "product_id": "season_pass_gold",
        "type": "non_consumable",
        "display_name": "Gold Pass",
        "description": "Unlock the Gold track rewards for this season's pass",
        "price_usd": 4.99,
        "currency": "USD",
        "lives_granted": None,
        "display_order": 3,
        "visible": True,
        "badge": "BEST VALUE",
    },
]


def main(project: str) -> None:
    client = firestore.Client(project=project)
    ref = client.collection("config").document("catalog")
    # catalog_version = today's date, per REST-001: "the client can cache if
    # the version hasn't changed" — re-running this script IS how the
    # catalog gets updated, so bumping it here on every run is correct, not
    # a magic/separate value to remember to update.
    ref.set({"products": PRODUCTS, "catalog_version": date.today().isoformat()})

    doc = ref.get().to_dict()
    print(f"config/catalog seeded in project={project} (catalog_version={doc['catalog_version']})")
    print(f"  {len(doc['products'])} products:")
    for p in doc["products"]:
        print(f"    {p['product_id']:15s} {p['type']:15s} ${p['price_usd']:.2f} {p['currency']}")
    print()
    print("Excluded (TBD pricing, not seeded): skin_gold, skin_silver, life_pack_large")
    print("config/promotions/{promo_id}: left empty, no active promotion yet")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, choices=["motamaze-dev", "motamaze"])
    args = parser.parse_args()
    main(args.project)
