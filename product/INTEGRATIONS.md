# Trendlines — Production Integrations Research

Everything required to turn the current prototype (static site + local pipeline)
into a real subscription business. Written August 2026. Prices/availability
should be re-verified before signing up — this space moves fast.

---

## 1. Payments & Billing

The single most important decision. Two viable paths for an Israeli-based operator:

### Option A — Merchant of Record (recommended to start)
A MoR is legally the seller: they handle global sales tax/VAT, card processing,
fraud, and payouts to you. Dramatically less compliance work; higher fee.

| Provider | Fees (approx.) | Israel support | Notes |
|---|---|---|---|
| **Paddle** | 5% + $0.50 | ✅ pays out to Israeli entities | Built for SaaS subscriptions; trials, proration, dunning built in; strong tax handling. Requires business registration and website review before approval. |
| **Lemon Squeezy** | 5% + $0.50 | ✅ | Simplest setup of all; now owned by Stripe. Great for launch, slightly fewer enterprise features. |
| **FastSpring** | ~5.9% + $0.95 | ✅ | Older, solid, less modern API. |

**Recommendation:** launch with **Paddle** or **Lemon Squeezy**. At $5/mo & $45/yr
price points, the ~5% fee is worth never touching VAT/sales-tax filings in
dozens of jurisdictions.

### Option B — Direct processor (later, at scale)
You are the merchant; you handle tax compliance yourself.

| Provider | Fees | Israel support | Notes |
|---|---|---|---|
| **Stripe Billing** | 2.9% + $0.30 + 0.5-0.8% billing | ⚠️ Stripe has no native Israel entity support — requires opening a US LLC (via Atlas, ~$500) or UK/EU entity | Best-in-class API, subscriptions, trials, customer portal. The standard choice worldwide. |
| **Israeli PSPs: Tranzila / Cardcom / Meshulam / Grow (Meshulam)** | ~1.2-2.5% + monthly fee | ✅ native | Work with Israeli business + local acquirer (Isracard/Max/Cal). APIs are dated; recurring billing exists but is clunky vs Stripe. Good if your audience is Israeli and you want local cards + Bit. |
| **PayPal Subscriptions** | ~3.5% | ✅ | Easy add-on button; poor subscription management; useful as a secondary method. |

**Bottom line:** MoR now → consider Stripe-via-US-LLC when MRR justifies it
(roughly >$3-5k MRR, where the ~2.5% fee difference pays for the accounting).

### Billing features you need regardless of provider
- 7-day free trial **without card** (your chosen model) → implement as an
  app-level entitlement, not a processor trial. Card-less trials mean the
  paywall conversion happens at day 7 in your app.
- Webhooks: `subscription.created / renewed / payment_failed / cancelled` →
  update the `subscriptions` table. Never trust client-side state (the current
  blur is UI-only demo).
- Dunning (failed-payment retries + emails) — built into Paddle/Stripe.
- Customer portal (cancel/upgrade/invoices) — built into both.

---

## 2. Database

Current state: local PostgreSQL (`stock_data`, 11M+ price rows) on a MacBook.
Production needs a managed Postgres plus a separation of concerns:

| Need | Recommendation | Alternatives | Est. cost |
|---|---|---|---|
| **Market data + signals DB** | **Neon** (serverless Postgres, generous free tier, branching for dev) | Supabase, AWS RDS, DigitalOcean Managed PG | $0-25/mo to start |
| **Users / auth / subscriptions DB** | **Supabase** (Postgres + built-in Auth + Row Level Security) | Same Neon cluster with an auth provider on top | $0-25/mo |
| Cache / rate limiting | Upstash Redis (serverless) | — | $0-10/mo |

Notes:
- Keep the research pipeline writing to its own schema; the web app reads from
  a `signals` schema through a read-only role. Never expose the raw pipeline DB
  to the web tier.
- 11M rows of OHLCV is small for Postgres — no need for anything exotic.
- Nightly `pg_dump` to object storage (Backblaze B2 / S3) — trivial and vital.

---

## 3. Authentication

| Option | Why | Cost |
|---|---|---|
| **Supabase Auth** (recommended if Supabase is the app DB) | Email magic-link + Google login, RLS integration, free to 50k MAU | free tier generous |
| Clerk | Best DX, beautiful prebuilt UI components | free to 10k MAU, then $25/mo |
| Auth0 | Enterprise standard, overkill here | free tier shrinking |

Model: `users` ←→ `subscriptions` (status, plan, trial_ends_at, paddle_customer_id).
The signals API checks entitlement server-side on every request; free users get
the top-1 signal per list from the same endpoint (server decides, not CSS blur).

---

## 4. Hosting & Architecture

```
[Alpha Vantage] → nightly worker (Python pipeline, cron 07:00 IL Tue-Sat)
                     │  writes signals + wallet state
                     ▼
              managed Postgres (Neon)
                     ▲
                     │ read-only API
[Next.js app on Vercel] ── auth (Supabase) ── billing webhooks (Paddle)
        │
   [users / browsers]
```

| Component | Recommendation | Notes | Est. cost |
|---|---|---|---|
| Web app | **Vercel** (Next.js) | The current static pages port naturally to Next.js; SSR lets the server decide what's blurred | $0-20/mo |
| Nightly pipeline worker | **Railway** or **Render** cron job / small VM; or a $6 Hetzner VPS | Needs Python + ~2GB RAM + 45 min/day runtime; the current LaunchAgent moves here so it stops depending on your MacBook being awake | $5-10/mo |
| Object storage (backups, reports) | Backblaze B2 or Cloudflare R2 | | ~$1/mo |
| DNS/CDN/WAF | Cloudflare (free) | | $0 |

---

## 5. Market Data (production licensing)

Currently: Alpha Vantage premium key. For a paid product, verify licensing:

- **Alpha Vantage**: premium tiers ($50-250/mo by rate limit). Their terms allow
  displaying *derived* data (signals, lines) in commercial products; redistributing
  raw OHLCV requires a business agreement — our use (signals + one price per stock)
  is derived, but get written confirmation.
- Alternatives if scaling/licensing becomes an issue: **Polygon.io** ($29-199/mo,
  clean licensing for display), **EODHD** (~$80/mo, includes delistings — would
  also fix our survivorship-bias limitation), **Tiingo** (~$50/mo).
- **Delisted-stock data** (EODHD/Norgate) is worth buying anyway to harden the
  backtests against survivorship bias.

---

## 6. WhatsApp Alerts (phase 2 — researched, not implemented)

| Option | How | Cost | Notes |
|---|---|---|---|
| **Meta WhatsApp Cloud API** (official) | Business verification + template approval; send via REST | ~$0.005-0.08 per conversation (varies by country; utility templates to Israel ≈ $0.0053) | The legitimate path. Requires a Meta Business account, a dedicated number, and pre-approved message templates ("Signal alert: {{ticker}}…"). |
| Twilio WhatsApp | Same Cloud API via Twilio's wrapper | Meta fee + $0.005 Twilio markup | Easier onboarding, good docs. |
| Green API / unofficial gateways | Automates a regular WhatsApp account | ~$20-40/mo | ⚠️ against WhatsApp ToS, numbers get banned — do not build a paid feature on this. |
| **Telegram bot (pragmatic alternative)** | Free Bot API, instant setup | $0 | Worth offering on day one *instead of* WhatsApp; many trading communities prefer it. |

Recommendation: launch with **Telegram** (free, zero approval), add official
WhatsApp Cloud API once there are paying users to justify the setup.

---

## 7. Transactional Email

Trial-ending reminders, payment receipts (MoR sends its own), signal digests.
- **Resend** — modern, 3k emails/mo free, React email templates. Recommended.
- Alternatives: Postmark (best deliverability, $15/mo), AWS SES (cheapest, more setup).

---

## 8. Analytics & Monitoring

- Product analytics: **Plausible** ($9/mo, privacy-friendly, no cookie banner needed) or PostHog (free tier, includes funnels + session replay).
- Error tracking: **Sentry** (free tier) for both the web app and the Python pipeline.
- Uptime + cron monitoring: **Healthchecks.io** (free) — pings when the nightly pipeline finishes; alerts if it didn't run. Directly addresses the "missing trading day" incident.

---

## 9. Legal & Compliance (Israel-specific — talk to a lawyer)

This is the highest-risk area for this specific product:

1. **Investment advice licensing (חוק הסדרת העיסוק בייעוץ השקעות, תשנ"ה-1995):**
   generic, non-personalized, algorithm-generated signals distributed identically
   to all subscribers generally fall under the "generic advice/publication"
   exemptions — but the line is thin, especially with words like "המלצות".
   Get a written legal opinion; consider renaming "המלצות" → "איתותים/סריקות"
   and adding the standard disclaimer to every page (already included in the
   footer of every page of the prototype).
2. **Terms of Service + Risk Disclaimer + Privacy Policy** — required before
   accepting payment. Privacy policy must cover the Israeli Privacy Protection
   Law + GDPR if EU users can subscribe (they can, with a MoR).
3. **Business registration**: עוסק מורשה / חברה בע"מ — required by Paddle/Lemon
   Squeezy onboarding anyway.
4. **Performance claims**: simulated results must be labeled as such everywhere
   (done in the prototype); avoid implying guaranteed returns.

---

## 10. Suggested rollout order

| Phase | Scope | New monthly cost |
|---|---|---|
| 1. Now | Static prototype (done) + Telegram channel for signals + Healthchecks on the pipeline | ~$0 |
| 2. MVP business | Next.js on Vercel + Supabase (auth+users) + Neon (signals) + Lemon Squeezy/Paddle billing + server-side paywall + move pipeline to Railway cron | ~$30-60 |
| 3. Growth | Official WhatsApp Cloud API, delisted-data feed (EODHD), Plausible/Sentry paid tiers, legal opinion + ToS package | ~$150-250 |

**Total to a real, paying MVP: roughly $30-60/month in infrastructure + one-time
legal work. The heaviest lift is not technical — it's the Paddle/Lemon Squeezy
onboarding (needs registered business + ToS pages) and the licensing opinion.**
