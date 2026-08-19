"""One-time: copy discount codes missing from production over the live admin API.

Matches by code and skips anything production already has. Product-level exclusions are
remapped from preview product ids to the matching production product ids (matched by name);
category exclusions carry over as-is. Usage: python3 sync_coupons_to_prod.py [--apply]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PREVIEW = "http://localhost:8001"
PROD = "https://pokecoins.cc"
FIELDS = ["code", "discount_type", "percent_off", "amount_off", "one_per_customer", "active",
          "excluded_categories", "min_subtotal", "max_uses", "expires_at", "note"]


def call(base, path, method="GET", body=None, token=None):
    req = urllib.request.Request(f"{base}{path}", method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (compatible; pokecoins-sync/1.0)")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{method} {base}{path} -> {exc.code}: {exc.read().decode()[:400]}")


def login(base, email, password):
    return call(base, "/api/auth/login", "POST",
                {"email": email, "password": password})["access_token"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write to production")
    args = ap.parse_args()

    email = os.environ["ADMIN_EMAIL"]
    password = os.environ["ADMIN_PASSWORD"]

    prev_token = login(PREVIEW, email, password)
    preview = call(PREVIEW, "/api/admin/coupons", token=prev_token)
    prod_token = login(PROD, email, password)
    prod = call(PROD, "/api/admin/coupons", token=prod_token)
    have = {c["code"] for c in prod}
    print(f"preview: {len(preview)} coupons | production: {len(prod)} coupons")

    # Product ids differ between databases, so translate exclusions by product name.
    prev_products = {p["id"]: p["name"] for p in call(PREVIEW, "/api/products?include_inactive=true",
                                                      token=prev_token)}
    prod_products = {p["name"]: p["id"] for p in call(PROD, "/api/products?include_inactive=true",
                                                     token=prod_token)}

    missing = [c for c in preview if c["code"] not in have]
    for c in preview:
        if c["code"] in have:
            print(f"  skip (already live): {c['code']}")
    for c in missing:
        kind = f"${c['amount_off']} off" if c.get("discount_type") == "fixed" else f"{c['percent_off']}% off"
        print(f"  to create: {c['code']} · {kind}"
              f"{' · 1 per customer' if c.get('one_per_customer') else ''}"
              f"{'' if c.get('active') else ' · disabled'}")
    if not missing:
        print("Nothing to do — production already has every preview coupon.")
        return
    if not args.apply:
        print("\nDry run. Re-run with --apply to write to production.")
        return

    for c in missing:
        payload = {k: c.get(k) for k in FIELDS}
        excluded, dropped = [], []
        for pid in c.get("excluded_product_ids") or []:
            name = prev_products.get(pid)
            if name and name in prod_products:
                excluded.append(prod_products[name])
            else:
                dropped.append(name or pid)
        payload["excluded_product_ids"] = excluded
        created = call(PROD, "/api/admin/coupons", "POST", payload, prod_token)
        note = f" (exclusions dropped, not in production: {', '.join(dropped)})" if dropped else ""
        print(f"  created: {created['code']}{note}")

    after = call(PROD, "/api/admin/coupons", token=prod_token)
    print(f"\nproduction now has {len(after)} coupons")
    for c in after:
        kind = f"${c['amount_off']} off" if c.get("discount_type") == "fixed" else f"{c['percent_off']}% off"
        print(f" - {c['code']} · {kind} · {'active' if c['active'] else 'disabled'}"
              f"{' · 1 per customer' if c.get('one_per_customer') else ''}")


if __name__ == "__main__":
    sys.exit(main())
