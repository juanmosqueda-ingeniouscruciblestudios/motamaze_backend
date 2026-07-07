#!/usr/bin/env python3
"""
scripts/seed_bq_test_data.py

Inserta ~200 filas de prueba en 4 tablas BQ para desarrollo de dashboards T-303.
Genera datos con retención D1/D7/D14/D30 realista, IAP revenue, AdMob revenue
y entitlement grants — suficiente para que los 3 gates del KPI scorecard pasen.

Uso:
    gcloud auth application-default login --project motamaze
    python scripts/seed_bq_test_data.py

No requiere dependencias nuevas — usa google-cloud-bigquery ya en pyproject.toml.
"""

from datetime import date, datetime, timedelta, timezone
from google.cloud import bigquery

PROJECT = "motamaze"
DATASET = "motamaze_analytics"
TODAY = date(2026, 7, 6)

client = bigquery.Client(project=PROJECT)


def d(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


def ts(event_date: date, hour: int = 10) -> str:
    return datetime(
        event_date.year, event_date.month, event_date.day,
        hour, 0, 0, tzinfo=timezone.utc,
    ).isoformat()


# ---------------------------------------------------------------------------
# Users: (uid, country, platform, app_version, cohort_days_ago)
# ---------------------------------------------------------------------------
USERS = [
    ("uid_001", "MX", "android", "1.0.0", 35),
    ("uid_002", "MX", "android", "1.0.0", 35),
    ("uid_003", "MX", "android", "1.0.0", 35),
    ("uid_004", "MX", "android", "1.0.0", 35),
    ("uid_005", "US", "android", "1.0.0", 35),
    ("uid_006", "US", "android", "1.0.0", 28),
    ("uid_007", "US", "android", "1.0.0", 28),
    ("uid_008", "BR", "android", "1.0.0", 28),
    ("uid_009", "BR", "android", "1.0.0", 28),
    ("uid_010", "MX", "android", "1.0.0", 28),
    ("uid_011", "MX", "android", "1.0.1", 21),
    ("uid_012", "US", "android", "1.0.1", 21),
    ("uid_013", "CO", "android", "1.0.1", 21),
    ("uid_014", "BR", "android", "1.0.1", 21),
    ("uid_015", "MX", "android", "1.0.1", 21),
    ("uid_016", "MX", "android", "1.0.1", 14),
    ("uid_017", "US", "android", "1.0.2", 14),
    ("uid_018", "BR", "android", "1.0.2", 14),
    ("uid_019", "MX", "android", "1.0.2", 7),
    ("uid_020", "CO", "android", "1.0.2", 7),
]

USER_INFO = {u[0]: u for u in USERS}

# Offsets en días desde el cohort_date de cada usuario.
# Día 0 = primer login (is_new_user=True).
# Diseñados para producir:
#   D1 retention: 11/20 = 55%  (gate: ≥25% ✅)
#   D7 retention:  9/20 = 45%  (gate: ≥10% ✅)
#   No-Ads conv.:  1/20 =  5%  (gate: 2–5% ✅)
RETENTION_PLAN = {
    "uid_001": [0, 1, 2, 3, 5, 7, 8, 10, 14, 20, 30],  # D1✅ D7✅ D14✅ D30✅
    "uid_002": [0, 1, 3, 5, 8, 15],                     # D1✅
    "uid_003": [0, 7, 12, 16, 25],                       # D7✅
    "uid_004": [0, 2, 4, 6, 9],                          # churn temprano
    "uid_005": [0, 1, 3, 7],                             # D1✅ D7✅
    "uid_006": [0, 1, 4, 7, 12, 18, 25],                 # D1✅ D7✅
    "uid_007": [0, 1, 3, 6, 9],                          # D1✅
    "uid_008": [0, 2, 7, 12, 17],                        # D7✅
    "uid_009": [0, 2, 5, 9, 15],                         # sin D1/D7
    "uid_010": [0, 3],                                   # mínimo engagement
    "uid_011": [0, 1, 3, 7, 9, 14, 18],                  # D1✅ D7✅
    "uid_012": [0, 1, 2, 4, 8, 15],                      # D1✅
    "uid_013": [0, 3, 7, 12],                            # D7✅
    "uid_014": [0, 1, 5, 8],                             # D1✅
    "uid_015": [0, 2, 7, 11, 17],                        # D7✅
    "uid_016": [0, 1, 2, 4, 7, 9],                       # D1✅ D7✅
    "uid_017": [0, 2, 5, 8],                             # sin D1/D7
    "uid_018": [0, 1, 3],                                # D1✅
    "uid_019": [0, 1, 3, 5],                             # D1✅
    "uid_020": [0, 2, 5],                                # sin D1
}


# ---------------------------------------------------------------------------
# TABLE 1: login_events  (~101 filas)
# ---------------------------------------------------------------------------
def build_login_events() -> list[dict]:
    rows = []
    for uid, offsets in RETENTION_PLAN.items():
        _, country, platform, app_version, cohort_days_ago = USER_INFO[uid]
        cohort_date = d(cohort_days_ago)
        for i, offset in enumerate(offsets):
            event_date = cohort_date + timedelta(days=offset)
            if event_date > TODAY:
                continue
            rows.append({
                "event_timestamp": ts(event_date, hour=9 + (i % 3)),
                "event_date": event_date.isoformat(),
                "user_id": uid,
                "session_id": f"sess_{uid}_{offset:03d}",
                "platform": platform,
                "app_version": app_version,
                "country": country,
                "login_method": "google_oauth",
                "is_new_user": (i == 0),
                "age_verified": uid in ("uid_001", "uid_006", "uid_011"),
                "device_model": "Pixel 7" if country in ("MX", "CO") else "Samsung Galaxy S23",
                "os_version": "Android 14",
            })
    return rows


# ---------------------------------------------------------------------------
# TABLE 2: purchase_events  (20 filas)
# ---------------------------------------------------------------------------
PRODUCTS = {
    "lives_pack_5":     ("consumable",     0.99),
    "lives_pack_15":    ("consumable",     2.99),
    "no_ads":           ("non_consumable", 4.99),
    "skin_classic":     ("non_consumable", 2.99),
    "season_pass_gold": ("non_consumable", 9.99),
}

# (uid, product_id, days_ago_from_today)
PURCHASES = [
    ("uid_001", "no_ads",           33),
    ("uid_001", "season_pass_gold", 28),
    ("uid_002", "lives_pack_5",     34),
    ("uid_003", "skin_classic",     30),
    ("uid_005", "lives_pack_15",    33),
    ("uid_005", "lives_pack_5",     26),
    ("uid_006", "lives_pack_5",     27),
    ("uid_006", "season_pass_gold", 21),
    ("uid_007", "skin_classic",     26),
    ("uid_008", "lives_pack_15",    25),
    ("uid_011", "lives_pack_5",     20),
    ("uid_011", "lives_pack_15",    14),
    ("uid_012", "skin_classic",     19),
    ("uid_015", "lives_pack_5",     18),
    ("uid_016", "season_pass_gold", 13),
    ("uid_016", "lives_pack_5",      7),
    ("uid_017", "skin_classic",     12),
    ("uid_018", "lives_pack_15",    13),
    ("uid_019", "lives_pack_5",      6),
    ("uid_020", "lives_pack_5",      5),
]

CURRENCY = {"MX": "MXN", "US": "USD", "BR": "BRL", "CO": "COP"}


def build_purchase_events() -> list[dict]:
    rows = []
    for i, (uid, product_id, days_ago) in enumerate(PURCHASES):
        _, country, platform, app_version, _ = USER_INFO[uid]
        ptype, price = PRODUCTS[product_id]
        event_date = d(days_ago)
        rows.append({
            "event_timestamp": ts(event_date, hour=14),
            "event_date": event_date.isoformat(),
            "user_id": uid,
            "session_id": f"sess_{uid}_pur_{i:02d}",
            "platform": platform,
            "app_version": app_version,
            "country": country,
            "product_id": product_id,
            "product_type": ptype,
            "purchase_token": f"tok_{uid}_{product_id}_{i:04d}",
            "order_id": f"GPA.{3000+i:04d}-{9000+i:04d}-{8000+i:04d}-{70000+i:05d}",
            "price_usd": price,
            "currency_code": CURRENCY.get(country, "USD"),
            "verification_status": "verified",
            "grant_status": "granted",
        })
    return rows


# ---------------------------------------------------------------------------
# TABLE 3: admob_daily_report  (60 filas — 30 días × 2 países: MX + US)
# ---------------------------------------------------------------------------
def build_admob_report() -> list[dict]:
    rows = []
    ad_unit = "ca-app-pub-3940256099942544/5224354917"
    for day_offset in range(30):
        report_date = d(30 - day_offset)  # de hace 30 días hasta ayer

        mx_micros = 1_500_000 + (day_offset % 7) * 150_000   # ~$1.50–$2.55/día
        mx_impr   = 120 + day_offset * 8
        rows.append({
            "report_date":               report_date.isoformat(),
            "ad_unit_id":                ad_unit,
            "ad_format":                 "rewarded",
            "country":                   "MX",
            "estimated_earnings_micros": mx_micros,
            "impressions":               mx_impr,
            "clicks":                    max(1, mx_impr // 10),
            "impression_rpm":            round((mx_micros / 1_000_000) / mx_impr * 1000, 4),
        })

        us_micros = 800_000 + (day_offset % 5) * 200_000    # ~$0.80–$1.60/día
        us_impr   = 60 + day_offset * 4
        rows.append({
            "report_date":               report_date.isoformat(),
            "ad_unit_id":                ad_unit,
            "ad_format":                 "rewarded",
            "country":                   "US",
            "estimated_earnings_micros": us_micros,
            "impressions":               us_impr,
            "clicks":                    max(1, us_impr // 12),
            "impression_rpm":            round((us_micros / 1_000_000) / us_impr * 1000, 4),
        })
    return rows


# ---------------------------------------------------------------------------
# TABLE 4: entitlement_grants  (20 filas)
# ---------------------------------------------------------------------------
# (uid, entitlement_type, entitlement_id, source, granted_by, quantity, days_ago)
GRANTS = [
    ("uid_001", "no_ads",       "no_ads",           "iap", "payment_verify", None, 33),
    ("uid_001", "season_pass",  "season_pass_gold",  "iap", "payment_verify", None, 28),
    ("uid_002", "life_pack",    "lives_pack_5",      "iap", "payment_verify", 5,   34),
    ("uid_003", "skin",         "skin_classic",      "iap", "payment_verify", None, 30),
    ("uid_005", "life_pack",    "lives_pack_15",     "iap", "payment_verify", 15,  33),
    ("uid_005", "life_pack",    "lives_pack_5",      "iap", "payment_verify", 5,   26),
    ("uid_006", "life_pack",    "lives_pack_5",      "iap", "payment_verify", 5,   27),
    ("uid_006", "season_pass",  "season_pass_gold",  "iap", "payment_verify", None, 21),
    ("uid_007", "skin",         "skin_classic",      "iap", "payment_verify", None, 26),
    ("uid_008", "life_pack",    "lives_pack_15",     "iap", "payment_verify", 15,  25),
    ("uid_011", "life_pack",    "lives_pack_5",      "iap", "payment_verify", 5,   20),
    ("uid_011", "life_pack",    "lives_pack_15",     "iap", "payment_verify", 15,  14),
    ("uid_012", "skin",         "skin_classic",      "iap", "payment_verify", None, 19),
    ("uid_015", "life_pack",    "lives_pack_5",      "iap", "payment_verify", 5,   18),
    ("uid_016", "season_pass",  "season_pass_gold",  "iap", "payment_verify", None, 13),
    ("uid_016", "life_pack",    "lives_pack_5",      "iap", "payment_verify", 5,    7),
    ("uid_017", "skin",         "skin_classic",      "iap", "payment_verify", None, 12),
    ("uid_018", "life_pack",    "lives_pack_15",     "iap", "payment_verify", 15,  13),
    ("uid_019", "life_pack",    "lives_pack_5",      "iap", "payment_verify", 5,    6),
    ("uid_020", "life_pack",    "lives_pack_5",      "iap", "payment_verify", 5,    5),
]


def build_entitlement_grants() -> list[dict]:
    rows = []
    for i, (uid, etype, eid, source, granted_by, qty, days_ago) in enumerate(GRANTS):
        _, country, platform, app_version, _ = USER_INFO[uid]
        event_date = d(days_ago)
        rows.append({
            "event_timestamp":  ts(event_date, hour=14),
            "event_date":       event_date.isoformat(),
            "user_id":          uid,
            "session_id":       f"sess_{uid}_pur_{i:02d}",
            "platform":         platform,
            "app_version":      app_version,
            "country":          country,
            "entitlement_type": etype,
            "entitlement_id":   eid,
            "source":           source,
            "granted_by":       granted_by,
            "quantity":         qty,
        })
    return rows


# ---------------------------------------------------------------------------
# INSERT helper
# ---------------------------------------------------------------------------
def insert_table(table: str, rows: list[dict], label: str) -> None:
    full_id = f"{PROJECT}.{DATASET}.{table}"
    errors = client.insert_rows_json(full_id, rows)
    if errors:
        print(f"  ERROR {label}: {errors[:2]}")
    else:
        print(f"  OK    {label}: {len(rows)} filas insertadas")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    login_rows       = build_login_events()
    purchase_rows    = build_purchase_events()
    admob_rows       = build_admob_report()
    entitlement_rows = build_entitlement_grants()

    print("=" * 60)
    print("seed_bq_test_data.py — T-303 Looker Studio test data")
    print("=" * 60)
    print(f"  login_events:      {len(login_rows)} filas")
    print(f"  purchase_events:   {len(purchase_rows)} filas")
    print(f"  admob_daily_report:{len(admob_rows)} filas")
    print(f"  entitlement_grants:{len(entitlement_rows)} filas")
    print(f"  TOTAL:             {len(login_rows)+len(purchase_rows)+len(admob_rows)+len(entitlement_rows)} filas")
    print()

    insert_table("login_events",       login_rows,       "login_events")
    insert_table("purchase_events",    purchase_rows,    "purchase_events")
    insert_table("admob_daily_report", admob_rows,       "admob_daily_report")
    insert_table("entitlement_grants", entitlement_rows, "entitlement_grants")

    print()
    print("Listo. Abre Looker Studio — las vistas BQ leen en tiempo real.")
    print()
    print("Gates esperados en el KPI scorecard:")
    print("  D1 retention:      ~55%   (gate >=25% => VERDE)")
    print("  D7 retention:      ~45%   (gate >=10% => VERDE)")
    print("  No-Ads conversion:  5.0%  (gate 2-5% => VERDE)")
    print("  Total revenue:    ~$154   (IAP ~$67 + AdMob ~$87 => POSITIVO)")
