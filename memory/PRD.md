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

- **Jun 2026 — review upgrade**: admin "Pin to Top" per review (pinned lead the homepage carousel,
  the new /products carousel and /reviews with a "Featured" marker); Display Name field on the
  review form pre-filled from the account first name; Anonymous checkbox → shown publicly as
  "Valued Customer" (also the fallback for a blank name); admin has both Decline (deletes + locks
  the order via `?lock=true` default) and Delete (deletes, order stays eligible, `?lock=false`).
  Public /api/reviews never exposes email, real name or order id. Verified: iteration_19.json
  (10/10 new + 9/9 regression backend, all frontend flows green).

- **Jun 2026 — review dialog mobile fix**: Turnstile switches to the `compact` widget below 480px
  and is clipped inside the dialog; Submit/Cancel stack full width with clear spacing below the
  widget; Submit is no longer silently disabled — a yellow reason line states exactly what is
  missing ("N more characters needed…", "Add a title…", "Complete the verification above…").
  The original report ("Turnstile blocks Submit") was actually the 150-character minimum leaving
  the button disabled with no explanation.

- **Jun 2026 — commercial launch reconfiguration**: catalog_sync matches by `sellauth_product_id`
  (name is fallback only) and syncs `variants`, so re-syncs update instead of duplicating; sync
  refuses to run when the target host equals the serving host (no production → production push);
  POST /api/products returns 409 on a duplicate name and `products.name` has a unique index;
  categories are now Pokécoins, Hunting Service, Event Passes, PokéLid Stamp Rally, Platinum
  Medals, Stardust (shundo_service category deleted, both Shundo products moved into
  hunting_service, still Coming Soon); new Hunting Service inventory seeded from live SellAuth
  data — Auto Raid Hunting (870739, 4 variants), Egg Hatching (870828, 3 variants), Team GO
  Rocket — Shiny Shadow Hunting (870940, 7 variants, Coming Soon). Descriptions stay editable via
  Admin > Products. Verified: iteration_20.json (20/20 backend + all frontend flows green).

- **Jun 2026 — Rocket re-tier**: Team GO Rocket variants re-applied on every boot
  (`ROCKET_VARIANTS` / `migrate_rocket_variants`): Giovanni removed; grunts are now 100/250/500/800
  Battles at $24.99/$49.99/$84.99/$119.99 (800 carries a `MAX` badge — new optional `badge` field on
  ProductVariant, shown in both variant selects); leaders 10/25/50 at $29.99/$64.99/$119.99;
  description rewritten to the "Targeted Team GO Rocket battles…" copy.

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
