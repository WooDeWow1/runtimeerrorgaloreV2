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

## Production
Live at https://pokecoins.cc (preview and production use separate databases).
`/app/scripts/sync_products_to_prod.py` is a one-time/repeatable catalog sync: it reads the
preview catalog from localhost:8001, creates any product production is missing (matched by name)
via the live admin API, and syncs the `is_featured` star. Run with no args for a dry run,
`--apply` to write. Reads ADMIN_EMAIL / ADMIN_PASSWORD from backend/.env.
`/app/scripts/sync_coupons_to_prod.py` does the same for discount codes (skips codes production
already has, remaps product exclusions from preview ids to production ids by product name).
`/app/scripts/fix_coupon_exclusions.py` re-syncs exclusions on coupons that already exist in
production — run it after adding products, since ids differ per database.
- 2026-06: used it to push the 3 Stardust products (missing in production because writes were
  blocked when the cluster was full) and to restore 3 featured stars. Production now has all 11.
- 2026-06: synced coupons META / 1337 / FOREVERFRIENDS to production plus the Mega Raid Day
  Ticket product, then repaired the exclusion lists. All 3 codes verified live on pokecoins.cc.

## SellAuth payment flow (2026-06)
- Webhook URL to configure in SellAuth (Notifications → webhook, invoice events):
  `https://pokecoins.cc/api/webhooks/sellauth`. Secret lives at
  dash.sellauth.com/shop#miscellaneous and must equal `SELLAUTH_WEBHOOK_SECRET`.
  Signature = HMAC-SHA256 of the raw body in the `X-Signature` header (verified working).
- SellAuth's Checkout API has NO return_url/success_url, and the per-product "Redirect URL"
  setting does not apply to custom cart items, so SellAuth can never redirect buyers back.
  Fix: checkout opens the SellAuth invoice in a NEW TAB and routes the original tab to
  `/payment/success?session_id=...`, which polls `/api/checkout-sessions/{id}` until the order
  exists. The success page offers "Reopen payment window" from `pokeforge_checkout_url`.
- The React route is `/payment/success` (NOT `/payment-success` — that renders a blank page).
- Session id is now sent as SellAuth `metadata` (documented field) instead of the unsupported
  top-level `custom_fields`; the webhook reads metadata (dict or list) then falls back to invoice id.
- SellAuth failures now return 400, not 502/503, so the real message reaches the buyer instead of
  a Cloudflare error page.
- The Emergent email proxy returns 422 `undeliverable_recipient` for fake test addresses
  (use delivered@resend.dev for tests). Real addresses deliver fine; emailer now logs the body.

## Customer chat, accounts & dashboard (2026-06)
- `/payment/success` now shows the live order chat plus a "Create account to track order" card
  (`ClaimAccountCard`) for anonymous buyers.
- `POST /api/auth/claim-order` {order_id, password}: email is taken from the ORDER (never the
  caller), refuses orders that already have a user_id or an email that already has an account,
  and adopts every unclaimed order with that email (case-insensitive match).
- `/my-orders` (`MyOrders.jsx`, also served at `/dashboard`; `Dashboard.jsx` deleted) lists orders
  with an inline Open Chat toggle per order. Guest ids come from `pokeforge_guest_orders`
  localStorage, capped at 20 and pruned when unreadable.
- Polling: OrderChat 3s, NotificationBell 10s (no websockets, by user's choice).
- Admin replies notify account holders in-app AND email the buyer (`support_reply_html`), using
  `order.origin_url` which is now persisted on the order.
- Login lockout is keyed on the forwarded client IP (`client_ip`) so 5 failures actually lock.

## Order confirmation email (2026-06)
- Fires from the SellAuth webhook path in `create_order_from_session`, so it only sends once
  payment is confirmed. Idempotent: a repeated webhook returns the existing order and re-sends nothing.
- Branded pokecoins.cc shell (`_wrap` in emailer.py): dark header POKE/COINS wordmark, neon
  #00e6b8 CTA, footer linking pokecoins.cc. Same shell used for admin chat replies.
- CTA "Track order & chat with us" links to `{origin_url}/order/{id}`, which falls back to
  `PUBLIC_APP_URL` (https://pokecoins.cc) via `emailer.order_url()` when origin is missing or
  not https — the old code silently produced a relative link and tripped the G3 link gate.
- Both sends are wrapped in try/except: a provider outage can no longer fail a paid order.
- `PUBLIC_APP_URL` added to backend/.env.

## Commercial launch — SellAuth catalog (2026-06)
- Checkout now sends SellAuth **catalog** items (`productId` + `variantId`) instead of custom lines,
  so SellAuth owns pricing, stock and coupons. Ids live on each product
  (`sellauth_product_id` / `sellauth_variant_id`), mapped by `/app/scripts/map_sellauth_ids.py`
  (dry run by default, `--apply` to write; also syncs price from the SellAuth variant).
  Shundo items stay unmapped (coming soon) and would fall back to custom lines.
- Local coupon engine DELETED (`apply_coupon`, `/coupons/validate`, `/admin/coupons`, coupons +
  coupon_redemptions indexes, admin Coupons tab). The checkout coupon field now passes the code
  through as SellAuth's `coupon` param; the discount appears on SellAuth's payment page.
- Admin Products tab is now display-only: Featured star + Coming Soon toggle, no create/edit/
  delete/price. Product create/update/delete API endpoints still exist for scripts.
- Cart rules: an Event Pass needs at least one non-pass item (any category) and is capped at 1 per
  order — enforced client-side (`CartContext`, ProductCard lock) and server-side
  (`assert_cart_rules`). Event pass copy/badge updated to "ADD-ON ONLY".
- Announcement banner: `settings` collection doc `banner`; `GET /api/settings/banner` (public),
  `PUT /api/admin/settings/banner` (admin, rejects non-https/non-path links). Rendered site-wide by
  `AnnouncementBanner` above the Navbar, dismissible per session.
- /products sorts PokéCoins first (CATEGORY_ORDER).
- Checkout opens the SellAuth tab synchronously on click (popup-blocker safe) and closes it on error.
- /payment/success polls every 2s for up to 2 min, unlocking chat + the claim-account card.
- Email links always use PUBLIC_APP_URL (https://pokecoins.cc).

## Catalog sync button (2026-06)
- Admin → Products → "Push catalog live": `GET /api/admin/sync/catalog` (dry-run diff) and
  `POST /api/admin/sync/catalog` (apply). Logic in `/app/backend/catalog_sync.py`: logs into
  PUBLIC_APP_URL with ADMIN_EMAIL/ADMIN_PASSWORD, matches products by NAME, creates missing ones
  and PUTs changed fields. Never deletes. Replaces `scripts/sync_products_to_prod.py`.
- `sellauth_product_id` / `sellauth_variant_id` added to ProductIn + ProductUpdate so the ids
  can be pushed over the API (previously only settable by direct DB scripts).
- Finding 2026-06: production has all 13 products but is MISSING every SellAuth id, so live
  checkout falls back to custom line items. One "Push to production" fixes it. Not pushed yet
  (waiting on the user, since it writes to the production database).
- Backlog: sync does not push banner settings or delete products removed in preview.

## Hybrid launch — Emergent owns catalog + coupons, SellAuth owns checkout (2026-06)
- **Categories are data**, not code: `categories` collection ({key, label, note, coming_soon, order}).
  `GET /api/categories` (public); admin POST / PUT / `POST /{id}/move` {up|down} / DELETE (delete is
  blocked while products still use the key). `key` is slugified from the label on create and is
  NEVER re-slugified on rename, so product references stay intact. Seeded: Pokécoins, Event Passes,
  PokéLid Stamp Rally, Platinum Medals, Stardust, Shundo Hunting (Waitlist, coming soon).
  Frontend reads them via `lib/useCategories.js`; `CATEGORY_LABELS` deleted from api.js.
- **Admin Products** is a full editor again (`components/admin/ProductEditor.jsx`): name, description,
  category, price, MSRP, badge, image filename, SellAuth product id, active/coming soon/featured.
  Image filenames resolve to `/images/<file>` with a live thumbnail. `GET /api/admin/sellauth/products/{id}`
  + `sellauth_fields()` auto-resolve the variant id and overwrite price from the live SellAuth variant
  on create and whenever the SellAuth id changes, so ids/prices are never typed twice.
- **Coupon engine rebuilt on this side** (`discount_eligible` / `load_coupon` / `compute_discount`):
  percent or fixed, expiry, min cart, max uses, one-per-customer (`coupon_redemptions`), category
  exclusions. Event Passes can NEVER be discounted — blocked by `NO_DISCOUNT_CATEGORIES=["event_pass"]`
  AND `NO_DISCOUNT_SELLAUTH_IDS=[851924, 851927, 851928]`. Mixed carts discount only the eligible
  lines; the discount is spread across them so SellAuth receives the exact final total.
  `POST /api/coupons/validate` powers the Apply button on checkout; admin CRUD at `/api/admin/coupons`.
  Redemption is recorded on the webhook (paid) path, not at checkout.
- **No coupon code is sent to SellAuth any more.** The user disables the coupon field in the SellAuth
  dashboard themselves (no API for it). When a coupon applies, those lines go to SellAuth as CUSTOM
  line items (`custom_price`) because a catalog price cannot be overridden; full-price carts still use
  catalog productId/variantId so SellAuth keeps stock tracking.
- New PokéLid products seeded: Japan PokéLid Stamp Rally Collection (857694) and LEGO PokéLid Stamp
  Rally (857690), prices pulled live from SellAuth ($49.99), images `/images/japanlid.jpg` and
  `/images/legolid.jpg`.
- Home page is a single flat "Featured Stock" grid (1/2/3/4 cols) — no per-category sections.
- Iteration 15 fixes after testing: PUT /admin/coupons now rejects duplicate codes (was a 500 from
  the unique index) and enforces the same percent_off/amount_off guards as POST; category and coupon
  deletes now confirm in the UI.
- Still open (backlog): CORS `allow_origin_regex='.*'` with credentials, native date input for coupon
  expiry, server.py is ~1300 lines and should be split into routers.

## Testing
Latest: `/app/test_reports/iteration_12.json` — 134/134 in-scope backend tests, all frontend
assertions passing. Backend test files must be run ONE FILE AT A TIME (pytest.ini forces xdist).

## Deployment notes (2026-06)
- Production deploy failed because the FastAPI startup handler created indexes + seeded data
  inline: Atlas returned `User writes blocked, reason: DiskUseThresholdExceeded` (code 371) and
  the app aborted startup, so the pod crashlooped. Startup now iterates an `INDEXES` table with
  a per-index try/except (one blocked index no longer skips the others) and `seed_data()` is
  separately guarded, so the app always boots and serves reads on a read-only database.
  Verified by stubbing every write to raise OperationFailure 371: `startup()` completes and logs
  one error per index.
- Added a plain `GET /health` route (the container's nginx probes `127.0.0.1:8001/health`,
  which previously had no handler); `/api/health` also added.
- `.gitignore` no longer excludes `.env` files (deployment scan flagged it as a blocker).
- **The Atlas cluster is out of disk.** Until storage is freed/upgraded, writes (orders,
  waitlist signups, coupon redemptions) will fail in production even though the app boots.

## Credentials
See `/app/memory/test_credentials.md`.
