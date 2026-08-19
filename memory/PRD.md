# PokeCoins — Product Requirements

## Problem statement
Full-stack e-commerce web app for selling digital gaming services (Pokémon GO items):
React frontend, FastAPI backend, MongoDB. Product catalog, strict cart logic (Event Passes
require Coin Bundles), SellAuth payments (Crypto/CashApp), encrypted PTC credential capture,
order tracking, admin dashboard, premium dark "hacker-forum" aesthetic.

## Architecture
- `/app/backend`: server.py (routes), models.py, security.py (JWT + Fernet), sellauth.py, emailer.py
- `/app/frontend`: React 19 + CRA/craco, pages/ components/ context/ lib/
- Images localized in `/app/frontend/public/images/`
- Orders are created ONLY by the SellAuth webhook; checkout creates a 30-min `checkout_sessions` doc

## Implemented
- Catalog, cart rules, guest checkout, SellAuth checkout + webhook, encrypted PTC creds
- Order tracking + emails (Emergent Resend), admin orders/products, featured toggles
- Products page, About Us, Platinum Medals & Stardust categories
- Settings & Analytics admin tab (password change, IP geolocation analytics)
- Coupon system with per-product/category exclusions, min spend, max uses
- **2026-06 (this session)**
  - Fixed-amount coupons: `discount_type` percent|fixed + `amount_off`; discount capped so the
    cart keeps a $0.50 minimum charge (SellAuth rejects $0 totals); admin form type selector
  - One-per-customer coupons: `one_per_customer` flag, `coupon_redemptions` collection
    (unique code+email), enforced at `/api/coupons/validate` and `/api/orders/checkout`;
    recorded on webhook payment. Checkout clears the applied code if the guest email changes
  - Waitlist admin tab: email, source product, date, search + CSV export
  - Pokeball favicon (`/favicon.png`, `/apple-touch-icon.png`)

## Backlog
- P1: Brute-force lockout keys on the ingress pod IP (`request.client.host`) instead of
  X-Forwarded-For, so lockout fires late and can be bypassed. Needs auth review.
- P1: CORS uses `allow_origin_regex='.*'` with `allow_credentials=True`; wire `CORS_ORIGINS`.
- P2: Bundle deals — automatic discount when Stardust is bought with a coin bundle
- P2: Server-side product-name join on `/api/admin/waitlist` (deleted products show blank source)
- P2: Inline styled validation on the admin coupon form (currently native browser tooltip)

## Credentials
See `/app/memory/test_credentials.md`.
