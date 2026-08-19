# PokéForge — PRD

## Original problem statement
Full-stack e-commerce web app (React + FastAPI + MongoDB) for selling Pokémon GO digital items and services.
Categories: Pokécoin Bundles, Event Passes, Shundo Hunting Services (Coming Soon — private simulation tool suite).
Cart rule: an Event Pass cannot be added or purchased without a Pokécoin Bundle in the cart.
Checkout collects PTC (Pokémon Trainer Club) username + password, encrypted at rest.
Order statuses Pending / Processing (Logged In) / Completed, per-order chat, alerts on Processing & Completed.
Admin dashboard for product CRUD, order management, status updates and decrypting PTC credentials.
UI: premium dark-mode hacker-forum gaming aesthetic with Snorlax / Gengar / Psyduck imagery, mobile responsive.

## User choices / decisions
- JWT email/password auth (Bearer tokens), seeded admin `officialwifi@icloud.com` / `admin`
- Guest checkout: cart, /checkout, /dashboard and order tracking are PUBLIC; only /admin is gated
- Payments: **SellAuth** (crypto + Cash App). Stripe was removed entirely (sandbox deleted, package uninstalled)
- Notifications: in-app for registered users + transactional email of the tracking link on payment

## Architecture
- Backend `/app/backend`: `server.py` (routes), `security.py` (bcrypt, JWT, Fernet), `models.py` (Pydantic + PyObjectId), `sellauth.py` (SellAuth REST client), `emailer.py` (managed email + phishing-safety gate).
- Auth: `Authorization: Bearer` JWT (localStorage `pokeforge_token`). Cookies unused — the preview proxy rewrites CORS ACAO to `*`.
- Anti-spam payment flow: checkout writes ONLY to `checkout_sessions` (TTL index on `expires_at`, 30 min auto-delete) with Fernet-encrypted PTC creds → SellAuth invoice created with `custom_fields.checkout_session_id` → user redirected to SellAuth → signed webhook `POST /api/webhooks/sellauth` verifies HMAC-SHA256 of the raw body, re-checks invoice status via the SellAuth API, then promotes the session into a permanent `orders` doc, sends the in-app notification and emails the `/order/{id}` tracking link. Idempotent via `webhook_events` unique index (inserted after successful promotion).
- Collections: users, products, orders, messages, notifications, checkout_sessions (TTL), webhook_events, login_attempts.
- Frontend: React Router, Tailwind, shadcn, framer-motion, sonner. Unbounded + JetBrains Mono, `#050505` void black with `#00ffcc` neon.

## User personas
- Trainer (customer or guest): buys coins/passes, tracks orders via emailed link, chats with the operator.
- Operator (admin): manages the catalog weekly, fulfils orders, reveals PTC credentials, updates statuses.

## Implemented
- 2026-06: JWT auth + seeded admin, brute-force lockout, admin-gated routes; storefront with neon Snorlax/Gengar/Psyduck art; cart with dual-sided Event Pass ↔ Pokécoin Bundle validation; PTC checkout with Fernet encryption; customer dashboard, order detail with status timeline + stay-logged-out warning; per-order chat; in-app notification bell; admin console (orders, statuses, PTC reveal, product CRUD); mobile responsive
- 2026-06: guest checkout (public cart/checkout/order tracking), Shundo section copy + second Shundo product
- 2026-06: Stripe removed; SellAuth + temporary `checkout_sessions` (30 min TTL) + signed webhook order promotion + tracking-link email; `/order/{id}` tracking route
- 2026-06: rebrand to PokeCoins (header, tab title, footer © 2026 PokeCoins.cc, email sender, API), new hero subtitle; public 'Orders' nav link removed (all-orders list is admin-only); checkout 'How it works' info card
- 2026-06: `medals` (Platinum Medals) category with MSRP-vs-price display; dedicated `/products` catalog with filter tabs; dedicated `/about` page; public `POST /api/waitlist` + admin `GET /api/admin/waitlist`; nav = Store / Products / About Us / Cart (+ Admin for admins)
- 2026-06: SellAuth Checkout API confirmed LIVE — real hosted checkout URLs are now returned (invoice ids stored on the session for webhook matching)
- 2026-06: all artwork localised to `frontend/public/images` (no CDN dependency) via `scripts/download_images.py` + `scripts/migrate_product_images.py`; new hero art `Mainpage.jpg`
- 2026-06: Vercel build fixes in `frontend/package.json` — date-fns 3.6.0, react-day-picker 9.11.1 (React 19 support), ajv 8.17.1 + ajv-keywords 5.1.0 devDeps, npm `overrides` using `$name` refs; `ui/calendar.jsx` migrated to react-day-picker v9 API. Clean `npm install` + `craco build` both pass
- 2026-06: `stardust` category with 1M/5M/10M Stardust Farming products; Admin third tab "Settings & Analytics" with bcrypt password change (`POST /api/auth/change-password`, sets `password_self_managed` so the env seed no longer overwrites it) and lightweight visitor analytics (`POST /api/track` upserts one row per IP per day with hit counter, 90-day TTL, country cached per IP in `ip_geo` via ip-api.com; `GET /api/admin/analytics`)
- 2026-06: fixed Stardust invisibility (root cause: those docs had `active=false` + `coming_soon=true`, so the active-only storefront query skipped them — categories were already correctly synced lowercase snake_case). Added `is_featured` to products with an admin star toggle (`PATCH /api/products/{id}/featured`); the home page now renders ONLY starred products grouped by category and hides any category with zero stars, while `/products` still lists the whole active catalog. Long descriptions clamped to 5 lines on cards. 66/66 backend tests pass
- 2026-06: coupon/discount codes — `coupons` collection (unique code, percent_off, active, excluded_product_ids, excluded_categories, min_subtotal, max_uses, used_count, expires_at, note); public `POST /api/coupons/validate`; admin CRUD `GET/POST/PUT/DELETE /api/admin/coupons`; checkout recomputes the discount server-side, stores subtotal/discount/coupon_code on the session and charges SellAuth the discounted per-item amounts (with rounding drift absorbed into the last eligible line); `used_count` increments once when the webhook promotes the session. New admin "Coupons" tab with category chips + per-product exclusion pickers; checkout shows subtotal / discount / total. 89/89 backend tests pass

## Backlog
- P1: confirm the real SellAuth webhook payload shape on a live paid invoice and tighten field mapping
- P1: guest order lookup by email + order number; credential auto-purge after completion
- P2: coupon codes, admin order search/filters, sales analytics, audit log of credential reveals
- P2: split `server.py` into routers, admin 2FA
