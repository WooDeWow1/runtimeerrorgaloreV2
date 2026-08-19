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

## Product visibility rules (global, no per-product exceptions)
- `active = false` → hidden from the storefront entirely (admin-only hide switch)
- `coming_soon = true` (with active) → renders on Products, and on Home when `is_featured`;
  shows a Coming Soon overlay + muted price, no savings badge, Join Waitlist instead of Add to Cart
- Backend rejects coming-soon/inactive items at checkout

## Implemented
- Catalog, cart rules, guest checkout, SellAuth checkout + webhook, encrypted PTC creds
- Order tracking + emails (Emergent Resend), admin orders/products, featured star toggles
- Products page, About Us, Platinum Medals & Stardust categories
- Settings & Analytics admin tab (password change, IP geolocation analytics)
- Coupon system with per-product/category exclusions, min spend, max uses
- **2026-06**
  - Fixed-amount coupons (`discount_type` percent|fixed + `amount_off`), capped so the cart keeps
    a $0.50 minimum charge; admin type selector
  - One-per-customer coupons (`one_per_customer` + `coupon_redemptions`), enforced on validate and
    checkout, recorded on webhook payment; applied code clears if the guest email changes
  - Waitlist admin tab (email, source product, date, search, CSV export)
  - Pokeball favicon
  - Coming Soon / Active unified: removed the hardcoded Shundo product section on Home
    (`shundo_service` now a normal featured category), Coming Soon overlay + notice on cards
  - **Root cause of the vanishing-product bug**: `PUT /api/products/{id}` rebuilt the document from
    `ProductIn`, silently resetting `is_featured` to false on every admin edit. Now uses
    `ProductUpdate` with `exclude_unset=True`; the admin form also round-trips `is_featured`
  - `GET /api/products?include_inactive=true` now requires an admin token

## Backlog
- P1: Brute-force lockout keys on the ingress pod IP (`request.client.host`) instead of
  X-Forwarded-For, so lockout fires late and can be bypassed. Needs auth review.
- P1: CORS uses `allow_origin_regex='.*'` with `allow_credentials=True`; wire `CORS_ORIGINS`.
- P2: Bundle deals — automatic discount when Stardust is bought with a coin bundle
- P2: Retry/backoff around the emailer (429s seen under load)
- P2: Server-side product-name join on `/api/admin/waitlist`; paginate `/api/products`
- P2: Split `Admin.jsx` (840 lines) into per-tab components

## Testing
Latest: `/app/test_reports/iteration_12.json` — 134/134 in-scope backend tests, all frontend
assertions passing. Backend test files must be run ONE FILE AT A TIME (pytest.ini forces xdist).

## Credentials
See `/app/memory/test_credentials.md`.
