"""One-time: re-map product exclusions on coupons that already exist in production.

Product ids differ per database, so this rewrites each production coupon's
excluded_product_ids from the preview coupon of the same code, matched by product name.
Usage: python3 fix_coupon_exclusions.py [--apply]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sync_coupons_to_prod import PREVIEW, PROD, call, login  # noqa: E402

FIELDS = ["code", "discount_type", "percent_off", "amount_off", "one_per_customer", "active",
          "excluded_categories", "min_subtotal", "max_uses", "expires_at", "note"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    email, password = os.environ["ADMIN_EMAIL"], os.environ["ADMIN_PASSWORD"]

    pv = login(PREVIEW, email, password)
    pr = login(PROD, email, password)
    prev_coupons = {c["code"]: c for c in call(PREVIEW, "/api/admin/coupons", token=pv)}
    prod_coupons = call(PROD, "/api/admin/coupons", token=pr)
    prev_names = {p["id"]: p["name"] for p in call(PREVIEW, "/api/products?include_inactive=true", token=pv)}
    prod_ids = {p["name"]: p["id"] for p in call(PROD, "/api/products?include_inactive=true", token=pr)}

    for pc in prod_coupons:
        src = prev_coupons.get(pc["code"])
        if not src:
            continue
        want_names = sorted(prev_names.get(i, i) for i in src.get("excluded_product_ids") or [])
        have_names = sorted(
            next((n for n, i in prod_ids.items() if i == pid), pid)
            for pid in pc.get("excluded_product_ids") or []
        )
        if want_names == have_names:
            print(f"  {pc['code']}: exclusions already match ({len(want_names)} products)")
            continue
        new_ids = [prod_ids[n] for n in want_names if n in prod_ids]
        missing = [n for n in want_names if n not in prod_ids]
        print(f"  {pc['code']}: {len(have_names)} -> {len(new_ids)} excluded products"
              + (f" (still missing in production: {', '.join(missing)})" if missing else ""))
        if not args.apply:
            continue
        payload = {k: src.get(k) for k in FIELDS}
        payload["excluded_product_ids"] = new_ids
        call(PROD, f"/api/admin/coupons/{pc['id']}", "PUT", payload, pr)
        print(f"    updated {pc['code']}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to write to production.")


if __name__ == "__main__":
    sys.exit(main())
