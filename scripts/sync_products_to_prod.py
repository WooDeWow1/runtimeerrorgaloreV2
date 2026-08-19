"""One-time: copy products missing from production over the live admin API.

Reads the preview catalog, creates any product (matched by name) that production is missing,
then syncs the `is_featured` star so the home page matches preview.
Usage: python3 sync_products_to_prod.py [--apply]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PREVIEW = "http://localhost:8001"
PROD = "https://pokecoins.cc"
FIELDS = ["name", "description", "category", "price", "msrp", "image_url", "coins", "badge",
          "active", "coming_soon", "is_featured"]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually write to production")
    args = ap.parse_args()

    email = os.environ["ADMIN_EMAIL"]
    password = os.environ["ADMIN_PASSWORD"]

    preview = call(PREVIEW, "/api/products")
    prod = call(PROD, "/api/products")
    prod_by_name = {p["name"]: p for p in prod}
    print(f"preview: {len(preview)} products | production: {len(prod)} products")

    missing = [p for p in preview if p["name"] not in prod_by_name]
    restar = [p for p in preview
              if p["name"] in prod_by_name
              and prod_by_name[p["name"]]["is_featured"] != p["is_featured"]]

    for p in missing:
        print(f"  MISSING in production: {p['name']} ({p['category']}, ${p['price']})")
    for p in restar:
        print(f"  STAR mismatch: {p['name']} -> is_featured={p['is_featured']}")
    if not missing and not restar:
        print("Nothing to do — production already matches preview.")
        return
    if not args.apply:
        print("\nDry run. Re-run with --apply to write to production.")
        return

    token = call(PROD, "/api/auth/login", "POST",
                 {"email": email, "password": password})["access_token"]

    for p in missing:
        payload = {k: p.get(k) for k in FIELDS}
        created = call(PROD, "/api/products", "POST", payload, token)
        if p["is_featured"]:
            call(PROD, f"/api/products/{created['id']}/featured", "PATCH",
                 {"is_featured": True}, token)
        print(f"  created: {created['name']} (featured={p['is_featured']})")

    for p in restar:
        pid = prod_by_name[p["name"]]["id"]
        call(PROD, f"/api/products/{pid}/featured", "PATCH",
             {"is_featured": p["is_featured"]}, token)
        print(f"  starred: {p['name']} -> {p['is_featured']}")

    after = call(PROD, "/api/products")
    print(f"\nproduction now has {len(after)} products")
    for p in after:
        print(f" - {p['name']} | featured={p['is_featured']} | soon={p['coming_soon']}")


if __name__ == "__main__":
    sys.exit(main())
