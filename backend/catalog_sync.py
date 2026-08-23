"""Push the local (preview) catalog to the live production site over its admin API."""
import os

import httpx

SYNC_FIELDS = [
    "name", "description", "category", "price", "msrp", "image_url", "coins", "badge",
    "active", "coming_soon", "is_featured", "sellauth_product_id", "sellauth_variant_id",
]
TIMEOUT = 30


class SyncError(Exception):
    pass


def target_base() -> str:
    base = (os.environ.get("PUBLIC_APP_URL") or "").rstrip("/")
    if not base.startswith("https://"):
        raise SyncError("PUBLIC_APP_URL is not set to an https:// production URL")
    return base


def _payload(p: dict) -> dict:
    return {k: p.get(k) for k in SYNC_FIELDS if p.get(k) is not None}


def _differences(src: dict, dst: dict) -> dict:
    out = {}
    for k in SYNC_FIELDS:
        if k == "name":
            continue
        a, b = src.get(k), dst.get(k)
        if isinstance(a, float) or isinstance(b, float):
            same = a is not None and b is not None and abs(float(a) - float(b)) < 0.005
        else:
            same = a == b
        if not same and not (a is None and b in (None, "", 0)):
            out[k] = {"from": b, "to": a}
    return out


async def _login(client: httpx.AsyncClient, base: str) -> str:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")
    if not (email and password):
        raise SyncError("ADMIN_EMAIL / ADMIN_PASSWORD are not configured")
    resp = await client.post(f"{base}/api/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        raise SyncError(f"Production login failed ({resp.status_code}). Admin password may differ there.")
    return resp.json()["access_token"]


async def _target_products(client, base, token) -> list:
    resp = await client.get(
        f"{base}/api/products",
        params={"include_inactive": "true"},
        headers={"Authorization": f"Bearer {token}"},
    )
    if resp.status_code != 200:
        raise SyncError(f"Could not read the production catalog ({resp.status_code})")
    return resp.json()


async def plan(source: list[dict], apply: bool = False) -> dict:
    base = target_base()
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        token = await _login(client, base)
        target = await _target_products(client, base, token)
        by_name = {p["name"]: p for p in target}
        headers = {"Authorization": f"Bearer {token}"}

        creates, updates = [], []
        for p in source:
            dst = by_name.get(p["name"])
            if not dst:
                creates.append({"name": p["name"], "category": p.get("category"), "price": p.get("price")})
                continue
            diff = _differences(p, dst)
            if diff:
                updates.append({"name": p["name"], "id": dst["id"], "changes": diff})

        result = {
            "target": base,
            "source_count": len(source),
            "target_count": len(target),
            "creates": creates,
            "updates": updates,
            "applied": False,
            "errors": [],
        }
        if not apply or not (creates or updates):
            return result

        src_by_name = {p["name"]: p for p in source}
        for c in creates:
            p = src_by_name[c["name"]]
            resp = await client.post(f"{base}/api/products", json=_payload(p), headers=headers)
            if resp.status_code >= 400:
                result["errors"].append(f"create {p['name']}: {resp.status_code} {resp.text[:160]}")
                continue
            new_id = resp.json()["id"]
            if p.get("is_featured"):
                await client.patch(f"{base}/api/products/{new_id}/featured",
                                   json={"is_featured": True}, headers=headers)
        for u in updates:
            p = src_by_name[u["name"]]
            body = {k: p.get(k) for k in u["changes"]}
            resp = await client.put(f"{base}/api/products/{u['id']}", json=body, headers=headers)
            if resp.status_code >= 400:
                result["errors"].append(f"update {p['name']}: {resp.status_code} {resp.text[:160]}")
                continue
            if "is_featured" in body:
                await client.patch(f"{base}/api/products/{u['id']}/featured",
                                   json={"is_featured": bool(p.get("is_featured"))}, headers=headers)

        result["applied"] = True
        result["target_count"] = len(await _target_products(client, base, token))
        return result
