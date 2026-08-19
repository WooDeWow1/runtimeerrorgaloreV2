"""Iteration 13: order-chat + post-purchase claim-account + notifications/email.

Covers:
- GET /api/checkout-sessions/{id} (payment success polling)
- GET/POST /api/orders/{id}/messages (guest + admin, access control)
- POST /api/auth/claim-order (create account from order email, multi-order claim, security)
- GET /api/notifications + POST /api/notifications/read
"""
import json
import os
import subprocess
import uuid

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE = base.rstrip("/") + "/api"

ADMIN_EMAIL = "officialwifi@icloud.com"
ADMIN_PASSWORD = "admin"


def seed_order(email=None):
    cmd = ["python3", "/app/scripts/seed_test_order.py"]
    if email:
        cmd.append(email)
    out = subprocess.run(cmd, capture_output=True, text=True, cwd="/app/backend", timeout=120)
    assert out.returncode == 0, f"seed failed: {out.stderr[-800:]}"
    return json.loads(out.stdout.strip().splitlines()[-1])


class Anon:
    """Cookie-less client: every call is a fresh anonymous request (httpOnly auth cookies
    would otherwise leak between 'guest' and logged-in calls)."""

    def _do(self, method, url, **kw):
        return requests.request(method, url, headers={"Content-Type": "application/json",
                                                      **kw.pop("headers", {})}, timeout=40, **kw)

    def get(self, url, **kw):
        return self._do("GET", url, **kw)

    def post(self, url, **kw):
        return self._do("POST", url, **kw)


@pytest.fixture(scope="module")
def client():
    return Anon()


@pytest.fixture(scope="module")
def admin_headers(client):
    r = client.post(f"{BASE}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# NOTE: cleanup is intentionally NOT a fixture — pytest.ini runs 2 xdist workers and a per-worker
# teardown would delete the other worker's live test orders. Run after the suite:
#   python3 /app/scripts/cleanup_test_data.py


class TestPaymentSuccessData:
    """Data the /payment/success page needs."""

    def test_session_lookup_returns_order_id(self, client):
        seed = seed_order()
        r = client.get(f"{BASE}/checkout-sessions/{seed['session_id']}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("order_id") == seed["order_id"]

    def test_anonymous_can_read_unclaimed_order_and_email(self, client):
        seed = seed_order()
        r = client.get(f"{BASE}/orders/{seed['order_id']}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user_email"] == seed["email"]
        assert "_id" not in data
        assert "ptc_password" not in data
        # seeded admin greeting message present
        m = client.get(f"{BASE}/orders/{seed['order_id']}/messages")
        assert m.status_code == 200
        assert isinstance(m.json(), list)

    def test_unknown_session_404(self, client):
        r = client.get(f"{BASE}/checkout-sessions/{'a' * 24}")
        assert r.status_code == 404


class TestOrderChat:
    def test_guest_post_and_admin_reply(self, client, admin_headers):
        seed = seed_order()
        oid = seed["order_id"]
        r = client.post(f"{BASE}/orders/{oid}/messages", json={"body": "TEST-it13 guest question"})
        assert r.status_code == 200, r.text
        assert r.json()["sender_role"] == "customer"
        assert r.json()["body"] == "TEST-it13 guest question"

        a = client.post(f"{BASE}/orders/{oid}/messages",
                        json={"body": "TEST-it13 admin reply"}, headers=admin_headers)
        assert a.status_code == 200, a.text
        assert a.json()["sender_role"] == "admin"

        thread = client.get(f"{BASE}/orders/{oid}/messages").json()
        bodies = [m["body"] for m in thread]
        assert "TEST-it13 guest question" in bodies
        assert "TEST-it13 admin reply" in bodies
        roles = {m["body"]: m["sender_role"] for m in thread}
        assert roles["TEST-it13 admin reply"] == "admin"
        assert all("_id" not in m for m in thread)

    def test_empty_body_rejected(self, client):
        seed = seed_order()
        r = client.post(f"{BASE}/orders/{seed['order_id']}/messages", json={"body": ""})
        assert r.status_code in (400, 422), f"empty message accepted: {r.status_code}"

    def test_messages_unknown_order_404(self, client):
        r = client.get(f"{BASE}/orders/{'b' * 24}/messages")
        assert r.status_code == 404


class TestClaimOrder:
    def test_claim_creates_account_and_links_all_same_email_orders(self, client):
        email = f"test-it13+{uuid.uuid4().hex[:8]}@gmail.com"
        first = seed_order(email)
        second = seed_order(email)

        r = client.post(f"{BASE}/auth/claim-order",
                        json={"order_id": first["order_id"], "password": "hunter2pass"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["user"]["email"] == email.lower()
        assert data["user"]["role"] == "customer"
        assert data["orders_claimed"] == 2, data
        assert isinstance(data["access_token"], str) and data["access_token"]

        uh = {"Authorization": f"Bearer {data['access_token']}"}
        mine = client.get(f"{BASE}/orders", headers=uh)
        assert mine.status_code == 200
        ids = [o["id"] for o in mine.json()]
        assert first["order_id"] in ids and second["order_id"] in ids

        # login with the new password works
        li = client.post(f"{BASE}/auth/login", json={"email": email, "password": "hunter2pass"})
        assert li.status_code == 200, li.text

        # re-claim blocked
        again = client.post(f"{BASE}/auth/claim-order",
                            json={"order_id": first["order_id"], "password": "otherpass1"})
        assert again.status_code == 400
        assert "already" in again.json()["detail"].lower()

        # anonymous now blocked from the claimed order + its chat
        assert client.get(f"{BASE}/orders/{first['order_id']}").status_code == 403
        assert client.get(f"{BASE}/orders/{first['order_id']}/messages").status_code == 403
        assert client.get(f"{BASE}/orders/{first['order_id']}", headers=uh).status_code == 200
        assert client.get(f"{BASE}/orders/{first['order_id']}/messages", headers=uh).status_code == 200

    def test_claim_with_existing_account_email_rejected(self, client):
        email = f"test-it13+{uuid.uuid4().hex[:8]}@gmail.com"
        reg = client.post(f"{BASE}/auth/register",
                          json={"email": email, "password": "existing123", "name": "TEST-it13"})
        assert reg.status_code in (200, 201), reg.text
        order = seed_order(email)
        r = client.post(f"{BASE}/auth/claim-order",
                        json={"order_id": order["order_id"], "password": "newpass123"})
        assert r.status_code == 400, r.text
        assert "sign in" in r.json()["detail"].lower()

    def test_short_password_rejected(self, client):
        order = seed_order()
        r = client.post(f"{BASE}/auth/claim-order", json={"order_id": order["order_id"], "password": "abc"})
        assert r.status_code == 422, r.text

    def test_unknown_order_404(self, client):
        r = client.post(f"{BASE}/auth/claim-order", json={"order_id": "c" * 24, "password": "abcdef12"})
        assert r.status_code == 404

    def test_claim_ignores_client_supplied_email(self, client):
        order = seed_order()
        r = client.post(f"{BASE}/auth/claim-order", json={
            "order_id": order["order_id"], "password": "abcdef12",
            "email": "test-it13+attacker@gmail.com"})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["email"] == order["email"].lower()


class TestAdminReplyNotifications:
    def test_admin_reply_notifies_account_holder(self, client, admin_headers):
        email = f"test-it13+{uuid.uuid4().hex[:8]}@gmail.com"
        order = seed_order(email)
        claim = client.post(f"{BASE}/auth/claim-order",
                            json={"order_id": order["order_id"], "password": "abcdef12"})
        assert claim.status_code == 200, claim.text
        uh = {"Authorization": f"Bearer {claim.json()['access_token']}"}

        a = client.post(f"{BASE}/orders/{order['order_id']}/messages",
                        json={"body": "TEST-it13 support ping"}, headers=admin_headers)
        assert a.status_code == 200, a.text

        notes = client.get(f"{BASE}/notifications", headers=uh)
        assert notes.status_code == 200
        titles = [n["title"] for n in notes.json()]
        assert "New message from support" in titles, notes.json()
        unread = [n for n in notes.json() if not n["read"]]
        assert unread, "notification should start unread"

        read = client.post(f"{BASE}/notifications/read", headers=uh)
        assert read.status_code == 200
        after = client.get(f"{BASE}/notifications", headers=uh).json()
        assert all(n["read"] for n in after)

    def test_notifications_require_auth(self, client):
        assert client.get(f"{BASE}/notifications").status_code in (401, 403)


class TestCustomerOrdersList:
    def test_orders_requires_auth_and_scoped(self, client, admin_headers):
        anon = client.get(f"{BASE}/orders")
        assert anon.status_code in (401, 403)
        email = f"test-it13+{uuid.uuid4().hex[:8]}@gmail.com"
        order = seed_order(email)
        other = seed_order()
        claim = client.post(f"{BASE}/auth/claim-order",
                            json={"order_id": order["order_id"], "password": "abcdef12"})
        uh = {"Authorization": f"Bearer {claim.json()['access_token']}"}
        ids = [o["id"] for o in client.get(f"{BASE}/orders", headers=uh).json()]
        assert ids == [order["order_id"]], ids
        assert other["order_id"] not in ids
