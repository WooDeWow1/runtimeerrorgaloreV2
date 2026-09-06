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

- **Jun 2026 — Refer & Earn (SellAuth affiliate)**: new tab on /my-orders showing the customer's
  referral link, commission range, lifetime earnings, balance and referral count, with Copy,
  Request Payout and Become a Promoter. Backend `sellauth_affiliate.py` reads via the seller API
  and performs every customer action through a 5-minute customer-dashboard token minted for that
  one customer id (never accepted from the client). Identity resolves by site email, then emails
  from the user's past orders, then persists `sellauth_customer_id` on the user doc. Enrolment
  uses the default tier (622) so per-product overrides apply; commission is shown as a 0%–10%
  range with Event Passes named as 0%. Referral capture: `?ref=` stored 30 days
  (`lib/referral.js`) and sent as `ref` on checkout → passed to SellAuth as `affiliate`, but
  dropped when our coupon is applied AND the tier carries a buyer discount, so discounts never
  stack. Payouts: $10 floor, methods Cash App / BTC / SOL / LTC / USDC (+chain).
  SellAuth shop settings changed via API: `payout_min_amount` 50 → 10, `attribution_window_days`
  5 → 30. Verified: iteration_21.json (20/20 backend, all frontend flows, no security findings).
- **Jun 2026 — promoter leaderboard + share buttons**: Admin `promoters` tab
  (`components/admin/AffiliatesTab.jsx`, `GET /api/admin/affiliates`) ranks affiliates by lifetime
  earnings then referrals with program stats, medals on the top three, and a tier dropdown
  (`PUT /api/admin/affiliates/{customer_id}/tier`, returns 400 not 502 so the SellAuth message
  survives Cloudflare). Customer panel gained one-tap sharing (`components/ShareButtons.jsx`):
  X tweet intent plus copy-caption for Discord and TikTok, all clipboard-failure safe.
  Verified: iteration_22.json (8/8 new + 20/20 regression backend, all frontend flows).
- **Jun 2026 — custom affiliate codes**: `POST /api/affiliate/code` lets a promoter claim their own
  handle once (`CodeChangeRequest`, 3–16 chars, `^[A-Za-z0-9_-]+$`, upper-cased), executed with a
  customer-scoped SellAuth token via `set_code()`. A second attempt is refused with 400 and never
  reaches SellAuth; duplicate codes surface SellAuth's readable message. `/affiliate/me` exposes
  `code_editable` and `code_change_used`; the panel shows "Edit my code" until used, then
  "personalised" (`EditCodeDialog.jsx`, refetches `/affiliate/me` after saving).
  Verified: iteration_23.json (11/11 new + 28/28 regression), stale-flag bug from that run fixed.

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
