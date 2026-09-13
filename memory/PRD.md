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
- **Jun 2026 — automatic product images**: `sellauth._image_url()` reads the first gallery image
  (by pivot order) and `fetch_product` returns it, so `sellauth_fields()` saves it to `image_url`
  on create and whenever the SellAuth id changes. `POST /api/admin/sync/images`
  (`sync_sellauth_images`) backfills every product with a SellAuth id — run once, 17 updated. The
  two Shundo products have no SellAuth id and keep their local files. Admin "Image filename" is
  now optional: the field is omitted from the payload when blank and a SellAuth id exists, so a
  routine edit can't wipe the synced URL; the remote image shows as the preview, and a
  "Refresh images" button re-pulls on demand.
  Verified: iteration_24.json (12/12 new, 0 broken images on / and /products, regression green).

- **Jun 2026 — Backup Vault**: hidden owner escape hatch at `/admin/vault-access` (no nav or tab
  entry, `ProtectedRoute adminOnly`). Second gate is `VAULT_PHRASE` in backend env only, compared
  with `secrets.compare_digest`; the phrase is never in the bundle, never echoed, never stored
  client-side, and the page re-locks on reload. Wrong guesses are throttled 5 per 15 min per IP
  while a correct phrase always passes and clears the counter. Tools: `POST
  /api/admin/vault/code-map` (markdown outline of ~60 backend/frontend files via `vault.code_map`)
  and `POST /api/admin/vault/export` (every collection except `visits` as one JSON download).
  Verified: iteration_25.json (17/17 vault tests, no security findings).
- Stale test cleanup (Jun 2026): fixed the `post_webhook` helper bug that masked signature
  checking (server correctly returns 401), refreshed image/category/Rocket-price assertions, and
  restored the backticked format in `test_credentials.md` that fixtures parse.

- **Jun 2026 — compliance batch**: `/legal` hub (`pages/Legal.jsx` + `components/Markdown.jsx`,
  720px, tabbed Privacy/Terms, `?doc=` deep link) replaces `/about` (route, page and nav link
  removed). Documents live in `settings._id="legal"` seeded from `backend/legal_docs.py` and are
  editable in Admin → legal. Site-wide `components/Footer.jsx` with Privacy/Terms/Refund links and
  the exact Niantic disclaimer. Homepage hero is now `/images/video.mp4`
  (muted/autoplay/loop/playsInline, Mainpage.jpg poster). Checkout requires an 18+/Terms checkbox;
  `accepted_terms` is enforced server-side (400) and `accepted_terms_at` + `terms_version` are
  stored on the session and order. `purge_expired_credentials()` nulls PTC credentials 7 days
  after an order completes (runs on boot and whenever admin lists orders); the reveal endpoint
  then reports "(deleted — 7 day retention)". Admin → payout requests lists pending SellAuth
  affiliate payouts with a Mark as Paid action.
  Verified: iteration_26.json (15/15 backend, all frontend flows, no issues).
- **Jun 2026 — homepage video**: hero keeps `video.mp4` as the muted/autoplay/loop/playsInline
  background; new "Refer & Earn" homepage section (`home-refer-section`) holds a second instance in
  a manual player (`components/ExplainerVideo.jsx`) — native controls (play/pause, seek, volume,
  mute, fullscreen), no autoplay, neon-framed with a poster and custom play overlay, plus a
  "Get my link" CTA to /my-orders.
  NOT BUILT: the AI chatbot safety prompt — this app has no AI assistant (support is human
  customer↔admin chat), so there is no system prompt to harden.

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

## 2026-06 Hero video thumbnail
- Added /app/frontend/public/images/video-thumb.png (shattered-glass $99.99 -> $42.99 art).
- Set as poster for the hero-card ExplainerVideo in Home.jsx; background loop video keeps Mainpage.jpg poster.

## 2026-06 Admin payout method toggles
- New settings doc _id "payout_methods"; defaults: cashapp OFF, btc/sol/ltc/usdc ON.
- GET/PUT /api/admin/settings/payout-methods (admin only, must keep >=1 enabled).
- /api/affiliate/me payout.methods now only returns enabled methods; POST /api/affiliate/payout rejects disabled methods.
- UI: components/admin/PayoutMethodToggles.jsx rendered at top of PayoutsTab; PayoutDialog defaults to first enabled method.

## 2026-06 Popups (promo capture + abandoned checkout)
- New `popups` Mongo collection + generic engine. Public: GET /api/popups, POST /api/popups/{id}/submit (writes into the SAME waitlist collection, product_id=promo_list, source=promo_popup), POST /api/popups/{id}/offer (mints code via shared issue_auto_coupon()).
- Admin CRUD /api/admin/popups; new Admin tab "Popups" (components/admin/PopupsTab.jsx) with every field editable + create/delete.
- Seeded: "Promo & drop alerts" (email capture, 10s delay, 14-day suppress) and "Abandoned checkout 5%" (exit_checkout trigger, COMEBACK prefix, 5%, event_pass excluded, 7-day expiry/suppress).
- Frontend: components/PopupManager.jsx site-wide (delay / page_views / exit_checkout triggers, Escape close, localStorage suppression key pokeforge_popup_<id>, prefills logged-in email). Checkout auto-applies ?code=.
- CartContext now persists the applied coupon in localStorage (pokeforge_coupon) and re-prices it on load, so the come-back popup never re-fires after a hard reload.
- Admin Waitlist labels promo_list rows as "Promo list / specials" (flows into CSV export).

## 2026-06 Security hardening (audit P0+P1)
- CORS_ORIGINS now includes https://pokecoins.cc,https://www.pokecoins.cc (+ preview, localhost). csrf_guard middleware: cookie-auth POST/PUT/PATCH/DELETE needs same-host or allowlisted Origin (Bearer callers exempt).
- ADMIN_PASSWORD rotated to acientraft2020 (user to change in-app).
- Per-IP rate limits (rate_limits collection, TTL 48h): popup offer 3/day, popup submit 10/h, waitlist 10/h, claim-order 5/h. Popup coupons scoped to signed-in email.
- Guest order access keys: orders.access_key, emailed links carry ?k=, required for guest GET /orders/{id}, /messages and /auth/claim-order. Legacy orders without a key still open (see iteration_28 note before removing that branch).
- Webhook: HMAC signature only (no ?secret=). Login lockout keys on rightmost X-Forwarded-For hop. Markdown hrefs limited to http(s)/mailto/relative.
- Verified: iteration_28.json 29/29 backend + all frontend flows pass.

## 2026-06 Security re-audit fixes (SEC-001 / SEC-002)
- Re-audit verdict: CONDITIONAL PASS. CSRF, admin-password rotation, and rate limits all PASS.
  Two guest-order IDOR gaps remained and are now fixed:
- SEC-001 (was P2): GET /api/checkout-sessions/{id} used to return the order's `access_key`
  (`order_key`) with no auth, so a guessed session id leaked guest order + chat. Fix: checkout
  session now mints an unguessable `session_token` (returned to the buyer at /orders/checkout);
  the status endpoint requires `?t=<token>` and 403s without it before exposing order_id/order_key.
  Frontend: Checkout.jsx stores the token (localStorage + `&t=` on /payment/success URL);
  PaymentSuccess.jsx passes it when polling.
- SEC-002 (was P3): `guest_access_ok` used to allow keyless guest orders to be read by id alone.
  Fix: it now returns False when an order has no `access_key`; `backfill_order_keys()` runs on
  boot and gave all 189 legacy orders a key (0 keyless remaining).
- Verified via curl: no/wrong token → 403, correct token → 200; DB check confirms 0 keyless orders.
