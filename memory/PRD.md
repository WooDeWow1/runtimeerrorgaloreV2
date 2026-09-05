# PokeCoins — PRD

## Problem statement
Full-stack e-commerce app for selling digital Pokémon GO services. React frontend, FastAPI
backend, MongoDB. Product catalog, strict cart logic (Event Passes require another item, max 1),
SellAuth checkout (Crypto/CashApp), encrypted PTC credential capture, order tracking, customer↔admin
chat, admin dashboard, premium dark "hacker-forum" aesthetic.

## Environments
- Production: https://pokecoins.cc (user redeploys)
- Preview (dev): REACT_APP_BACKEND_URL in /app/frontend/.env

## Architecture
- backend: server.py (API), models.py, security.py (Fernet + JWT), sellauth.py, emailer.py
  (Emergent managed email), catalog_sync.py, turnstile.py, tests/
- frontend: src/pages/*, src/components/*, src/components/admin/* (tab modules), context/, lib/api.js
- Auth: JWT in HttpOnly cookies. Coupons/discounts computed server-side, final price sent to SellAuth.

## Implemented (to June 2026)
- Catalog, categories, variants, SellAuth catalog sync, coming-soon + waitlist
- Cart rules, master coupon system (% / fixed, category exclusions, Event Passes always excluded)
- Checkout sessions (30 min TTL), SellAuth webhook, order confirmation email, order chat with
  unread badges + email alerts, admin PTC reveal, order status flow with customer notifications
- Reviews: one per completed order, Turnstile CAPTCHA, admin approve/decline, public /reviews page
  + homepage carousel
- **Jun 2026 — review reward rework**: coupon issued ONLY on admin approval (any star rating),
  decline = hard delete + order permanently ineligible (`review_declined`), auto coupons kept after
  redemption with `redeemed_at`, swept only after 30 days, strictly single use and locked to the
  issued_to email, approval email with code/percent/expiry, My Orders shows the code permanently
  with Credited / Redeemed / Expired / "Coupon no longer available" states, admin auto-coupon tab
  shows unredeemed / redeemed(date) / expired. Verified: iteration_18.json (9/9 backend + all
  frontend flows green).
- **Jun 2026** — /reviews explainer banner ("How our reviews work"); star summary hidden below 3
  approved reviews.
- **Jun 2026** — Admin can delete an order (trash icon + confirm); cascades to that order's chat
  messages, notifications and review. Verified via API (200 then 404 on repeat) + admin UI.

## Email
Sends via Emergent managed email. From address is Emergent-controlled; From name = PokeCoins,
Reply-To = support@pokecoins.cc. Sending *from* support@pokecoins.cc is not possible without a
separately verified outbound domain (iCloud custom domains cannot do API sending).

## Backlog
- P0: Live Cash App order end-to-end on production, confirm confirmation email lands
- P1: Self-serve customer password reset
- P1: Flip a Coming Soon product live + email its whole waitlist in one click
- P2: Canned replies in admin chat
- P2: Abandoned checkout discount nudge
- P2: Scheduled flash sales (auto on/off dates)
- Tech debt: server.py ~1,740 lines — split reviews/coupons into routers; approve_review is not
  concurrency-safe (two simultaneous approvals could double-issue) — use find_one_and_update
  guarded on status == "pending".
